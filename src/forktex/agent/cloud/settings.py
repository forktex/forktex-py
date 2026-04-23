"""Cloud context persistence — load/save CloudContext from .forktex/ files.

CloudContext (from forktex_cloud SDK) is a pure data model.  This module
owns all filesystem I/O: reading ``~/.forktex/cloud.json`` (global) and
``<project>/.forktex/cloud.json`` (project-level), merging them, and
persisting changes back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forktex_cloud.config import CloudContext
from forktex.core.paths import (
    get_global_config_dir,
    get_project_config_dir,
)

_CLOUD_CONFIG_FILENAME = "cloud.json"


def load_cloud_context(project_root: Path | None = None) -> CloudContext:
    """Load cloud context, merging global + project-level configs.

    Resolution: project-level overrides global.
    """
    data: dict[str, Any] = {}

    # Global config
    global_path = get_global_config_dir() / _CLOUD_CONFIG_FILENAME
    if global_path.exists():
        try:
            data = json.loads(global_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Project-level config (overrides global)
    if project_root:
        project_path = get_project_config_dir(project_root) / _CLOUD_CONFIG_FILENAME
        if project_path.exists():
            try:
                project_data = json.loads(project_path.read_text())
                data.update(project_data)
            except (json.JSONDecodeError, OSError):
                pass

    return CloudContext(
        controller=data.get("controller"),
        account_key=data.get("account_key"),
        access_token=data.get("access_token"),
        org_id=data.get("org_id"),
        region=data.get("region"),
        project_keys=data.get("project_keys", {}),
        current_project=data.get("current_project"),
        current_server=data.get("current_server"),
        current_environment=data.get("current_environment"),
    )


def save_cloud_context_global(ctx: CloudContext) -> None:
    """Persist controller + credentials to ~/.forktex/cloud.json."""
    path = get_global_config_dir() / _CLOUD_CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "controller": ctx.controller,
        "account_key": ctx.account_key,
        "access_token": ctx.access_token,
        "org_id": ctx.org_id,
        "region": ctx.region,
        "project_keys": ctx.project_keys,
    }
    path.write_text(json.dumps(data, indent=2) + "\n")


def save_cloud_context_project(ctx: CloudContext, project_root: Path) -> None:
    """Persist project-specific state to .forktex/cloud.json."""
    path = get_project_config_dir(project_root) / _CLOUD_CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "current_project": ctx.current_project,
        "current_server": ctx.current_server,
        "current_environment": ctx.current_environment,
    }
    path.write_text(json.dumps(data, indent=2) + "\n")
