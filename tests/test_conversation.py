"""Tests for Conversation and AgentResponse from agent.intelligence.agent."""

from forktex.agent.intelligence.agent import AgentResponse, Conversation


class TestConversation:
    def test_empty(self):
        c = Conversation()
        assert c.messages == []
        assert c.system is None

    def test_system_prompt(self):
        c = Conversation(system="You are a helpful assistant.")
        assert c.system == "You are a helpful assistant."
        assert c.messages == []

    def test_add_user(self):
        c = Conversation()
        c.add_user("Hello")
        assert len(c.messages) == 1
        assert c.messages[0] == {"role": "user", "content": "Hello"}

    def test_add_assistant(self):
        c = Conversation()
        c.add_assistant("Hi there")
        assert c.messages[0] == {"role": "assistant", "content": "Hi there"}

    def test_add_tool_result(self):
        c = Conversation()
        c.add_tool_result("call-1", "read_file", "file contents here")
        msg = c.messages[0]
        assert msg["role"] == "tool"
        assert msg["content"] == "file contents here"
        assert msg["tool_call_id"] == "call-1"

    def test_add_assistant_tool_calls(self):
        c = Conversation()
        tool_calls = [
            {"id": "tc-1", "name": "read_file", "arguments": {"path": "x.py"}}
        ]
        c.add_assistant_tool_calls("Let me read that file.", tool_calls)
        msg = c.messages[0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "Let me read that file."
        assert msg["tool_calls"] == tool_calls

    def test_add_assistant_tool_calls_empty_text(self):
        c = Conversation()
        c.add_assistant_tool_calls(
            "", [{"id": "tc-1", "name": "bash", "arguments": {}}]
        )
        assert c.messages[0]["content"] == ""

    def test_clear(self):
        c = Conversation(system="sys")
        c.add_user("one")
        c.add_assistant("two")
        c.clear()
        assert c.messages == []
        assert c.system == "sys"

    def test_message_order(self):
        c = Conversation()
        c.add_user("Q1")
        c.add_assistant("A1")
        c.add_user("Q2")
        c.add_tool_result("tc-1", "bash", "output")
        assert [m["role"] for m in c.messages] == ["user", "assistant", "user", "tool"]


class TestAgentResponse:
    def test_defaults(self):
        r = AgentResponse()
        assert r.text == ""
        assert r.tool_calls_made == []
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.error is None

    def test_with_data(self):
        r = AgentResponse(
            text="Done",
            tool_calls_made=[{"name": "bash"}],
            input_tokens=100,
            output_tokens=50,
        )
        assert r.text == "Done"
        assert len(r.tool_calls_made) == 1
        assert r.input_tokens == 100
        assert r.output_tokens == 50

    def test_error(self):
        r = AgentResponse(error="timeout")
        assert r.error == "timeout"
