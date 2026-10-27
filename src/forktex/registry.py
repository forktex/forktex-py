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

from forktex.log import get_logger

logger = get_logger(__name__)


class ClientRegistry[T]:
    def __init__(self, facade: str, error: type[Exception]) -> None:
        self._facade = facade
        self._error = error
        self._clients: dict[str, T] = {}

    def set(self, name: str, client: T) -> T:
        self._clients[name] = client
        logger.info("%s: client registered", self._facade, extra={"client": name})
        return client

    def get(self, name: str = "default") -> T:
        try:
            return self._clients[name]
        except KeyError:
            registered = ", ".join(f'"{k}"' for k in self._clients) or "(none)"
            raise self._error(
                f"No {self._facade} client named {name!r}. "
                f"Registered clients: {registered}. "
                f"Call {self._facade}.register({name!r}, ...) at startup."
            ) from None

    def pop(self, name: str = "default") -> T | None:
        dropped = self._clients.pop(name, None)
        if dropped is not None:
            logger.info("%s: client deregistered", self._facade, extra={"client": name})
        return dropped

    def names(self) -> list[str]:
        return list(self._clients)


__all__ = ["ClientRegistry"]
