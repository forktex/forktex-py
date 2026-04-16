"""Tests for forktex.config."""

import json
import os
import pytest
from pathlib import Path
from forktex.config import Settings, get_settings, reset_settings


class TestSettings:
    def setup_method(self):
        reset_settings()

    def test_default_settings(self):
        settings = Settings()
        assert settings.debug is False

    def test_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("FORKTEX_DEBUG", "true")

        settings = Settings.load()
        assert settings.debug is True

    def test_settings_overrides(self):
        settings = Settings.load(debug=True)
        assert settings.debug is True

    def test_get_settings_cached(self):
        reset_settings()
        s1 = get_settings(debug=True)
        s2 = get_settings()
        assert s1 is s2


class TestProjectConfig:
    def setup_method(self):
        reset_settings()

    def test_load_project_config(self, temp_dir):
        """Settings.load() reads .forktex/config.json from project root."""
        config_dir = Path(temp_dir) / ".forktex"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "debug": True,
        }))

        settings = Settings.load(project_root=temp_dir)
        assert settings.debug is True

    def test_env_overrides_project_config(self, temp_dir, monkeypatch):
        """Environment variables take precedence over project config."""
        config_dir = Path(temp_dir) / ".forktex"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({
            "debug": False,
        }))

        monkeypatch.setenv("FORKTEX_DEBUG", "true")

        settings = Settings.load(project_root=temp_dir)
        assert settings.debug is True

    def test_missing_project_config_is_fine(self, temp_dir):
        """No .forktex/config.json should not cause errors."""
        settings = Settings.load(project_root=temp_dir)
        assert settings.debug is False

    def test_get_settings_with_project_root(self, temp_dir):
        """get_settings() passes project_root through."""
        config_dir = Path(temp_dir) / ".forktex"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({
            "debug": True,
        }))

        reset_settings()
        s = get_settings(project_root=temp_dir)
        assert s.debug is True
