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

"""Tests for CloudContext (data model) and cloud settings persistence."""

import json
import pytest

from forktex_cloud.config import CloudContext
from forktex.agent.cloud.settings import (
    load_cloud_context,
    save_cloud_context_global,
    save_cloud_context_project,
)


class TestCloudContext:
    def test_defaults(self):
        ctx = CloudContext()
        assert ctx.controller is None
        assert ctx.is_connected is False
        assert ctx.project_keys == {}

    def test_is_connected_with_token(self):
        ctx = CloudContext(controller="http://ctrl", access_token="tok")
        assert ctx.is_connected is True

    def test_is_connected_with_account_key(self):
        ctx = CloudContext(controller="http://ctrl", account_key="key")
        assert ctx.is_connected is True

    def test_not_connected_without_auth(self):
        ctx = CloudContext(controller="http://ctrl")
        assert ctx.is_connected is False

    def test_require_connection_raises_no_controller(self):
        ctx = CloudContext()
        with pytest.raises(RuntimeError, match="No cloud controller"):
            ctx.require_connection()

    def test_require_connection_raises_no_credentials(self):
        ctx = CloudContext(controller="http://ctrl")
        with pytest.raises(RuntimeError, match="No credentials"):
            ctx.require_connection()

    def test_require_connection_passes(self):
        ctx = CloudContext(controller="http://ctrl", access_token="tok")
        ctx.require_connection()  # should not raise

    def test_to_dict(self):
        ctx = CloudContext(controller="http://ctrl", org_id="org1")
        d = ctx.to_dict()
        assert d["controller"] == "http://ctrl"
        assert d["org_id"] == "org1"
        assert d["project_keys"] == {}

    def test_model_dump(self):
        ctx = CloudContext(controller="http://ctrl", region="eu")
        d = ctx.model_dump()
        assert d["controller"] == "http://ctrl"
        assert d["region"] == "eu"


class TestCloudSettings:
    def test_load_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("forktex_cloud.paths.global_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "forktex_cloud.paths.global_cloud_file", lambda: tmp_path / "cloud.json"
        )
        ctx = load_cloud_context()
        assert ctx.controller is None

    def test_load_global(self, tmp_path, monkeypatch):
        monkeypatch.setattr("forktex_cloud.paths.global_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "forktex_cloud.paths.global_cloud_file", lambda: tmp_path / "cloud.json"
        )
        (tmp_path / "cloud.json").write_text(
            json.dumps(
                {
                    "controller": "http://global",
                    "access_token": "tok",
                    "org_id": "org-1",
                }
            )
        )
        ctx = load_cloud_context()
        assert ctx.controller == "http://global"
        assert ctx.access_token == "tok"
        assert ctx.org_id == "org-1"

    def test_load_project_overrides_global(self, tmp_path, monkeypatch):
        monkeypatch.setattr("forktex_cloud.paths.global_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "forktex_cloud.paths.global_cloud_file", lambda: tmp_path / "cloud.json"
        )
        # Global config
        (tmp_path / "cloud.json").write_text(
            json.dumps(
                {
                    "controller": "http://global",
                    "access_token": "tok",
                    "current_project": "global-proj",
                }
            )
        )
        # Project config
        project_root = tmp_path / "myproject"
        project_root.mkdir()
        proj_config = project_root / ".forktex"
        proj_config.mkdir()
        (proj_config / "cloud.json").write_text(
            json.dumps(
                {
                    "current_project": "local-proj",
                    "current_server": "srv-1",
                }
            )
        )
        ctx = load_cloud_context(project_root=project_root)
        assert ctx.controller == "http://global"
        assert ctx.current_project == "local-proj"
        assert ctx.current_server == "srv-1"

    def test_save_global(self, tmp_path, monkeypatch):
        monkeypatch.setattr("forktex_cloud.paths.global_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "forktex_cloud.paths.global_cloud_file", lambda: tmp_path / "cloud.json"
        )
        ctx = CloudContext(
            controller="http://saved",
            access_token="token-abc",
            org_id="org-x",
        )
        save_cloud_context_global(ctx)
        saved = json.loads((tmp_path / "cloud.json").read_text())
        assert saved["controller"] == "http://saved"
        assert saved["access_token"] == "token-abc"

    def test_save_project(self, tmp_path):
        ctx = CloudContext(
            current_project="proj-1",
            current_server="srv-2",
            current_environment="staging",
        )
        save_cloud_context_project(ctx, tmp_path)
        saved = json.loads((tmp_path / ".forktex" / "cloud.json").read_text())
        assert saved["current_project"] == "proj-1"
        assert saved["current_server"] == "srv-2"
        assert saved["current_environment"] == "staging"
