"""Tests for intelligence config, SSE stream parsing, and API models."""

import json
import pytest
from pathlib import Path

from forktex_intelligence.config import IntelligenceSettings
from forktex.agent.intelligence.settings import (
    get_intelligence_settings,
    load_intelligence_settings,
    reset_intelligence_settings,
)
from forktex_intelligence.streams import SSEEvent, SSEEventType, parse_sse_stream
from forktex_intelligence.api import Response, StructuredResponse


# ============================================================================
# IntelligenceSettings
# ============================================================================


class TestIntelligenceSettings:
    def setup_method(self):
        reset_intelligence_settings()

    def test_defaults(self):
        s = IntelligenceSettings()
        assert s.endpoint == "https://intelligence.forktex.com/api"
        assert s.api_key == ""
        assert s.is_configured is False

    def test_configured_when_both_set(self):
        s = IntelligenceSettings(endpoint="http://localhost:8000", api_key="sk-test")
        assert s.is_configured is True

    def test_load_from_env(self, monkeypatch):
        monkeypatch.setenv("FORKTEX_INTELLIGENCE_ENDPOINT", "http://test:9000")
        monkeypatch.setenv("FORKTEX_INTELLIGENCE_API_KEY", "key-123")
        s = load_intelligence_settings()
        assert s.endpoint == "http://test:9000"
        assert s.api_key == "key-123"

    def test_load_from_project_config(self, temp_dir):
        config_dir = Path(temp_dir) / ".forktex"
        config_dir.mkdir()
        (config_dir / "intelligence.json").write_text(
            json.dumps(
                {
                    "endpoint": "http://project:8080",
                    "api_key": "proj-key",
                }
            )
        )
        s = load_intelligence_settings(project_root=temp_dir)
        assert s.endpoint == "http://project:8080"
        assert s.api_key == "proj-key"

    def test_load_from_global_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "forktex.agent.intelligence.settings.get_global_config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "intelligence.json").write_text(
            json.dumps(
                {
                    "endpoint": "http://global:7070",
                    "api_key": "global-key",
                }
            )
        )
        s = load_intelligence_settings()
        assert s.endpoint == "http://global:7070"
        assert s.api_key == "global-key"

    def test_env_overrides_project_config(self, temp_dir, monkeypatch):
        config_dir = Path(temp_dir) / ".forktex"
        config_dir.mkdir()
        (config_dir / "intelligence.json").write_text(
            json.dumps(
                {
                    "endpoint": "http://project:8080",
                    "api_key": "proj-key",
                }
            )
        )
        monkeypatch.setenv("FORKTEX_INTELLIGENCE_API_KEY", "env-key")
        s = load_intelligence_settings(project_root=temp_dir)
        assert s.endpoint == "http://project:8080"
        assert s.api_key == "env-key"

    def test_explicit_overrides_win(self, monkeypatch):
        monkeypatch.setenv("FORKTEX_INTELLIGENCE_API_KEY", "env-key")
        s = load_intelligence_settings(api_key="override-key")
        assert s.api_key == "override-key"

    def test_get_intelligence_settings_cached(self):
        reset_intelligence_settings()
        s1 = get_intelligence_settings(api_key="k1")
        s2 = get_intelligence_settings()
        assert s1 is s2

    def test_save_global(self, tmp_path, monkeypatch):
        from forktex.agent.intelligence.settings import save_intelligence_global

        monkeypatch.setattr(
            "forktex.agent.intelligence.settings.get_global_config_dir",
            lambda: tmp_path,
        )
        s = IntelligenceSettings(endpoint="http://test", api_key="abc")
        save_intelligence_global(s)
        saved = json.loads((tmp_path / "intelligence.json").read_text())
        assert saved["endpoint"] == "http://test"
        assert saved["api_key"] == "abc"

    def test_save_project(self, temp_dir):
        from forktex.agent.intelligence.settings import save_intelligence_project

        s = IntelligenceSettings(endpoint="http://proj", api_key="xyz")
        save_intelligence_project(s, temp_dir)
        saved = json.loads(
            (Path(temp_dir) / ".forktex" / "intelligence.json").read_text()
        )
        assert saved["endpoint"] == "http://proj"
        assert saved["api_key"] == "xyz"


# ============================================================================
# SSE Stream Parsing
# ============================================================================


async def _lines_from(*strings: str):
    """Helper: yield encoded lines."""
    for s in strings:
        yield s.encode("utf-8")


