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

"""Observe-only desktop tools for local agent loops.

The first desktop-control milestone is intentionally read-only: identify
the session, capture screenshots, and return structured observation
metadata. Input injection belongs behind a later, explicit safety gate.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from forktex.agent.tools.base import Tool, ToolResult


_ENABLE_DESKTOP_ENV = "FORKTEX_ENABLE_DESKTOP"
_OBSERVATIONS_DIR = ".forktex/desktop-observations"


def desktop_enabled_default() -> bool:
    """Return whether desktop tools should be registered by default."""
    return os.environ.get(_ENABLE_DESKTOP_ENV, "").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class DesktopCapabilities:
    screenshot: bool
    observe: bool
    mouse: bool = False
    keyboard: bool = False
    window_focus: bool = False
    accessibility_tree: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return {
            "screenshot": self.screenshot,
            "observe": self.observe,
            "mouse": self.mouse,
            "keyboard": self.keyboard,
            "window_focus": self.window_focus,
            "accessibility_tree": self.accessibility_tree,
        }


class GnomeWaylandProvider:
    """Live GNOME/Wayland observe provider.

    The provider prefers tools that can operate in the current user session.
    ``grim`` is supported first because it is present on this development
    machine and works in many Wayland sessions. ``gnome-screenshot`` is kept
    as a pragmatic fallback for GNOME installations that ship it.
    """

    name = "gnome-wayland"

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root)

    def info(self) -> Dict[str, Any]:
        capture_backend = self._capture_backend()
        return {
            "provider": self.name,
            "session": {
                "type": os.environ.get("XDG_SESSION_TYPE"),
                "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
                "desktop_session": os.environ.get("DESKTOP_SESSION"),
                "wayland_display": os.environ.get("WAYLAND_DISPLAY"),
                "display": os.environ.get("DISPLAY"),
            },
            "capabilities": DesktopCapabilities(
                screenshot=capture_backend is not None,
                observe=capture_backend is not None,
            ).to_dict(),
            "capture_backend": capture_backend,
            "safety": {
                "mode": "observe-only",
                "input_enabled": False,
            },
        }

    def screenshot(
        self,
        *,
        include_base64: bool = False,
        save: bool = True,
    ) -> Dict[str, Any]:
        backend = self._capture_backend()
        if backend is None:
            raise RuntimeError(
                "No supported screenshot backend found. Install grim or "
                "gnome-screenshot, or use a desktop provider with capture support."
            )

        out_path = self._new_artifact_path() if save else None
        if out_path is None:
            temp_dir = self.project_root / _OBSERVATIONS_DIR
            temp_dir.mkdir(parents=True, exist_ok=True)
            out_path = temp_dir / f"tmp-{int(time.time() * 1000)}.png"

        self._capture(backend, out_path)
        data = out_path.read_bytes()

        result: Dict[str, Any] = {
            "provider": self.name,
            "backend": backend,
            "path": str(out_path) if save else None,
            "mime_type": "image/png",
            "bytes": len(data),
            "created_at": time.time(),
        }
        if include_base64:
            result["base64"] = base64.b64encode(data).decode("ascii")
        if not save:
            try:
                out_path.unlink()
            except OSError:
                pass
        return result

    def observe(self, *, include_base64: bool = False) -> Dict[str, Any]:
        info = self.info()
        screenshot = self.screenshot(include_base64=include_base64, save=True)
        observation = {
            "provider": self.name,
            "observed_at": time.time(),
            "desktop": info,
            "screenshot": screenshot,
        }
        self._record_observation(observation)
        return observation

    def _capture_backend(self) -> Optional[str]:
        if shutil.which("grim"):
            return "grim"
        if shutil.which("gnome-screenshot"):
            return "gnome-screenshot"
        return None

    def _capture(self, backend: str, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if backend == "grim":
            cmd = ["grim", str(out_path)]
        elif backend == "gnome-screenshot":
            cmd = ["gnome-screenshot", "-f", str(out_path)]
        else:
            raise RuntimeError(f"Unsupported screenshot backend: {backend}")

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"Screenshot capture failed via {backend}: {stderr}")

    def _new_artifact_path(self) -> Path:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        millis = int((time.time() % 1) * 1000)
        return self.project_root / _OBSERVATIONS_DIR / f"{timestamp}-{millis:03d}.png"

    def _record_observation(self, observation: Dict[str, Any]) -> None:
        try:
            from forktex_core.log import get_logger

            get_logger(__name__).info(
                "desktop observation captured",
                extra={
                    "provider": observation["provider"],
                    "screenshot_path": observation["screenshot"].get("path"),
                },
            )
        except Exception:
            pass


def create_desktop_tools(project_root: str) -> List[Tool]:
    """Create observe-only desktop tools bound to a project root."""
    provider = GnomeWaylandProvider(project_root)

    async def desktop_info() -> ToolResult:
        data = provider.info()
        return ToolResult(
            content=json.dumps(data, indent=2, sort_keys=True),
            data=data,
        )

    async def desktop_screenshot(
        include_base64: bool = False,
        save: bool = True,
    ) -> ToolResult:
        try:
            data = provider.screenshot(include_base64=include_base64, save=save)
        except Exception as exc:
            return ToolResult(content=str(exc), is_error=True)
        return ToolResult(
            content=json.dumps(
                {k: v for k, v in data.items() if k != "base64"},
                indent=2,
                sort_keys=True,
            ),
            data=data,
        )

    async def desktop_observe(include_base64: bool = False) -> ToolResult:
        try:
            data = provider.observe(include_base64=include_base64)
        except Exception as exc:
            return ToolResult(content=str(exc), is_error=True)
        printable = json.loads(json.dumps(data))
        if "base64" in printable.get("screenshot", {}):
            printable["screenshot"]["base64"] = "<omitted>"
        return ToolResult(
            content=json.dumps(printable, indent=2, sort_keys=True),
            data=data,
        )

    return [
        Tool(
            name="desktop_info",
            description=(
                "Report the current Linux desktop session and the available "
                "observe-only desktop automation capabilities."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=desktop_info,
        ),
        Tool(
            name="desktop_screenshot",
            description=(
                "Capture a PNG screenshot from the current desktop session. "
                "This tool is observe-only and does not move the mouse or type."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "include_base64": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include base64 PNG bytes in the tool data.",
                    },
                    "save": {
                        "type": "boolean",
                        "default": True,
                        "description": "Persist the screenshot under .forktex.",
                    },
                },
                "additionalProperties": False,
            },
            handler=desktop_screenshot,
        ),
        Tool(
            name="desktop_observe",
            description=(
                "Capture one observe-only desktop snapshot: session metadata, "
                "capabilities, and a screenshot artifact."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "include_base64": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include base64 PNG bytes in the tool data.",
                    },
                },
                "additionalProperties": False,
            },
            handler=desktop_observe,
        ),
    ]
