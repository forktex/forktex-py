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

"""Polish-tier tests for the bare ``forktex`` REPL.

Covers:
- Persistent FileHistory wiring (A1) — file path lands under
  ``<global_config_dir>/repl_history``.
- ``/exit`` ↔ ``/quit`` equivalence (A2).
- Stream-error classifier verdicts (A4).

The TTY-recovery polish (A3) and the menu login-cancel rendering (A5)
are wired but exercised manually per the plan's verification steps.
"""

from __future__ import annotations

import asyncio

import httpx

import forktex.fsd  # noqa: F401  warm-up; see test_manifest_overlay rationale

from forktex.agent.root_loop._stream_errors import classify
from forktex.agent.root_loop.menu import _repl_history
from forktex.agent.root_loop.slash import SLASH_COMMANDS


# ── A1: FileHistory at ~/.forktex/repl_history ────────────────────────────


def test_repl_history_creates_file_under_global_config_dir(tmp_path, monkeypatch):
    """When the user has a writable global config dir, _repl_history
    returns a FileHistory whose path lives under that dir."""
    from prompt_toolkit.history import FileHistory

    fake_dir = tmp_path / "global_forktex"
    fake_dir.mkdir()

    monkeypatch.setattr("forktex.core.paths.get_global_config_dir", lambda: fake_dir)
    monkeypatch.setattr("forktex.core.paths.ensure_global_config_dir", lambda: fake_dir)

    h = _repl_history()
    assert isinstance(h, FileHistory)
    assert h.filename == str(fake_dir / "repl_history")


def test_repl_history_falls_back_to_in_memory_on_oserror(monkeypatch):
    """If the global config dir is not writable, _repl_history degrades
    gracefully to in-memory storage so the REPL still boots."""
    from prompt_toolkit.history import InMemoryHistory

    def boom():
        raise OSError("read-only home")

    monkeypatch.setattr("forktex.core.paths.ensure_global_config_dir", boom)

    h = _repl_history()
    assert isinstance(h, InMemoryHistory)


# ── A2: /exit aliases /quit ──────────────────────────────────────────────


def test_slash_exit_is_registered():
    assert "/exit" in SLASH_COMMANDS


def test_slash_exit_handler_matches_quit():
    """`/exit` should dispatch to the same handler that backs `/quit`."""
    assert SLASH_COMMANDS["/exit"].handler is SLASH_COMMANDS["/quit"].handler


# ── A4: stream-error classifier ───────────────────────────────────────────


def test_classify_httpx_remote_protocol_is_transient():
    v = classify(httpx.RemoteProtocolError("EOF"))
    assert v.verdict == "transient"
    assert "again" in v.hint


def test_classify_httpx_read_timeout_is_transient():
    v = classify(httpx.ReadTimeout("slow"))
    assert v.verdict == "transient"


def test_classify_asyncio_timeout_is_transient():
    v = classify(asyncio.TimeoutError())
    assert v.verdict == "transient"


def test_classify_connection_error_is_transient():
    v = classify(ConnectionError("network down"))
    assert v.verdict == "transient"


def test_classify_intelligence_api_401_suggests_connect():
    """A 401/403 response from the SDK should land in `fatal` and tell
    the user to /connect intelligence."""
    from forktex_intelligence.client.client import IntelligenceAPIError

    exc = IntelligenceAPIError(401, "Unauthorised")
    v = classify(exc)
    assert v.verdict == "fatal"
    assert "/connect intelligence" in v.hint


def test_classify_intelligence_api_429_is_transient():
    """Rate-limiting / 408 / 429 should be transient — the user should
    just retry."""
    from forktex_intelligence.client.client import IntelligenceAPIError

    exc = IntelligenceAPIError(429, "Too many")
    v = classify(exc)
    assert v.verdict == "transient"


def test_classify_unknown_exception_is_unknown():
    v = classify(RuntimeError("surprise"))
    assert v.verdict == "unknown"
    assert "FORKTEX_DEBUG" in v.hint


def test_verdict_markup_contains_label():
    v_t = classify(httpx.ReadTimeout("x"))
    v_f = classify(RuntimeError("x"))  # unknown, not fatal — but exercises markup
    assert "stream interrupted" in v_t.markup
    assert "stream error" in v_f.markup