class TestSSEParsing:
    @pytest.mark.asyncio
    async def test_delta_event(self):
        lines = _lines_from(
            "event: delta\n",
            'data: {"text": "Hello"}\n',
            "\n",
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 1
        assert events[0].event == SSEEventType.DELTA
        assert events[0].delta_text == "Hello"

    @pytest.mark.asyncio
    async def test_usage_event(self):
        lines = _lines_from(
            "event: usage\n",
            'data: {"input_tokens": 10, "output_tokens": 20}\n',
            "\n",
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 1
        assert events[0].event == SSEEventType.USAGE
        assert events[0].input_tokens == 10
        assert events[0].output_tokens == 20

    @pytest.mark.asyncio
    async def test_error_event(self):
        lines = _lines_from(
            "event: error\n",
            'data: {"message": "rate limited"}\n',
            "\n",
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 1
        assert events[0].event == SSEEventType.ERROR
        assert events[0].error_message == "rate limited"

    @pytest.mark.asyncio
    async def test_done_event(self):
        lines = _lines_from(
            "event: done\n",
            "data: {}\n",
            "\n",
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 1
        assert events[0].event == SSEEventType.DONE

    @pytest.mark.asyncio
    async def test_tool_result_needed_event(self):
        lines = _lines_from(
            "event: tool_result_needed\n",
            'data: {"name": "read_file", "call_id": "abc123", "arguments": {"path": "test.py"}}\n',
            "\n",
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 1
        assert events[0].event == SSEEventType.TOOL_RESULT_NEEDED
        assert events[0].tool_name == "read_file"
        assert events[0].tool_call_id == "abc123"
        assert events[0].tool_arguments == {"path": "test.py"}

    @pytest.mark.asyncio
    async def test_multiple_events(self):
        lines = _lines_from(
            "event: delta\n",
            'data: {"text": "Hi"}\n',
            "\n",
            "event: delta\n",
            'data: {"text": " there"}\n',
            "\n",
            "event: done\n",
            "data: {}\n",
            "\n",
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 3
        assert events[0].delta_text == "Hi"
        assert events[1].delta_text == " there"
        assert events[2].event == SSEEventType.DONE

    @pytest.mark.asyncio
    async def test_comments_ignored(self):
        lines = _lines_from(
            ": keep-alive\n",
            "event: delta\n",
            'data: {"text": "ok"}\n',
            "\n",
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 1
        assert events[0].delta_text == "ok"

    @pytest.mark.asyncio
    async def test_trailing_event_without_blank_line(self):
        lines = _lines_from(
            "event: delta\n",
            'data: {"text": "trailing"}\n',
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 1
        assert events[0].delta_text == "trailing"

    @pytest.mark.asyncio
    async def test_unknown_event_type_defaults_to_delta(self):
        lines = _lines_from(
            "event: custom_unknown\n",
            'data: {"text": "fallback"}\n',
            "\n",
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 1
        assert events[0].event == SSEEventType.DELTA

    @pytest.mark.asyncio
    async def test_non_json_data(self):
        lines = _lines_from(
            "event: delta\n",
            "data: plain text data\n",
            "\n",
        )
        events = [e async for e in parse_sse_stream(lines)]
        assert len(events) == 1
        assert events[0].data == {"text": "plain text data"}


# ============================================================================
# Response / StructuredResponse models
# ============================================================================


class TestResponseModel:
    def test_basic(self):
        r = Response(text="hello")
        assert r.text == "hello"
        assert r.total_tokens == 0
        assert str(r) == "hello"

    def test_with_tokens(self):
        r = Response(text="hi", input_tokens=10, output_tokens=5)
        assert r.total_tokens == 15

    def test_repr_truncates(self):
        r = Response(text="x" * 200)
        assert "..." in repr(r)
        assert len(repr(r)) < 200

    def test_serialisation(self):
        r = Response(text="test", model="gpt-4", input_tokens=1, output_tokens=2)
        d = r.model_dump()
        assert d["text"] == "test"
        assert d["model"] == "gpt-4"
        r2 = Response.model_validate(d)
        assert r2.text == "test"


class TestStructuredResponseModel:
    def test_basic(self):
        r = StructuredResponse(parsed={"name": "John", "age": 30})
        assert r["name"] == "John"
        assert r.get("age") == 30
        assert r.get("missing", "default") == "default"

    def test_total_tokens(self):
        r = StructuredResponse(parsed={}, input_tokens=5, output_tokens=10)
        assert r.total_tokens == 15

    def test_serialisation(self):
        r = StructuredResponse(parsed={"key": "val"}, text="raw", model="m")
        d = r.model_dump()
        r2 = StructuredResponse.model_validate(d)
        assert r2.parsed == {"key": "val"}


# ============================================================================
# SSEEvent model
# ============================================================================


class TestSSEEventModel:
    def test_serialisation(self):
        e = SSEEvent(event=SSEEventType.DELTA, data={"text": "hi"})
        d = e.model_dump()
        assert d["event"] == "delta"
        e2 = SSEEvent.model_validate(d)
        assert e2.delta_text == "hi"
