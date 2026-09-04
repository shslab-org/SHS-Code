"""SHS Code v3.0 — 100% UPGRADE REGRESSION SUITE.

Every fix in this file maps to a measured weakness from the live forensic
benchmark (Compare/):

  1. Adaptive rate limiter      — task-22 death: 429s without Retry-After
                                  refilled the 40-RPM window every ~1.5s,
                                  every retry died on the next 429.
  2. Rate-limit retry budget    — the 8-retry generic budget treated
                                  capacity events like errors and gave up.
  3. classify_request           — task-06: "2+2?" paid a planner LLM call.
  4. Chat fast-path             — same: planner call skipped, review /
                                  self-check injections skipped for chat.
  5. Conversation continuity    — task-01: turn-2 of a one-shot session
                                  started EMPTY and answered "0"; task-25:
                                  context did not survive a model switch.
  6. Final-answer persistence   — the assistant side of the dialogue was
                                  never written to the session DB.
  7. MCP tools in main agent    — task-18: tools existed only in the
                                  separate MCPAgent, never in SHSCode.
  8. Multi-agent triage         — 55/250: 4-role pipeline on trivial Q&A,
                                  4x request amplification, 28 timeouts.
  9. Role validation leniency   — PM 5-word reject + Engineer format reject
                                  killed real live runs.
 10. Tool-error request waste   — inline LLM self-correction doubled
                                  requests on every failed tool call.
"""
import asyncio
import json
import os
import time

import pytest

os.environ.setdefault("APP_ENV", "test")

from app.llm.rate_limiter import RollingWindowRateLimiter
from app.agent.base import classify_request


# ═════════════════════════════════════════════════════════════════════════════
# 1. Adaptive rate limiter
# ═════════════════════════════════════════════════════════════════════════════

class TestAdaptiveRateLimiter:

    def test_429_without_retry_after_grows_penalty(self):
        """Three consecutive 429s without Retry-After must produce an
        exponentially growing wait — NOT the ~0-1.5s window refill that
        walked the retry loop into the next 429."""
        lim = RollingWindowRateLimiter("nim", rpm=40)
        base = 1000.0
        lim.on_rate_limit_response(None, now=base)
        w1 = lim.wait_seconds(now=base + 0.1)
        lim.on_rate_limit_response(None, now=base + 0.2)
        w2 = lim.wait_seconds(now=base + 0.3)
        lim.on_rate_limit_response(None, now=base + 0.4)
        w3 = lim.wait_seconds(now=base + 0.5)

        assert w1 >= 1.5          # first penalty: ~2s (minus 0.1s elapsed)
        assert w2 >= 3.5          # second: ~4s
        assert w3 >= 7.5          # third: ~8s
        assert w3 > w2 > w1       # strictly growing

    def test_429_penalty_caps_at_max(self):
        lim = RollingWindowRateLimiter("nim", rpm=40)
        base = 2000.0
        for _ in range(12):
            lim.on_rate_limit_response(None, now=base)
        w = lim.wait_seconds(now=base + 0.1)
        assert w <= RollingWindowRateLimiter.ADAPTIVE_MAX_BLOCK_S + 0.01

    def test_success_decays_pressure(self):
        """After successes the limiter must converge back toward the
        configured rate — no permanent throttle."""
        lim = RollingWindowRateLimiter("nim", rpm=40)
        base = 3000.0
        for _ in range(4):
            lim.on_rate_limit_response(None, now=base)
        hot = lim.wait_seconds(now=base + 0.1)
        for _ in range(8):
            lim.on_success()
        cool = lim.wait_seconds(now=base + 0.2)
        assert cool < hot
        assert lim._pressure < 4

    def test_retry_after_still_honored(self):
        lim = RollingWindowRateLimiter("nim", rpm=40)
        lim.on_rate_limit_response(20.0, now=1000.0)
        assert abs(lim.wait_seconds(now=1000.0 + 1.0) - 19.0) < 0.01

    def test_unlimited_rpm_adaptive_block_works(self):
        """rpm=0 limiters still respect adaptive pressure — NIM endpoints
        with no configured RPM must not spin on 429 storms."""
        lim = RollingWindowRateLimiter("x", rpm=0)
        lim.on_rate_limit_response(None, now=1000.0)
        w = lim.wait_seconds(now=1000.0 + 0.5)
        assert w >= 1.5

    def test_stats_expose_pressure(self):
        lim = RollingWindowRateLimiter("nim", rpm=40)
        lim.on_rate_limit_response(None, now=1000.0)
        s = lim.stats()
        assert s["total_429"] == 1
        assert s["adaptive_pressure"] >= 1


