"""
Forktex - Python SDK

pip install forktex

Includes:
- Core: state management, utilities, config
- Intelligence: agentic AI via Intelligence API (also available standalone: pip install forktex-intelligence)
- Cloud: infrastructure management
- Agent: CLI and interactive tools

Quick Start:
    from forktex.core.state import StateManager
    from forktex_intelligence import Intelligence
    from forktex_cloud.client import ForktexCloudClient

CLI:
    forktex chat
"""

__version__ = "1.0.0"
__author__ = "Forktex Team"

# Core library exports — always available, no optional deps
from forktex.core.state import StateManager
from forktex.core.utils import generate_id, current_timestamp
from forktex.core.paths import (
    get_global_config_dir,
    get_project_config_dir,
    ensure_global_config_dir,
    ensure_project_config_dir,
)
from forktex.config import Settings, get_settings

__all__ = [
    "__version__",
    # Core
    "StateManager",
    "generate_id",
    "current_timestamp",
    "get_global_config_dir",
    "get_project_config_dir",
    "ensure_global_config_dir",
    "ensure_project_config_dir",
    # Config
    "Settings",
    "get_settings",
]
