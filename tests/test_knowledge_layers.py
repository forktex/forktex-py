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

"""Target-agnostic mode: when ``forktex.json [knowledge].layers`` is set, the
resolver composes against any directory layout — no assumption about
``.forktex/knowledge/`` or ``docs/engineering/*.md``. The substrate stays
agnostic; each layer declares its own adapter.

This is the v1 unlock that lets the knowledge mechanism work for *any*
forktex/* project (and beyond) without forcing a particular workspace shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from forktex_core.fractal import FractalQuery

from forktex.agent.knowledge.config import load_knowledge_config
from forktex.agent.knowledge.recycle import recycle
from forktex.agent.knowledge.search import ranked_search
from forktex.agent.knowledge.sources import (
    COMPOSED_NAMESPACE,
    build_knowledge_resolver,
)
from forktex.manifest.models import KnowledgeConfig, KnowledgeLayerDef


def test_layers_config_overrides_default_two_layer(tmp_path: Path) -> None:
    """Custom layer paths replace the default docs+project composition."""
    # Two custom workspaces in unusual locations.
    a = tmp_path / "team" / "principles"
    b = tmp_path / "repo" / "notes"
    recycle(a, id="principle.battle-test", title="Battle test", summary="No mocks.")
    recycle(b, id="note.local", title="Local note", summary="Project-specific.")

    cfg = KnowledgeConfig(
        layers=[
            KnowledgeLayerDef(name="principles", path=str(a), adapter="workspace"),
            KnowledgeLayerDef(name="local", path=str(b), adapter="workspace"),
        ]
    )
    resolver = build_knowledge_resolver(config=cfg)

    # Both layers + the composed view are addressable.
    assert set(resolver.namespaces()) == {COMPOSED_NAMESPACE, "principles", "local"}

    # The composed view sees both nodes.
    query = FractalQuery(resolver)
    nodes = ranked_search(query, COMPOSED_NAMESPACE, "battle test mock", limit=5)
    assert any(n.id == "principle.battle-test" for n in nodes)
    nodes = ranked_search(query, COMPOSED_NAMESPACE, "project specific note", limit=5)
    assert any(n.id == "note.local" for n in nodes)


def test_config_block_loads_from_forktex_json(tmp_path: Path) -> None:
    """A real forktex.json [knowledge] block resolves via load_knowledge_config()."""
    (tmp_path / "forktex.json").write_text(
        json.dumps(
            {
                "manifestVersion": "1.0.0",
                "name": "demo",
                "version": "0.0.1",
                "knowledge": {
                    "pinnedTag": "always",
                    "groundingCharBudget": 1234,
                    "knowledgeLimit": 7,
                    "retiredStatuses": ["dead", "rolled-up"],
                    "layers": [
                        {"name": "x", "path": "x_space", "adapter": "workspace"},
                    ],
                },
            }
        )
    )
    cfg = load_knowledge_config(tmp_path)
    assert cfg.pinned_tag == "always"
    assert cfg.grounding_char_budget == 1234
    assert cfg.knowledge_limit == 7
    assert cfg.retired_statuses == ["dead", "rolled-up"]
    assert cfg.layers is not None
    assert len(cfg.layers) == 1
    assert cfg.layers[0].adapter == "workspace"


def test_config_defaults_on_missing_manifest(tmp_path: Path) -> None:
    """No forktex.json at all → defaults (preserves pre-v1 behaviour exactly)."""
    cfg = load_knowledge_config(tmp_path)
    assert cfg.pinned_tag == "pinned"
    assert cfg.grounding_char_budget == 4000
    assert cfg.knowledge_limit == 40
    assert cfg.layers is None  # signals "use default two-layer composition"


def test_unknown_adapter_skipped_not_crashed(tmp_path: Path) -> None:
    """An unknown adapter (typo, future-but-unsupported) doesn't blow up the resolver."""
    a = tmp_path / "real"
    recycle(a, id="n.real", title="Real")

    cfg = KnowledgeConfig(
        layers=[
            KnowledgeLayerDef(name="real", path=str(a), adapter="workspace"),
            KnowledgeLayerDef(name="bogus", path=str(tmp_path / "nope"), adapter="not_real"),
        ]
    )
    resolver = build_knowledge_resolver(config=cfg)
    # Only the recognized layer made it through.
    assert "real" in resolver.namespaces()
    assert "bogus" not in resolver.namespaces()
