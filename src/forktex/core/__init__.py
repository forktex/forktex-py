"""forktex.core - Core utilities, state management, and path resolution."""

from forktex.core.utils import generate_id, current_timestamp
from forktex.core.state import StateManager
from forktex.core.paths import (
    get_global_config_dir,
    get_project_config_dir,
    ensure_global_config_dir,
    ensure_project_config_dir,
    get_global_config_file,
    get_project_config_file,
)

__all__ = [
    "generate_id",
    "current_timestamp",
    "StateManager",
    "get_global_config_dir",
    "get_project_config_dir",
    "ensure_global_config_dir",
    "ensure_project_config_dir",
    "get_global_config_file",
    "get_project_config_file",
]
