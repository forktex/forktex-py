"""Legacy compatibility wrapper for ``forktex.agent.fsd.check``."""

from forktex.agent.fsd.check import (
    TEMPLATES_DIR,
    SKIP_DIRS,
    _discover_services,
    _evaluate,
    _find_makefile_targets,
    _render_html,
    check,
)

__all__ = [
    "TEMPLATES_DIR",
    "SKIP_DIRS",
    "_discover_services",
    "_evaluate",
    "_find_makefile_targets",
    "_render_html",
    "check",
]
