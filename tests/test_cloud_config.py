"""Tests for forktex.cloud.config.CloudContext (Pydantic model)."""

import json
import pytest
from pathlib import Path

from forktex_cloud.config import CloudContext


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

    def test_load_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        ctx = CloudContext.load()
        assert ctx.controller is None

    def test_load_global(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        config_dir = tmp_path / ".forktex"
        config_dir.mkdir()
        (config_dir / "cloud.json").write_text(json.dumps({
            "controller": "http://global",
            "access_token": "tok",
            "org_id": "org-1",
        }))
        ctx = CloudContext.load()
        assert ctx.controller == "http://global"
        assert ctx.access_token == "tok"
        assert ctx.org_id == "org-1"

    def test_load_project_overrides_global(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        # Global config
        global_dir = tmp_path / ".forktex"
        global_dir.mkdir()
        (global_dir / "cloud.json").write_text(json.dumps({
            "controller": "http://global",
            "access_token": "tok",
            "current_project": "global-proj",
        }))
        # Project config
        project_root = tmp_path / "myproject"
        project_root.mkdir()
        proj_config = project_root / ".forktex"
        proj_config.mkdir()
        (proj_config / "cloud.json").write_text(json.dumps({
            "current_project": "local-proj",
            "current_server": "srv-1",
        }))
        ctx = CloudContext.load(project_root=project_root)
        assert ctx.controller == "http://global"
        assert ctx.current_project == "local-proj"
        assert ctx.current_server == "srv-1"

    def test_save_global(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        ctx = CloudContext(
            controller="http://saved",
            access_token="token-abc",
            org_id="org-x",
        )
        ctx.save_global()
        saved = json.loads((tmp_path / ".forktex" / "cloud.json").read_text())
        assert saved["controller"] == "http://saved"
        assert saved["access_token"] == "token-abc"

    def test_save_project(self, tmp_path):
        ctx = CloudContext(
            current_project="proj-1",
            current_server="srv-2",
            current_environment="staging",
        )
        ctx.save_project(tmp_path)
        saved = json.loads((tmp_path / ".forktex" / "cloud.json").read_text())
        assert saved["current_project"] == "proj-1"
        assert saved["current_server"] == "srv-2"
        assert saved["current_environment"] == "staging"
