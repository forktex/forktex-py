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

"""Tests for forktex.config."""

import json
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
        config_file.write_text(
            json.dumps(
                {
                    "debug": True,
                }
            )
        )

        settings = Settings.load(project_root=temp_dir)
        assert settings.debug is True

    def test_env_overrides_project_config(self, temp_dir, monkeypatch):
        """Environment variables take precedence over project config."""
        config_dir = Path(temp_dir) / ".forktex"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "debug": False,
                }
            )
        )

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
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "debug": True,
                }
            )
        )

        reset_settings()
        s = get_settings(project_root=temp_dir)
        assert s.debug is True
