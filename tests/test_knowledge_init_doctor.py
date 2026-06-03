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

"""``forktex knowledge init`` + ``forktex knowledge doctor`` — the bootstrap
and drift-detector that make the system usable from *any* forktex/* project.

The init test is the v1 acceptance for "useful for any forktex/* project": a
fresh tmp dir, one command, and the project doc-space is ready to recycle into
and grounded against.
"""

from __future__ import annotations

import json
from pathlib import Path

from forktex.agent.knowledge.doctor import exit_code, format_report, run_doctor
from forktex.agent.knowledge.init import init_doc_space
from forktex.agent.knowledge.recycle import recycle
from forktex.agent.knowledge.retire import retire
from forktex.agent.knowledge.rollup import rollup


def test_init_scaffolds_fresh_project(tmp_path: Path) -> None:
    """One-command bootstrap: empty repo → ready doc-space + manifest block."""
    # Pretend this is a real forktex project — minimal forktex.json present.
    (tmp_path / "forktex.json").write_text(
        json.dumps({"manifestVersion": "1.0.0", "name": "demo", "version": "0.0.1"})
    )

    result = init_doc_space(tmp_path)

    assert result.created_dirs is True
    assert result.created_readme is True
    assert result.added_manifest_block is True
    assert (tmp_path / ".forktex" / "knowledge" / "nodes").is_dir()
    assert (tmp_path / ".forktex" / "knowledge" / "patches").is_dir()
    assert (tmp_path / ".forktex" / "knowledge" / "README.md").is_file()

    # forktex.json now carries explicit [knowledge] defaults — discoverable.
    manifest = json.loads((tmp_path / "forktex.json").read_text())
    assert manifest["knowledge"]["pinnedTag"] == "pinned"
    assert manifest["knowledge"]["groundingCharBudget"] == 4000


def test_init_produces_spec_clean_forktex_dir(tmp_path: Path) -> None:
    """``knowledge init`` must run the standard lifecycle bootstrap so the
    .forktex/ it creates passes ``structure.audit`` with no orphans and no
    missing-required entries — knowledge-only inits used to leave a dir that
    lacked .version/.gitignore and carried an undeclared knowledge/README.md.
    """
    from forktex.substrate.spec import audit

    (tmp_path / "forktex.json").write_text(
        json.dumps({"manifestVersion": "1.0.0", "name": "demo", "version": "0.0.1"})
    )

    init_doc_space(tmp_path)

    # Lifecycle bootstrap landed the required files.
    assert (tmp_path / ".forktex" / ".version").is_file()
    assert (tmp_path / ".forktex" / ".gitignore").is_file()

    entries = audit("project", tmp_path)
    orphans = [e for e in entries if e.status == "unknown"]
    missing = [e for e in entries if e.status == "missing_required"]
    assert orphans == [], f"unexpected orphans: {[e.rel_path for e in orphans]}"
    assert missing == [], f"missing required: {[e.rel_path for e in missing]}"


def test_init_is_idempotent(tmp_path: Path) -> None:
    """Re-running init on an existing doc-space doesn't clobber user state."""
    init_doc_space(tmp_path)
    (tmp_path / ".forktex" / "knowledge" / "README.md").write_text("# my custom readme")

    result = init_doc_space(tmp_path)

    assert result.created_dirs is False
    assert result.created_readme is False  # we don't overwrite the existing one
    assert (
        (tmp_path / ".forktex" / "knowledge" / "README.md").read_text()
        == "# my custom readme"
    )


def test_init_preserves_existing_manifest_block(tmp_path: Path) -> None:
    """An existing [knowledge] block in forktex.json is left untouched."""
    (tmp_path / "forktex.json").write_text(
        json.dumps(
            {
                "manifestVersion": "1.0.0",
                "name": "demo",
                "knowledge": {"pinnedTag": "always", "groundingCharBudget": 7777},
            }
        )
    )
    result = init_doc_space(tmp_path)
    assert result.added_manifest_block is False
    manifest = json.loads((tmp_path / "forktex.json").read_text())
    assert manifest["knowledge"]["pinnedTag"] == "always"  # preserved


def test_doctor_clean_doc_space_reports_zero_issues(tmp_path: Path) -> None:
    init_doc_space(tmp_path)
    recycle(
        tmp_path / ".forktex" / "knowledge",
        id="lesson.clean",
        title="A clean lesson",
        summary="Nothing wrong here.",
    )
    issues = run_doctor(tmp_path)
    assert issues == []
    assert exit_code(issues, strict=False) == 0
    assert exit_code(issues, strict=True) == 0


def test_doctor_surfaces_dangling_reference(tmp_path: Path) -> None:
    init_doc_space(tmp_path)
    space = tmp_path / ".forktex" / "knowledge"
    recycle(space, id="lesson.has-ref", title="With ref", references=["nonexistent.id"])

    issues = run_doctor(tmp_path)
    codes = {i.code for i in issues}
    assert "reference-dangling" in codes
    assert exit_code(issues, strict=False) == 0  # warning only
    assert exit_code(issues, strict=True) == 1  # strict mode escalates


def test_doctor_surfaces_filename_id_mismatch(tmp_path: Path) -> None:
    init_doc_space(tmp_path)
    space = tmp_path / ".forktex" / "knowledge"
    recycle(space, id="lesson.real", title="Real")
    # Move the file to a path whose stem disagrees with the node's id.
    (space / "nodes" / "lesson.real.md").rename(space / "nodes" / "lesson.wrong-name.md")

    issues = run_doctor(tmp_path)
    codes = {i.code for i in issues}
    assert "filename-id-mismatch" in codes
    assert exit_code(issues, strict=False) == 1  # this is an error


def test_doctor_flags_retired_with_inbound_refs(tmp_path: Path) -> None:
    init_doc_space(tmp_path)
    space = tmp_path / ".forktex" / "knowledge"
    recycle(space, id="lesson.target", title="Will be retired")
    recycle(
        space, id="lesson.referrer", title="Points at target", references=["lesson.target"]
    )
    retire(space, "lesson.target", reason="Superseded.")

    issues = run_doctor(tmp_path)
    codes = {i.code for i in issues}
    assert "retired-inbound" in codes


def test_doctor_missing_doc_space_prompts_init(tmp_path: Path) -> None:
    issues = run_doctor(tmp_path)
    assert len(issues) == 1
    assert issues[0].code == "doc-space-missing"
    assert "init" in issues[0].message  # tells the user what to do
    assert exit_code(issues, strict=False) == 1


def test_doctor_end_to_end_round_trip(tmp_path: Path) -> None:
    """init → recycle → retire → rollup → doctor: every step works in one place."""
    init_doc_space(tmp_path)
    space = tmp_path / ".forktex" / "knowledge"
    recycle(space, id="topic.demo", title="Demo topic", summary="Parent.")
    recycle(
        space, id="lesson.demo-child", title="Demo child", summary="Will be folded.",
        references=["topic.demo"],
    )
    # Build a real parent-edge via a hand-set Node (recycle doesn't expose parents today).
    from forktex_core.fractal import Node
    from forktex_core.fractal.io import dump_node

    dump_node(
        Node(
            id="lesson.demo-child",
            kind="lesson",
            title="Demo child",
            summary="Will be folded.",
            parents=["topic.demo"],
        ),
        space / "nodes" / "lesson.demo-child.md",
    )
    rollup(space, "topic.demo")
    retire(space, "lesson.demo-child")  # already rolled-up, but retire wins (per plan)

    assert run_doctor(tmp_path) == []  # clean even after the chain
    report = format_report([], project_root=tmp_path)
    assert "0 issues" in report
