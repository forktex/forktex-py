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


import base64
import hashlib
import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import TypeDecorator
from sqlalchemy.engine import Dialect

from forktex.log import get_logger
from forktex.vault.errors import DecryptionError, VaultError

logger = get_logger(__name__)


def _derive_fernet_key(kek: str | bytes) -> bytes:
    if isinstance(kek, str):
        kek = kek.encode()
    digest = hashlib.sha256(kek).digest()
    return base64.urlsafe_b64encode(digest)


class Vault:
    def __init__(self, kek: str | bytes) -> None:
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise ImportError("Install 'forktex[vault]' (cryptography) to use forktex.vault") from exc
        self._fernet = Fernet(_derive_fernet_key(kek))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(<redacted>)"

    def encrypt(self, data: dict[str, Any]) -> bytes:
        plaintext = json.dumps(data, default=str).encode()
        return self._fernet.encrypt(plaintext)

    def decrypt(self, blob: bytes) -> dict[str, Any]:
        try:
            plaintext = self._fernet.decrypt(blob)
        except Exception as exc:
            logger.error(
                "vault: decryption failed — wrong KEK or tampered ciphertext",
                extra={"blob_bytes": len(blob)},
            )
            raise DecryptionError("decryption failed — wrong KEK or tampered ciphertext") from exc
        return json.loads(plaintext)

    def rotate_kek(self, new_kek: str | bytes, blob: bytes) -> bytes:
        from cryptography.fernet import Fernet

        data = self.decrypt(blob)
        new_fernet = Fernet(_derive_fernet_key(new_kek))
        logger.info("vault: re-wrapping blob under a new KEK", extra={"blob_bytes": len(blob)})
        return new_fernet.encrypt(json.dumps(data, default=str).encode())


class EncryptedJSON(TypeDecorator):
    impl = sa.LargeBinary
    cache_ok = True

    def __init__(self, vault: Vault) -> None:
        super().__init__()
        self._vault = vault

    def process_bind_param(self, value: dict | None, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        return self._vault.encrypt(value)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> dict | None:
        if value is None:
            return None
        return self._vault.decrypt(value)


__all__ = ["DecryptionError", "EncryptedJSON", "Vault", "VaultError"]
