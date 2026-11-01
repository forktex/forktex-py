# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

pytest.importorskip("cryptography", reason="cryptography not installed")

from forktex.database import BaseDBModel, TimestampMixin
from forktex.error import AppError
from forktex.vault import DecryptionError, EncryptedJSON, Vault
from tests.conftest import models_sessionmaker

KEK = "super-secret-key-for-testing-only"
KEK2 = "another-secret-key-for-rotation"

_vault_for_model = Vault(kek=KEK)


class _VaultSecret(BaseDBModel, TimestampMixin):
    __tablename__ = "vault_secret_test"

    id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid7)
    payload: Mapped[bytes | None] = mapped_column(EncryptedJSON(_vault_for_model), nullable=True)


def test_encrypt_decrypt_roundtrip() -> None:
    vault = Vault(kek=KEK)
    data = {"api_key": "sk-abc", "org_id": "org-xyz", "nested": {"a": 1}}
    blob = vault.encrypt(data)
    assert isinstance(blob, bytes)
    assert vault.decrypt(blob) == data


def test_encrypt_empty_dict() -> None:
    vault = Vault(kek=KEK)
    assert vault.decrypt(vault.encrypt({})) == {}


def test_encrypt_unicode_values() -> None:
    vault = Vault(kek=KEK)
    data = {"msg": "Ünïcödé héré 🎉", "lang": "ro"}
    assert vault.decrypt(vault.encrypt(data)) == data


def test_different_keks_produce_different_blobs() -> None:
    blob1 = Vault(kek=KEK).encrypt({"secret": "value"})
    blob2 = Vault(kek=KEK2).encrypt({"secret": "value"})
    assert blob1 != blob2


def test_same_kek_produces_different_blobs_each_call() -> None:
    vault = Vault(kek=KEK)
    data = {"x": 1}
    assert vault.encrypt(data) != vault.encrypt(data)


def test_wrong_kek_raises_on_decrypt() -> None:
    from cryptography.fernet import InvalidToken

    blob = Vault(kek=KEK).encrypt({"x": 1})
    with pytest.raises(DecryptionError) as excinfo:
        Vault(kek=KEK2).decrypt(blob)

    assert isinstance(excinfo.value, AppError)
    assert isinstance(excinfo.value.__cause__, InvalidToken)
    assert KEK2 not in str(excinfo.value)
    assert "blob" not in str(excinfo.value).lower() or "tampered" in str(excinfo.value)


def test_tampered_blob_raises() -> None:
    vault = Vault(kek=KEK)
    blob = bytearray(vault.encrypt({"x": 1}))
    blob[10] ^= 0xFF
    with pytest.raises(DecryptionError):
        vault.decrypt(bytes(blob))


def test_rotate_kek_roundtrip() -> None:
    vault = Vault(kek=KEK)
    data = {"credentials": "token-abc"}
    blob = vault.encrypt(data)
    new_blob = vault.rotate_kek(KEK2, blob)

    assert Vault(kek=KEK2).decrypt(new_blob) == data

    with pytest.raises(DecryptionError):
        Vault(kek=KEK2).decrypt(blob)


def test_rotate_kek_bytes_form() -> None:
    vault = Vault(kek=KEK)
    data = {"k": "v"}
    blob = vault.encrypt(data)
    new_blob = vault.rotate_kek(KEK2.encode(), blob)
    assert Vault(kek=KEK2).decrypt(new_blob) == data


def test_kek_bytes_input() -> None:
    vault = Vault(kek=KEK.encode())
    data = {"key": "val"}
    assert vault.decrypt(vault.encrypt(data)) == data


def test_kek_length_independence() -> None:
    for kek in ["a", "x" * 128, "中文キー"]:
        v = Vault(kek=kek)
        d = {"k": kek}
        assert v.decrypt(v.encrypt(d)) == d


def test_empty_string_kek_still_works() -> None:
    v = Vault(kek="")
    assert v.decrypt(v.encrypt({"k": "v"})) == {"k": "v"}


def test_repr_does_not_leak_key_material() -> None:
    v = Vault(kek=KEK)
    assert KEK not in repr(v)
    assert "signing_key" not in repr(v).lower()
    assert "encryption_key" not in repr(v).lower()


def test_non_json_native_values_are_stringified_not_rejected() -> None:
    vault = Vault(kek=KEK)
    data = {"raw": b"\x00\x01binary"}
    blob = vault.encrypt(data)
    assert vault.decrypt(blob) == {"raw": str(b"\x00\x01binary")}


@pytest.mark.asyncio
async def test_encrypted_json_column_roundtrip(postgres_url_str: str, fresh_schema: str) -> None:
    async with models_sessionmaker(postgres_url_str, fresh_schema, "forktex_grid") as maker:
        secret_data = {"api_key": "sk-test", "org_id": "org-1", "score": 42}

        async with maker() as session:
            row = _VaultSecret(payload=secret_data)
            session.add(row)
            await session.commit()
            row_id = row.id

        async with maker() as session:
            loaded = await session.get(_VaultSecret, row_id)
            assert loaded is not None
            assert loaded.payload == secret_data


@pytest.mark.asyncio
async def test_encrypted_json_wrong_vault_on_load_raises(postgres_url_str: str, fresh_schema: str) -> None:
    from sqlalchemy.orm import DeclarativeBase

    async with models_sessionmaker(postgres_url_str, fresh_schema, "forktex_grid") as maker:
        async with maker() as session:
            row = _VaultSecret(payload={"api_key": "sk-wrong-vault-test"})
            session.add(row)
            await session.commit()
            row_id = row.id

        wrong_vault = Vault(kek=KEK2)

        class _Base(DeclarativeBase):
            pass

        class _VaultSecretWrongVault(_Base):
            __tablename__ = "vault_secret_test"
            id: Mapped[uuid.UUID] = mapped_column(sa.UUID(as_uuid=True), primary_key=True)
            payload: Mapped[bytes | None] = mapped_column(EncryptedJSON(wrong_vault), nullable=True)

        async with maker() as session:
            with pytest.raises(DecryptionError):
                await session.get(_VaultSecretWrongVault, row_id)


@pytest.mark.asyncio
async def test_encrypted_json_null_roundtrip(postgres_url_str: str, fresh_schema: str) -> None:
    async with models_sessionmaker(postgres_url_str, fresh_schema, "forktex_grid") as maker:
        async with maker() as session:
            row = _VaultSecret(payload=None)
            session.add(row)
            await session.commit()
            row_id = row.id

        async with maker() as session:
            loaded = await session.get(_VaultSecret, row_id)
            assert loaded.payload is None
