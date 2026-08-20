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


"""Named-client registry — the mechanic behind ``register`` / ``get_client`` /
``deregister`` in :mod:`forktex.storage`, :mod:`forktex.store` and
:mod:`forktex.vector`.

Promoted here on its third use, per ``code-reuse.md``: the three copies had
already diverged — each carried a differently-worded "not registered" message,
and only ``storage`` logged. The promoted implementation is ``storage``'s (the
one with logging and the most useful error), not a fresh synthesis.

Only the *lookup* half is shared. Construction stays with each facade, because
each builds a different client from different arguments — that is the part which
genuinely differs, and forcing it into a common signature would be the
"shared module that owns half a mechanic" failure the same standard warns about.
"""

from __future__ import annotations

from forktex.log import get_logger

logger = get_logger(__name__)


class ClientRegistry[T]:
    """A process-global map of name → client for one facade.

    Each facade owns one instance and keeps its own ``ClientNotRegisteredError``
    subclass, so a consumer catching ``forktex.storage.ClientNotRegisteredError``
    still gets a storage-specific type while the behaviour stays identical.
    """

    def __init__(self, facade: str, error: type[Exception]) -> None:
        """
        Args:
            facade: The module name used in log lines and error text (``"storage"``).
            error: The facade's own ``ClientNotRegisteredError`` — raised by
                :meth:`get`, so the exception type stays package-specific.
        """
        self._facade = facade
        self._error = error
        self._clients: dict[str, T] = {}

    def set(self, name: str, client: T) -> T:
        """Register ``client`` under ``name``, replacing any previous entry.

        Returns the client so a facade's ``register`` can ``return registry.set(...)``.
        Replacement is the caller's call to make: a client holding a live
        connection pool cannot be closed from here (closing is a coroutine on
        every one of them), so a facade that owns such a client warns first —
        see ``forktex.store.register``.
        """
        self._clients[name] = client
        logger.info("%s: client registered", self._facade, extra={"client": name})
        return client

    def get(self, name: str = "default") -> T:
        """Return the client registered as ``name``.

        Raises the facade's ``ClientNotRegisteredError``, naming what *is*
        registered — the message exists because "not registered" without the
        list is the least actionable error in a multi-client service.
        """
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
        """Remove ``name`` and return the dropped client, or ``None``. Idempotent.

        Lets tests and dev tooling restore the registry to a known shape without
        reaching into the underlying dict.
        """
        dropped = self._clients.pop(name, None)
        if dropped is not None:
            logger.info("%s: client deregistered", self._facade, extra={"client": name})
        return dropped

    def names(self) -> list[str]:
        """Every registered name, for diagnostics."""
        return list(self._clients)


__all__ = ["ClientRegistry"]
