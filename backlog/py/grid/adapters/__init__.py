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

"""File-format ingestion adapters — a declared SEAM (no drivers yet).

Once the base sync interface is proven, drivers for excel/csv/image/text/pptx/
docling register here. Each turns raw bytes for a format into a *proposed*
table+column config and rows, which the caller applies through the validated
write path. This module only ships the Protocol + registry today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class IngestProposal:
    """A format adapter's proposed grid shape + rows for review/apply."""

    columns: list[dict[str, Any]] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@runtime_checkable
class FileAdapter(Protocol):
    """Turns raw file bytes of a given format into an :class:`IngestProposal`."""

    format: str  # e.g. "csv", "xlsx", "pdf"

    def parse(
        self, content: bytes, *, filename: str | None = None
    ) -> IngestProposal: ...


_ADAPTERS: dict[str, FileAdapter] = {}


def register_adapter(adapter: FileAdapter, *, replace: bool = False) -> None:
    if not replace and adapter.format in _ADAPTERS:
        raise ValueError(f"Adapter for format {adapter.format!r} already registered")
    _ADAPTERS[adapter.format] = adapter


def get_adapter(fmt: str) -> FileAdapter | None:
    return _ADAPTERS.get(fmt)


def available_formats() -> list[str]:
    return sorted(_ADAPTERS)


__all__ = [
    "IngestProposal",
    "FileAdapter",
    "register_adapter",
    "get_adapter",
    "available_formats",
]
