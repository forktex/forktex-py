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

"""Tests for forktex.agent.cli (basic import and structure)."""

import pytest


def test_cli_import():
    """Test that CLI module imports cleanly."""
    from forktex.agent.cli import cli, main

    assert cli is not None
    assert main is not None


def test_package_import():
    """Test that main package imports work."""
    from forktex import (
        StateManager,
        Settings,
        get_settings,
        generate_id,
        current_timestamp,
    )

    assert StateManager is not None
    assert Settings is not None
    assert get_settings is not None
    assert generate_id is not None
    assert current_timestamp is not None


def test_version():
    from forktex import __version__

    assert __version__ == "1.0.0"


class TestInitCommand:
    """Tests for the forktex init command."""

    @pytest.mark.asyncio
    async def test_init_writes_config(self, temp_dir):
        """Test that init command writes config.json."""
        from forktex.core.state import StateManager

        state = StateManager(temp_dir)
        await state.write_config(
            {
                "provider": "openai",
                "api_key": "sk-test123",
                "model": "gpt-4o",
            }
        )

        config = await state.read_config()
        assert config["provider"] == "openai"
        assert config["api_key"] == "sk-test123"
        assert config["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_init_config_roundtrip(self, temp_dir):
        """Test set/get config values."""
        from forktex.core.state import StateManager

        state = StateManager(temp_dir)
        await state.set_config_value("provider", "anthropic")
        await state.set_config_value("api_key", "sk-ant-test")

        assert await state.get_config_value("provider") == "anthropic"
        assert await state.get_config_value("api_key") == "sk-ant-test"
        assert await state.get_config_value("missing") is None
