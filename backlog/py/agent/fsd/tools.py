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

"""FSD ``Tool`` catalog — the delivery-standard audit as agent/API/MCP tools.

Wraps the same ``_evaluate`` orchestration ``forktex fsd check`` uses, so the
``/fsd`` domain on the generic tool API (and MCP) reports per-atom pass/fail and
the achieved maturity level over the *one* evaluation path — no second author.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forktex.agent.tools.base import Tool, ToolResult


def create_fsd_tools(project_root: str | Path) -> list[Tool]:
    """Bind the FSD audit into the forktex tool catalog for *project_root*."""
    root = Path(project_root).resolve()

    async def _check(**_kw: Any) -> ToolResult:
        from forktex.agent.fsd.check import _evaluate

        try:
            data = _evaluate(root)
        except Exception as exc:  # loader / manifest / make errors → tool error
            return ToolResult(content=f"fsd check failed: {exc}", is_error=True)

        summary = {
            "project": data.get("project"),
            "level": data.get("level"),
            "root_makefile": data.get("root_makefile"),
            "atoms": [
                {
                    "name": a.get("name"),
                    "status": a.get("status"),
                    "missing_required": a.get("missing_required", []),
                }
                for a in data.get("atoms", [])
            ],
        }
        return ToolResult(content=json.dumps(summary, ensure_ascii=False))

    return [
        Tool(
            name="fsd_check",
            description=(
                "Audit the project against the ForkTex Standard for Delivery (FSD): "
                "returns per-atom pass/fail/skip + the achieved maturity level (L0–L4). "
                "Use this to know what delivery gates a project does and doesn't meet."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=_check,
        ),
    ]


__all__ = ["create_fsd_tools"]
