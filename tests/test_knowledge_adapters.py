# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""Generic knowledge adapters — point forktex at any markdown tree / codebase.

Covers the two new adapters (`generic_markdown`, `code_index`), their
registration, the resolver composing declared `config.layers`, and the ad-hoc
`extra_sources` overlay (the `--source` CLI path).
"""

from __future__ import annotations

from forktex.agent.knowledge.sources import (
    build_knowledge_resolver,
    known_adapters,
    load_code_index,
    load_generic_markdown,
)


def _markdown_tree(root):
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "guide.md").write_text(
        "---\ntitle: My Guide\ntags: [a, b]\n---\n# Heading\nbody text",
        encoding="utf-8",
    )
    (root / "readme.md").write_text(
        "# Readme Title\nplain prose here", encoding="utf-8"
    )
    (root / "node_modules").mkdir()
    (root / "node_modules" / "skip.md").write_text("vendored", encoding="utf-8")
    (root / ".hidden").mkdir()
    (root / ".hidden" / "x.md").write_text("hidden", encoding="utf-8")
    return root


def _code_tree(root):
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "src" / "ui.ts").write_text("export const a = 1\n", encoding="utf-8")
    (root / "README.md").write_text("not code", encoding="utf-8")  # not indexed
    (root / "node_modules").mkdir()
    (root / "node_modules" / "v.js").write_text("vendored", encoding="utf-8")
    return root


# ── generic_markdown ────────────────────────────────────────────────────────


def test_generic_markdown_loads_and_skips_vendored(tmp_path):
    ws = load_generic_markdown(_markdown_tree(tmp_path))
    ids = set(ws.nodes)
    assert ids == {"md.docs-guide.md", "md.readme.md"}  # node_modules + .hidden skipped

    guide = ws.nodes["md.docs-guide.md"]
    assert guide.kind == "markdown"
    assert guide.title == "My Guide"  # frontmatter title wins
    assert guide.tags == ["a", "b"]

    readme = ws.nodes["md.readme.md"]
    assert readme.title == "Readme Title"  # first H1 fallback
    assert readme.summary == "plain prose here"  # body excerpt → searchable


# ── code_index ──────────────────────────────────────────────────────────────


def test_code_index_loads_source_files(tmp_path):
    ws = load_code_index(_code_tree(tmp_path))
    ids = set(ws.nodes)
    assert ids == {"code.src-app.py", "code.src-ui.ts"}  # .md + node_modules excluded

    app = ws.nodes["code.src-app.py"]
    assert app.kind == "code.python"
    assert app.title == "src/app.py"
    assert "python" in app.tags and "src" in app.tags
    assert "def f()" in app.body_md


def test_code_index_size_cap_skips_large(tmp_path, monkeypatch):
    import forktex.agent.knowledge.sources as src

    monkeypatch.setattr(src, "_CODE_MAX_BYTES", 8)
    (tmp_path / "big.py").write_text("x = " + "1" * 100, encoding="utf-8")
    (tmp_path / "small.py").write_text("y=1", encoding="utf-8")
    ws = load_code_index(tmp_path)
    assert "code.small.py" in ws.nodes
    assert "code.big.py" not in ws.nodes  # over the cap


# ── registry + resolver composition ─────────────────────────────────────────


def test_known_adapters_includes_all_four():
    assert known_adapters() >= {
        "docs_corpus",
        "workspace",
        "generic_markdown",
        "code_index",
    }


def test_resolver_composes_declared_layers(tmp_path):
    from forktex.manifest.models import KnowledgeConfig, KnowledgeLayerDef

    (tmp_path / "note.md").write_text("# Note\nthe flux widget", encoding="utf-8")
    cfg = KnowledgeConfig(
        layers=[
            KnowledgeLayerDef(
                name="notes", path=str(tmp_path), adapter="generic_markdown"
            )
        ]
    )
    ws = build_knowledge_resolver(config=cfg).resolve("knowledge")
    assert "md.note.md" in ws.nodes


def test_resolver_extra_sources_overlay(tmp_path):
    (tmp_path / "x.md").write_text("# X\noverlay content", encoding="utf-8")
    r = build_knowledge_resolver(
        extra_sources=[("adhoc", str(tmp_path), "generic_markdown")]
    )
    assert "adhoc" in r.namespaces()
    assert "md.x.md" in r.resolve("knowledge").nodes


def test_doctor_accepts_new_adapters():
    """doctor validates layer adapters against the live registry (no drift)."""
    from forktex.manifest.models import KnowledgeConfig, KnowledgeLayerDef

    for adapter in ("generic_markdown", "code_index"):
        cfg = KnowledgeConfig(
            layers=[KnowledgeLayerDef(name="x", path=".", adapter=adapter)]
        )
        bad = [
            layer.adapter
            for layer in cfg.layers
            if layer.adapter not in known_adapters()
        ]
        assert not bad
