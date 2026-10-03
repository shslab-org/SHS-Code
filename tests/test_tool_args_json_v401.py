"""v4.0.1 regression: tool-call arguments must ALWAYS serialize as valid JSON.

Live Agnes finding (mission §10 Test A / §11): the agent's history echoed
an assistant tool_call with empty ("") or malformed arguments — the strict
provider rejected the ENTIRE next request with
``400 Assistant tool call … arguments must be valid JSON`` and the run
died as a hard error. Two fixes pinned here:
  1. Message.to_dict() normalizes arguments via _safe_tool_args.
  2. UniversalClient streaming accumulator defaults empty args to "{}".
"""
from __future__ import annotations

import json

import pytest


class TestSafeToolArgs:
    def test_empty_becomes_object(self):
        from app.schema import _safe_tool_args
        assert _safe_tool_args("") == "{}"
        assert _safe_tool_args(None) == "{}"
        assert _safe_tool_args("   ") == "{}"

    def test_valid_json_passes_through(self):
        from app.schema import _safe_tool_args
        assert _safe_tool_args('{"command": "ls"}') == '{"command": "ls"}'
        assert _safe_tool_args("{}") == "{}"

    def test_malformed_becomes_object_or_repaired(self):
        from app.schema import _safe_tool_args
        out = _safe_tool_args('{"command": "ls",}')   # trailing comma
        # either repaired to valid JSON or normalized to {}
        json.loads(out)
        assert out.startswith("{")

    def test_message_to_dict_never_emits_invalid_json(self):
        from app.schema import Message, ToolCall, Function
        m = Message.assistant(
            content="calling",
            tool_calls=[ToolCall(
                id="tc-1",
                function=Function(name="terminate", arguments=""))])
        d = m.to_dict()
        args = d["tool_calls"][0]["function"]["arguments"]
        json.loads(args)   # MUST be valid JSON — no exception

    def test_history_roundtrip_is_provider_safe(self):
        """A whole conversation history with sloppy tool args must
        re-serialize with valid JSON everywhere."""
        from app.schema import Message, ToolCall, Function
        msgs = [
            Message.user("do the thing"),
            Message.assistant(
                content=None,
                tool_calls=[ToolCall(
                    id="tc-1",
                    function=Function(name="bash", arguments=""))]),
            Message.tool(content="ok", tool_call_id="tc-1", name="bash"),
            Message.assistant(
                tool_calls=[ToolCall(
                    id="tc-2",
                    function=Function(name="terminate",
                                      arguments='{"reason": "done"}'))]),
        ]
        for m in msgs:
            d = m.to_dict()
            for tc in d.get("tool_calls") or []:
                json.loads(tc["function"]["arguments"])


class TestStreamingAccumulatorEmptyArgs:
    @pytest.mark.asyncio
    async def test_streaming_tool_call_without_args_gets_object(self):
        """A streamed tool_call that carries NO argument fragments must end
        with arguments='{}', not ''."""
        from app.llm.llm import UniversalClient
        from tests.test_streaming_v401 import _SSEScenario, _make_chunk, _run_sse_server
        scenario = _SSEScenario([
            _make_chunk({"tool_calls": [{"index": 0, "id": "call-9",
                                         "type": "function",
                                         "function": {"name": "terminate"}}]}),
            _make_chunk({}, finish="tool_calls"),
        ])
        base, runner, _ = await _run_sse_server(scenario)
        try:
            client = UniversalClient(base, "sk-test", "test-model")
            data = await client.chat(
                [{"role": "user", "content": "stop"}],
                tools=[{"type": "function", "function": {"name": "terminate",
                                                         "parameters": {}}}],
                on_delta=lambda s: None)
            args = data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
            assert args == "{}"
            json.loads(args)
            await client.cleanup()
        finally:
            await runner.cleanup()
