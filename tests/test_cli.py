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

    assert __version__ == "0.5.0"


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
