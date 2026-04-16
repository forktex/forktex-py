"""forktex.fsd — FSD evaluation engine (no CLI dependencies).

Usage:
    from forktex.fsd import load_standard, evaluate

    standard = load_standard()
    result = evaluate(standard, project_root=Path("."), make_targets=targets)
"""

from forktex.fsd.loader import load_standard
from forktex.fsd.evaluate import evaluate, FSDResult, AtomResult, AtomStatus

__all__ = ["load_standard", "evaluate", "FSDResult", "AtomResult", "AtomStatus"]
