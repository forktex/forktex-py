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

"""Tests for SECURITY.md §G — agent history hardening."""

import json
import stat
import sys

import pytest

from forktex.agent.state import AgentStateStore


pytestmark = pytest.mark.usefixtures("isolated_home")


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ── Default redactions ───────────────────────────────────────────────────


def test_default_redacts_forktex_api_key(project_root):
    store = AgentStateStore(str(project_root))
    store.append(
        "agent-1",
        {"event": "tool_call", "args": {"api_key": "ftx-abcdef0123456789xyz"}},
    )
    path = store._agent_path("agent-1")
    raw = path.read_text()
    assert "ftx-abcdef0123456789xyz" not in raw
    assert "***REDACTED***" in raw


def test_default_redacts_jwt(project_root):
    store = AgentStateStore(str(project_root))
    jwt = (
        "eyJhbGciOiJIUzI1NiJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    store.append("a", {"output": f"got token: {jwt}"})
    raw = store._agent_path("a").read_text()
    assert jwt not in raw
    assert "***REDACTED***" in raw


def test_default_redacts_bearer_header(project_root):
    store = AgentStateStore(str(project_root))
    store.append(
        "a",
        {"headers": "Authorization: Bearer abcdef0123456789ABCDEF=="},
    )
    raw = store._agent_path("a").read_text()
    assert "abcdef0123456789ABCDEF" not in raw


def test_default_redacts_pem_block(project_root):
    store = AgentStateStore(str(project_root))
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIICXAIB...\n-----END RSA PRIVATE KEY-----"
    store.append("a", {"key": pem})
    raw = store._agent_path("a").read_text()
    assert "MIICXAIB" not in raw
    assert "***REDACTED***" in raw


def test_default_redacts_github_token(project_root):
    store = AgentStateStore(str(project_root))
    store.append("a", {"github": "ghp_abcdefghijklmnopqrstuvwxyz12"})
    raw = store._agent_path("a").read_text()
    assert "ghp_abcdefghijklmnop" not in raw


def test_redaction_recurses_into_nested_dicts_and_lists(project_root):
    store = AgentStateStore(str(project_root))
    store.append(
        "a",
        {
            "args": {"creds": ["ftx-llllllllllllllll0000", "safe"]},
            "tags": ["ftx-mmmmmmmmmmmmmmmm1111", "ok"],
        },
    )
    entry = _read_jsonl(store._agent_path("a"))[0]
    assert entry["args"]["creds"] == ["***REDACTED***", "safe"]
    assert entry["tags"] == ["***REDACTED***", "ok"]


def test_unmatched_strings_pass_through(project_root):
    store = AgentStateStore(str(project_root))
    store.append("a", {"safe": "this is a plain message"})
    entry = _read_jsonl(store._agent_path("a"))[0]
    assert entry["safe"] == "this is a plain message"


# ── Custom redaction patterns ────────────────────────────────────────────


def test_custom_pattern_string(project_root):
    store = AgentStateStore(
        str(project_root),
        redact_patterns=[r"INTERNAL-[A-Z0-9]{6,}"],
    )
    store.append("a", {"trace": "leak: INTERNAL-XYZ987"})
    raw = store._agent_path("a").read_text()
    assert "INTERNAL-XYZ987" not in raw


def test_custom_pattern_compiled(project_root):
    import re

    store = AgentStateStore(
        str(project_root),
        redact_patterns=[re.compile(r"\b(passw0rd|hunter2)\b", re.IGNORECASE)],
    )
    store.append("a", {"value": "Password is hunter2"})
    raw = store._agent_path("a").read_text()
    assert "hunter2" not in raw


def test_disable_default_redactions(project_root):
    store = AgentStateStore(
        str(project_root),
        use_default_redactions=False,
    )
    store.append("a", {"k": "ftx-aaaaaaaaaaaaaaaaaaaa"})
    raw = store._agent_path("a").read_text()
    # With defaults disabled and no custom patterns, the key should be
    # written as-is.
    assert "ftx-aaaaaaaaaaaaaaaaaaaa" in raw


# ── Permissions ──────────────────────────────────────────────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission test")
def test_history_file_is_0600(project_root):
    store = AgentStateStore(str(project_root))
    store.append("perm-test", {"event": "started"})
    path = store._agent_path("perm-test")
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got 0o{mode:o}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission test")
def test_subsequent_appends_keep_0600(project_root):
    store = AgentStateStore(str(project_root))
    for i in range(3):
        store.append("perm-test", {"event": f"step-{i}"})
    path = store._agent_path("perm-test")
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
