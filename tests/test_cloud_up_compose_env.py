# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""`forktex cloud up` pins docker compose's ${VAR} interpolation to the
manifest-declared env file (metadata.local.envFile), so `make start` resolves
provider keys from the project's .env.local rather than the caller's shell.
"""

from __future__ import annotations

from types import SimpleNamespace

from forktex.agent.cloud.up import _compose_base, _resolve_env_file


def _manifest(metadata):
    return SimpleNamespace(metadata=metadata)


def test_compose_base_injects_env_file_when_present():
    cmd = _compose_base("proj", "/c/compose.yml", "/p/.env.local")
    assert cmd == [
        "docker",
        "compose",
        "--env-file",
        "/p/.env.local",
        "-p",
        "proj",
        "-f",
        "/c/compose.yml",
    ]


def test_compose_base_omits_env_file_when_absent():
    cmd = _compose_base("proj", "/c/compose.yml", None)
    assert "--env-file" not in cmd
    assert cmd == ["docker", "compose", "-p", "proj", "-f", "/c/compose.yml"]


def test_resolve_env_file_returns_existing_path(tmp_path):
    (tmp_path / ".env.local").write_text("OPENAI_API_KEY=sk-test\n")
    m = _manifest({"local": {"envFile": ".env.local"}})
    assert _resolve_env_file(m, tmp_path) == str(tmp_path / ".env.local")


def test_resolve_env_file_none_when_not_declared(tmp_path):
    m = _manifest({"environment": "local"})
    assert _resolve_env_file(m, tmp_path) is None


def test_resolve_env_file_none_when_file_missing(tmp_path):
    m = _manifest({"local": {"envFile": ".env.local"}})
    assert _resolve_env_file(m, tmp_path) is None