# ═════════════════════════════════════════════════════════════════════════════
# 2. LLM retry — dedicated rate-limit budget
# ═════════════════════════════════════════════════════════════════════════════

class FlakyBackend:
    """Fails N times with RateLimitError (no Retry-After), then succeeds."""

    def __init__(self, failures: int):
        self.failures = failures
        self.model = "flaky-model"
        self.calls = 0

    async def chat(self, messages, tools=None, **kw):
        self.calls += 1
        if self.calls <= self.failures:
            from app.exceptions import RateLimitError
            raise RateLimitError("Rate limited (flaky)")
        return {"choices": [{"message": {"role": "assistant",
                                         "content": "OK after retries"}}]}

    async def cleanup(self):
        pass


class _LLMPatch:
    """Minimal LLM harness: runs _call_with_retry on a patched instance."""
    pass


class TestRateLimitRetryBudget:

    @staticmethod
    def _make_llm(backend):
        from app.llm import llm as llm_mod
        from app.llm.llm import LLM
        l = object.__new__(LLM)
        l._backend = backend
        l._pool = None
        l._max_retries = 8
        l._provider = "flaky"
        l._model = "flaky-model"
        l._base_url = ""
        l.token_budget = llm_mod.TokenBudget(max_tokens=0)
        l._limiter = lambda: None
        return l, llm_mod

    @staticmethod
    def _fast_sleep(monkeypatch, llm_mod):
        """Replace llm.py's asyncio reference with a no-sleep shim so
        backoff waits don't slow the test (real waits are covered by the
        rate-limiter unit tests above)."""
        import asyncio as _real_aio

        class _FastAio:
            TimeoutError = _real_aio.TimeoutError
            @staticmethod
            async def sleep(_s):
                return None

        monkeypatch.setattr(llm_mod, "asyncio", _FastAio)

    def test_survives_12_429s(self, monkeypatch):
        """Old code: 8 generic retries → dead. New: 12 consecutive 429s
        must still complete the request."""
        l, llm_mod = self._make_llm(FlakyBackend(12))
        self._fast_sleep(monkeypatch, llm_mod)

        data = asyncio.run(l._call_with_retry(
            [{"role": "user", "content": "hi"}], tools=None))
        assert data["choices"][0]["message"]["content"] == "OK after retries"
        assert l._backend.calls == 13

    def test_non_rate_errors_fail_fast(self, monkeypatch):
        """Non-transient errors still fail fast — the generous budget is
        ONLY for capacity events."""
        class BadBackend(FlakyBackend):
            async def chat(self, messages, tools=None, **kw):
                self.calls += 1
                raise ValueError("400 invalid request")

        l, llm_mod = self._make_llm(BadBackend(0))
        self._fast_sleep(monkeypatch, llm_mod)

        with pytest.raises(ValueError):
            asyncio.run(l._call_with_retry(
                [{"role": "user", "content": "hi"}], tools=None))


# ═════════════════════════════════════════════════════════════════════════════
# 3. classify_request
# ═════════════════════════════════════════════════════════════════════════════

class TestClassifyRequest:

    @pytest.mark.parametrize("prompt", [
        "2+2?", "what is 2+2", "hi", "hello there!", "who are you?",
        "remember the number 7", "what was the number I told you?",
        "thanks", "the weather is nice today", "what is the capital of France?",
    ])
    def test_chat(self, prompt):
        assert classify_request(prompt) == "chat"

    @pytest.mark.parametrize("prompt", [
        "Create a file called hello.py that prints hi",
        "fix the bug in calc.py",
        "Add a function slugify to textproc.py with tests",
        "write a README.md for this repo",
        "run the test suite and report failures",
        "Create a private GitHub repo, push, and open an issue",
    ])
    def test_task(self, prompt):
        assert classify_request(prompt) == "task"


# ═════════════════════════════════════════════════════════════════════════════
# 4-6. Chat fast-path + conversation continuity + answer persistence
# ═════════════════════════════════════════════════════════════════════════════

class CountingLLM:
    """Scripted LLM that counts every ask/ask_tool call."""

    def __init__(self, replies=None):
        from app.llm.token_tracker import TokenBudget
        self.token_budget = TokenBudget(max_tokens=0)
        self.calls = 0
        self.replies = list(replies or [])

    def _next(self):
        from app.schema import Message, Role
        self.calls += 1
        if self.replies:
            return Message(role=Role.ASSISTANT, content=str(self.replies.pop(0)))
        return Message(role=Role.ASSISTANT, content="Task complete.")

    async def ask(self, messages, **kw):
        return self._next()

    async def ask_tool(self, messages, tools=None, **kw):
        return self._next()

    def backend_info(self):
        return {"provider": "counting", "model": "count-model",
                "backend": "mock", "base_url": None}

    async def switch(self, provider=None, model=None, **kw):
        return {"provider": provider or "counting",
                "model": model or "count-model"}

    async def cleanup_backend(self):
        pass


