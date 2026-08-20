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


"""ForkTex — the shared Python substrate for ForkTex services.

Twelve modules, one library, one set of opinions. Import only what you need;
each module's third-party dependency is an optional extra.

Primitives — always available, no extra required:

    log      — structured JSON logging (Loki-ready), trace_id contextvar
    error    — AppError hierarchy + ErrorEnvelope
    types    — base Pydantic models, frozen value objects
    iso      — canonical ISO-8601 date/time formatting and parsing

Role facades — one per piece of infrastructure:

    database — async Postgres engine, session, ORM bases, CRUD, advisory locks
    cache    — async Redis client, @cached, namespaced keys
    queue    — arq background-job queue                      [queue]
    storage  — S3/MinIO object storage (aioboto3)            [storage]
    store    — schemaless document records (pymongo)         [store]
    vector   — Qdrant vector search                          [vector]
    vault    — Fernet encryption, EncryptedJSON column type  [vault]
    graph    — typed multi-edge in-memory graph algebra

A module whose extra is missing raises ``ImportError`` naming it, e.g.
``Install 'forktex[vector]' (qdrant-client) to use forktex.vector``.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("forktex")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0.0.0+unknown"

# Nothing is re-exported here on purpose: importing the root must stay cheap.
# Reach for the module you need — ``from forktex import database`` — so a
# service that only wants ``log`` never pays for sqlalchemy or redis.

__all__ = ["__version__"]
