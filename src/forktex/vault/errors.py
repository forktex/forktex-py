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


"""Vault module errors."""

from __future__ import annotations

from forktex.error import AppError, AppErrorCode


class VaultError(AppError):
    """Base class for vault errors."""

    code = AppErrorCode.INTERNAL


class DecryptionError(VaultError):
    """Raised when a blob cannot be decrypted.

    Deliberately does **not** distinguish "wrong KEK" from "tampered ciphertext":
    Fernet reports both as one failure, and only an operator with the key history
    can tell them apart. That ambiguity is preserved rather than guessed at — the
    original ``cryptography.fernet.InvalidToken`` stays on ``__cause__`` for the
    log/tracker, while callers get an ``AppError`` their boundary can render.

    ``INTERNAL``, not a 4xx: a blob that will not open is a key-management or
    integrity problem on the server side, never something the caller of an
    endpoint can fix by changing their request.

    Carries no plaintext, no ciphertext and no key material in its message.
    """


__all__ = ["DecryptionError", "VaultError"]
