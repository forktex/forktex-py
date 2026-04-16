"""Legacy compatibility wrapper for ``forktex.agent.fsd.report``."""

from forktex.agent.fsd.report import GATES, TEMPLATES_DIR, _render_html, _run_gate, report

__all__ = ["GATES", "TEMPLATES_DIR", "_render_html", "_run_gate", "report"]
