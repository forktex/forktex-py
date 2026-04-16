"""forktex.agent.scraper.truths — Per-domain knowledge store.

Persists reusable selectors, XPaths, flows, field mappings, and notes
to .forktex/scraper/truths/{domain}.json so the agent can recycle
verified patterns across sessions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class TruthsStore:
    """Per-domain knowledge persisted to disk."""

    VALID_CATEGORIES = ("selectors", "xpaths", "flows", "field_mappings", "notes")

    def __init__(self, project_root: str) -> None:
        self._root = Path(project_root) / ".forktex" / "scraper" / "truths"
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, domain: str) -> Path:
        safe = domain.replace("/", "_").replace(":", "_")
        return self._root / f"{safe}.json"

    def load(self, domain: str) -> Optional[Dict]:
        """Load all truths for a domain, or None if not found."""
        p = self._path(domain)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def save_entry(
        self,
        domain: str,
        category: str,
        key: str,
        value: Any,
        confidence: float = 1.0,
    ) -> None:
        """Save or update a single entry in a domain's truths."""
        if category not in self.VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Must be one of: {self.VALID_CATEGORIES}"
            )

        data = self.load(domain) or {
            "domain": domain,
            "version": 0,
            "updated_at": "",
            "categories": {c: {} for c in self.VALID_CATEGORIES},
        }

        cat = data["categories"].setdefault(category, {})
        existing = cat.get(key, {})
        entry_version = existing.get("version", 0) + 1

        cat[key] = {
            "value": value,
            "confidence": confidence,
            "version": entry_version,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        data["version"] = data.get("version", 0) + 1
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        self._path(domain).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def list_domains(self) -> List[str]:
        """List all domains that have truths stored."""
        domains = []
        for p in self._root.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                domains.append(data.get("domain", p.stem))
            except (json.JSONDecodeError, OSError):
                domains.append(p.stem)
        return domains