class TestChatFastPath:

    def test_chat_mode_flag_and_no_planner_call(self, tmp_path, monkeypatch):
        """A chat prompt must set _chat_mode and NEVER call the LLM planner
        (heuristic plan only) — one LLM request total."""
        monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
        from app.config import Config
        Config.reset()
        from app.agent.shscode import SHSCode

        agent = SHSCode()
        llm = CountingLLM(replies=["4"])
        agent.llm = llm
        # isolate DB + journal
        from app.db.session import SessionDB
        agent.db = SessionDB(db_path=tmp_path / "chat.db")
        agent.journal = None

        asyncio.run(agent.run("2+2?"))

        assert agent._chat_mode is True
        # exactly ONE llm request: the answer (no planner call)
        assert llm.calls == 1

    def test_task_mode_still_full(self, tmp_path, monkeypatch):
        """A real task keeps the planner path (planner + loop calls)."""
        monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
        from app.config import Config
        Config.reset()
        from app.agent.shscode import SHSCode

        agent = SHSCode()
        llm = CountingLLM(replies=[
            '{"steps": [{"title": "do the work"}]}',   # planner JSON
            "Task complete.",
        ])
        agent.llm = llm
        from app.db.session import SessionDB
        from app.state import Journal
        agent.db = SessionDB(db_path=tmp_path / "task.db")
        # a real journal: the LLM planner call is gated on journal+task id
        agent.journal = Journal(db_path=tmp_path / "journal.db")

        asyncio.run(agent.run("Create hello.py that prints hi"))

        assert agent._chat_mode is False
        assert llm.calls >= 2   # planner + at least one loop turn

    def test_chat_skips_self_check_injections(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
        from app.config import Config
        Config.reset()
        from app.agent.shscode import SHSCode
        from app.schema import Role

        agent = SHSCode()
        llm = CountingLLM(replies=["no", "still chatting", "4"])
        agent.llm = llm
        agent._max_steps = 6
        from app.db.session import SessionDB
        agent.db = SessionDB(db_path=tmp_path / "chat2.db")
        agent.journal = None

        asyncio.run(agent.run("what is 2+2?"))
        injected = [m.content for m in agent.memory.messages
                    if m.role == Role.USER and m.content
                    and "SELF-CHECK" in m.content]
        assert injected == []   # chat must not pay for self-check machinery


class TestConversationContinuity:

    def test_history_injected_on_continued_session(self, tmp_path, monkeypatch):
        """Turn 2 of a one-shot session must start with the prior dialogue
        in context (benchmark task-01: answered '0' instead of '7')."""
        monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
        from app.config import Config
        Config.reset()
        from app.agent.shscode import SHSCode
        from app.db.session import SessionDB

        db = SessionDB(db_path=tmp_path / "cont.db")
        sid = asyncio.run(db.create_session("remember numbers"))

        # Turn 1: user teaches a fact, assistant acknowledges.
        a1 = SHSCode(session_id=sid)
        a1.db = db
        a1.journal = None
        a1.llm = CountingLLM(replies=["Got it — the number is 7."])
        r1 = asyncio.run(a1.run("Remember the number 7"))
        assert "7" in r1

        # Turn 2: fresh agent instance, SAME session.
        a2 = SHSCode(session_id=sid)
        a2.db = db
        a2.journal = None
        a2.llm = CountingLLM(replies=["7"])
        history = " | ".join(m.content for m in a2.memory.messages)
        asyncio.run(a2.run("what was the number?"))

        # The restored history must contain the turn-1 exchange.
        restored = [m.content for m in a2.memory.messages
                    if m.content and "CONVERSATION HISTORY" in m.content]
        assert restored, "conversation history must be injected"
        assert "7" in restored[0]
        db.close()

    def test_final_answer_persisted_once(self, tmp_path, monkeypatch):
        """The final answer must land in the session DB exactly once —
        recall on the next run depends on it."""
        monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
        from app.config import Config
        Config.reset()
        from app.agent.shscode import SHSCode
        from app.db.session import SessionDB

        db = SessionDB(db_path=tmp_path / "ans.db")
        sid = asyncio.run(db.create_session("answer persist"))

        agent = SHSCode(session_id=sid)
        agent.db = db
        agent.journal = None
        agent.llm = CountingLLM(replies=["The port is 7331."])
        asyncio.run(agent.run("remember port 7331"))

        msgs = asyncio.run(db.get_messages(sid))
        assistants = [m for m in msgs if m["role"] == "assistant"]
        assert assistants, "assistant answer must be persisted"
        assert "7331" in assistants[-1]["content"]
        # no verbatim duplicates of the final answer
        finals = [m for m in assistants
                  if m["content"].strip() == "The port is 7331."]
        assert len(finals) == 1
        db.close()

    def test_get_messages_and_latest_session(self, tmp_path):
        from app.db.session import SessionDB
        db = SessionDB(db_path=tmp_path / "api.db")
        s1 = asyncio.run(db.create_session("first"))
        asyncio.run(db.log_message(s1, "user", "hello"))
        asyncio.run(db.log_message(s1, "assistant", "hi there"))
        asyncio.run(db.log_message(s1, "system", "bookkeeping"))

        msgs = asyncio.run(db.get_messages(s1))
        roles = {m["role"] for m in msgs}
        assert roles == {"user", "assistant"}     # system rows excluded
        assert msgs[0]["role"] == "user"          # oldest first

        s2 = asyncio.run(db.create_session("second"))
        latest = asyncio.run(db.latest_session())
        assert latest is not None
        assert latest["id"] == s2
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# 7. MCP tools in the main agent
# ═════════════════════════════════════════════════════════════════════════════

class FakeMCPTool:
    def __init__(self, name):
        self.name = name
        self.description = f"fake tool {name}"

    def to_openai_schema(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": {}}}}


class FakeMCPClient:
    tools = [FakeMCPTool("mcp_get_time"), FakeMCPTool("mcp_lookup")]
    next_fail = False

    def __init__(self, name=None, transport=None, command=None,
                 args=None, url=None, **kwargs):
        self.name = name

    async def connect(self):
        if FakeMCPClient.next_fail:
            raise RuntimeError("server down")
        return list(FakeMCPClient.tools)

    async def disconnect(self):
        pass


class TestMCPInMainAgent:

    def test_tools_merged_into_main_agent(self, tmp_path, monkeypatch):
        """SHSCode must surface configured MCP-server tools in its own
        ToolCollection (benchmark task-18: MCP-UNAVAILABLE fallback)."""
        monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
        from app.config import Config
        Config.reset()
        from app.agent.shscode import SHSCode

        class Srv:
            name = "bench"
            transport = "stdio"
            command = "python"
            args = []
            url = None

        cfg = Config.get()
        # mcp_servers is a read-only property — patch it on the CLASS so
        # monkeypatch restores the original afterwards.
        monkeypatch.setattr(
            type(cfg), "mcp_servers", property(lambda self: [Srv()]))

        import app.mcp.client as mcp_mod
        monkeypatch.setattr(mcp_mod, "MCPClient", FakeMCPClient)

        agent = SHSCode()
        added = asyncio.run(agent._load_mcp_tools())
        assert added == 2
        assert agent.tools.get("mcp_get_time") is not None
        assert agent.tools.get("mcp_lookup") is not None
        # selector rebuilt over the merged toolset
        assert "mcp_get_time" in agent._selector._tool_names

    def test_dead_server_is_non_fatal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
        from app.config import Config
        Config.reset()
        from app.agent.shscode import SHSCode

        class Srv:
            name = "dead"
            transport = "stdio"
            command = "python"
            args = []
            url = None

        cfg = Config.get()
        monkeypatch.setattr(
            type(cfg), "mcp_servers", property(lambda self: [Srv()]))
        import app.mcp.client as mcp_mod
        monkeypatch.setattr(mcp_mod, "MCPClient", FakeMCPClient)
        FakeMCPClient.next_fail = True
        try:
            agent = SHSCode()
            added = asyncio.run(agent._load_mcp_tools())
            assert added == 0
        finally:
            FakeMCPClient.next_fail = False


# ═════════════════════════════════════════════════════════════════════════════
# 8-9. Multi-agent triage + lenient role validation
# ═════════════════════════════════════════════════════════════════════════════

class TestMultiAgentTriage:

    def test_triage_simple_small_complex(self):
        from app.agent.orchestrator import _triage
        assert _triage("2+2?") == "simple"
        assert _triage("hello") == "simple"
        assert _triage("Create hello.py") == "small"
        long_goal = ("Build a complete REST API with authentication, database "
                     "models, migration scripts, integration tests, CI config, "
                     "and full documentation for the deployment process")
        assert _triage(long_goal) == "complex"

    def test_simple_goal_takes_single_agent_path(self, tmp_path, monkeypatch):
        """A trivial Q&A must NOT pay the 4-role pipeline (benchmark:
        multi-agent timed out at 240s on '2+2?')."""
        monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
        from app.config import Config
        Config.reset()
        from app.agent.orchestrator import MultiAgentOrchestrator
        from app.db.session import SessionDB

        orch = MultiAgentOrchestrator()
        # isolated DB
        orch.db = SessionDB(db_path=tmp_path / "tri.db")

        class StubAgent:
            def __init__(self, *a, **k):
                pass
            async def run(self, goal):
                return "4"
            async def cleanup(self):
                pass

        import app.agent.shscode as shs_mod
        monkeypatch.setattr(shs_mod, "SHSCode", StubAgent)

        result = asyncio.run(orch.run_pipeline("2+2?"))
        roles = [s.role_name for s in result.stages]
        assert roles == ["engineer"]        # single fast path, no PM/Arch/QA
        assert result.verdict == "approved"
        assert result.stages[0].output == "4"
        orch.db.close()

    def test_pm_accepts_short_goals(self):
        from app.agent.roles.product_manager import ProductManagerRole
        from app.agent.roles.base_role import RoleMessageBus
        role = ProductManagerRole(RoleMessageBus())
        ok, reason = role.validate_input("2+2?")
        assert ok, f"short goals must pass: {reason}"

    def test_engineer_accepts_any_design(self):
        from app.agent.roles.engineer import EngineerRole
        from app.agent.roles.base_role import RoleMessageBus
        role = EngineerRole(RoleMessageBus())
        ok, reason = role.validate_input("Some free-form design without markers")
        assert ok, f"format drift must not reject: {reason}"

    def test_architect_accepts_any_input(self):
        from app.agent.roles.architect import ArchitectRole
        from app.agent.roles.base_role import RoleMessageBus
        role = ArchitectRole(RoleMessageBus())
        ok, reason = role.validate_input("make something")
        assert ok, f"PRD-format sniff must not reject: {reason}"

    def test_empty_input_still_rejected(self):
        from app.agent.roles.product_manager import ProductManagerRole
        from app.agent.roles.engineer import EngineerRole
        from app.agent.roles.architect import ArchitectRole
        from app.agent.roles.base_role import RoleMessageBus
        bus = RoleMessageBus()
        assert ProductManagerRole(bus).validate_input("   ")[0] is False
        assert EngineerRole(bus).validate_input("")[0] is False
        assert ArchitectRole(bus).validate_input("")[0] is False


# ═════════════════════════════════════════════════════════════════════════════
# 10. Tool-error request efficiency
# ═════════════════════════════════════════════════════════════════════════════

class ToolErrLLM(CountingLLM):
    """First think emits a failing tool call; next think terminates."""

    def __init__(self):
        super().__init__()
        self.step = 0

    async def ask_tool(self, messages, tools=None, **kw):
        from app.schema import Message, Role, ToolCall, Function
        self.calls += 1
        self.step += 1
        if self.step == 1:
            tc = ToolCall(
                id="t-1", type="function",
                function=Function(
                    name="bash",
                    arguments=json.dumps({"command": "exit 7"})))
            return Message(
                role=Role.ASSISTANT, content="trying bash",
                tool_calls=[tc])
        return Message(role=Role.ASSISTANT, content="Task complete.")


class TestToolErrorEfficiency:

    def test_failed_tool_does_not_trigger_inline_llm_correction(self,
                                                                tmp_path,
                                                                monkeypatch):
        """Old code: a failing tool spawned an EXTRA inline ask_tool call
        for 'self-correction' (one extra request + rate-limit wait per
        failure). New: the error surfaces to the loop; the NEXT think
        handles it. Total calls must equal loop turns, not more."""
        monkeypatch.setenv("SHSCODE_WORKSPACE", str(tmp_path))
        from app.config import Config
        Config.reset()
        from app.agent.shscode import SHSCode
        from app.db.session import SessionDB

        agent = SHSCode()
        llm = ToolErrLLM()
        agent.llm = llm
        agent.db = SessionDB(db_path=tmp_path / "eff.db")
        agent.journal = None
        agent._max_steps = 6

        asyncio.run(agent.run("run this broken command"))

        # turn 1: failing tool call, turn 2: terminate.
        # If the inline self-correction still existed there would be 3+.
        assert llm.calls == 2
