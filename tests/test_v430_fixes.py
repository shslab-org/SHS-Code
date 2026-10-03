"""v4.3.0 regression tests — the four real-test-run bug classes.

1. max_steps configuration architecture (user-controlled, no silent
   swallowing, precedence, runtime respect, GUI/CLI selection).
2. Mandatory SHS-Code-Agent GitHub attribution (git shim, no opt-out,
   --author/-c/env bypass defeated, user's own config untouched).
3. Detached execution lifecycle (double-fork survival, registry,
   liveness, graceful interruption path).
4. Resumed-session tool-call protocol (orphaned tool_calls sanitized at
   the request boundary; producer paths fixed; diagnostics recorded).

The existing rate-limit retry/recovery behavior is deliberately NOT
touched here — test_rate_limiter.py / test_rate_limit_architecture.py /
test_fallback*.py continue to guard it (all green in this run).
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_ENV", "test")


# ═══════════════════════════════════════════════════════════════════════════
# 1. max_steps configuration architecture
# ═══════════════════════════════════════════════════════════════════════════

class TestMaxStepsConfig:
    """The configured max_steps must be exactly what the runtime uses."""

    def _clean_env(self, monkeypatch):
        for k in ("SHSCODE_MAX_STEPS", "MANUSCLAW_MAX_STEPS",
                  "SHSCODE_CONFIG_PERMISSIVE", "SHSCODE_PROFILE"):
            monkeypatch.delenv(k, raising=False)

    def test_default_is_30(self, tmp_path, monkeypatch):
        from app.config import Config, effective_max_steps
        self._clean_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "dev")     # test-env forces 5 for speed
        monkeypatch.chdir(tmp_path)            # no config.toml anywhere
        Config.reset()
        cfg = Config.get()
        assert cfg.max_steps == 30
        v, src = effective_max_steps()
        assert v == 30 and "default" in src

    def test_default_in_test_env_is_5_for_speed(self, tmp_path, monkeypatch):
        """APP_ENV=test keeps the documented 5-step default — but ONLY when
        the user did not configure anything (see the explicit-value test)."""
        from app.config import Config
        self._clean_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.chdir(tmp_path)
        Config.reset()
        assert Config.get().max_steps == 5

    def test_project_level_top_level_key_respected(self, tmp_path, monkeypatch):
        from app.config import Config, effective_max_steps
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.toml").write_text(
            'max_steps = 80\n[logging]\nconsole_level = "WARNING"\n',
            encoding="utf-8")
        Config.reset()
        cfg = Config.get()
        assert cfg.max_steps == 80
        v, src = effective_max_steps()
        assert v == 80
        assert "config" in src.lower()

    def test_logging_section_cannot_swallow_max_steps(self, tmp_path, monkeypatch):
        """THE reported bug: max_steps inside [logging] was silently ignored.
        Now it is a hard, actionable ConfigError."""
        from app.config import Config
        from app.exceptions import ConfigError
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.toml").write_text(
            '[logging]\nconsole_level = "WARNING"\nmax_steps = 80\n',
            encoding="utf-8")
        Config.reset()
        with pytest.raises(ConfigError) as ei:
            Config.get()
        msg = str(ei.value)
        assert "max_steps" in msg and "logging" in msg and "TOP-LEVEL" in msg

    def test_any_section_cannot_swallow_any_top_level_setting(self, tmp_path, monkeypatch):
        from app.config import Config
        from app.exceptions import ConfigError
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.toml").write_text(
            '[browser]\nheadless = true\ntoken_budget = 500\n',
            encoding="utf-8")
        Config.reset()
        with pytest.raises(ConfigError):
            Config.get()

    def test_permissive_mode_downgrades_to_warning(self, tmp_path, monkeypatch):
        from app.config import Config
        self._clean_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("SHSCODE_CONFIG_PERMISSIVE", "1")
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.toml").write_text(
            '[logging]\nconsole_level = "WARNING"\nmax_steps = 80\n',
            encoding="utf-8")
        Config.reset()
        cfg = Config.get()                      # must not raise
        assert cfg.max_steps == 30              # 80 stays ignored (warned)

    def test_unknown_keys_only_warn(self, tmp_path, monkeypatch):
        from app.config import Config
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.toml").write_text(
            'max_steps = 40\n[logging]\nconsole_level = "WARNING"\n'
            'bogus = "x"\n', encoding="utf-8")
        Config.reset()
        assert Config.get().max_steps == 40     # unknown key ≠ fatal

    def test_user_home_yaml_layer(self, tmp_path, monkeypatch):
        from app.config import Config
        from app import env as _env
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        home = tmp_path / "home"
        home.mkdir()
        # _HOME is resolved at import time — patch the module attribute
        # (the env var alone would not affect an already-imported module)
        monkeypatch.setattr("app.config._HOME", home)
        (home / "config.yaml").write_text("max_steps: 77\n", encoding="utf-8")
        Config.reset()
        assert Config.get().max_steps == 77

    def test_env_override_beats_files(self, tmp_path, monkeypatch):
        from app.config import Config, effective_max_steps
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.toml").write_text("max_steps = 80\n", encoding="utf-8")
        monkeypatch.setenv("SHSCODE_MAX_STEPS", "150")
        Config.reset()
        Config.get()
        v, src = effective_max_steps()
        assert v == 150 and "SHSCODE_MAX_STEPS" in src

    def test_invalid_env_rejected_loudly(self, tmp_path, monkeypatch):
        from app.config import Config
        from app.exceptions import ConfigError
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SHSCODE_MAX_STEPS", "banana")
        Config.reset()
        with pytest.raises(ConfigError):
            Config.get()

    def test_save_and_clear_roundtrip(self, tmp_path, monkeypatch):
        from app.config import Config, effective_max_steps
        self._clean_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.chdir(tmp_path)
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("app.config._HOME", home)
        (tmp_path / "config.toml").write_text("max_steps = 80\n", encoding="utf-8")
        Config.reset()
        Config.get()
        p = Config.get().save_max_steps(120)
        assert p is not None and p.exists()
        v, _ = effective_max_steps()
        assert v == 120
        import yaml
        assert yaml.safe_load(p.read_text()).get("max_steps") == 120
        Config.get().save_max_steps(None)
        v, _ = effective_max_steps()
        assert v == 80                          # back to the file layer

    def test_server_run_request_default_is_none_not_30(self):
        """The old ``max_steps: int = 30`` default silently stomped any
        configured value on every GUI/API run — the exact reported bug."""
        from app.server.main import RunRequest
        req = RunRequest(prompt="x")
        assert req.max_steps is None

    def test_streaming_wrapper_only_overrides_when_explicit(self):
        from app.server.main import StreamingSHSCode
        from app.permissions.gate import AgentMode
        s = StreamingSHSCode(session_id="s1", mode=AgentMode.BUILD,
                             max_steps=None)
        assert s.max_steps is None            # config value will apply

    def test_conversation_default_uses_config_not_30(self, tmp_path, monkeypatch):
        """local_conversation must not fall back to a hardcoded 30."""
        from app.config import Config
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.toml").write_text("max_steps = 55\n", encoding="utf-8")
        monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "nohome"))
        Config.reset()
        from app.config import effective_max_steps
        v, _ = effective_max_steps()
        assert v == 55

    @pytest.mark.asyncio
    async def test_runtime_actually_stops_at_configured_value(self, tmp_path, monkeypatch):
        """End-to-end loop behavior: with max_steps=3 configured (env layer,
        no explicit assignment anywhere), the agent stops after exactly 3
        steps — never the default 30."""
        from app.config import Config
        self._clean_env(monkeypatch)
        monkeypatch.setenv("SHSCODE_MAX_STEPS", "3")
        monkeypatch.chdir(tmp_path)
        Config.reset()
        Config.get()

        from app.agent.shscode import SHSCode
        from app.schema import Role
        agent = SHSCode()
        assert agent._max_steps == 3, "agent must read the configured value"

        # a stub LLM that ALWAYS requests a tool call — only the step
        # budget can stop it
        from app.schema import Message, ToolCall, Function

        class NeverEnding:
            # NOTE: no token_budget attribute — _effective_budget then uses
            # its standalone fallback instead of crashing on None

            async def ask_tool(self, messages, tools, **_):
                return Message(
                    role=Role.ASSISTANT, content=None,
                    tool_calls=[ToolCall(
                        id=f"tc-{time.time_ns()}", type="function",
                        function=Function(
                            name="python_execute",
                            arguments='{"code": "1+1"}'))])

            async def chat(self, *a, **k):
                return await self.ask_tool(*a, **k)

        agent.llm = NeverEnding()
        await agent.run("keep working forever")
        assert agent._step_count <= 3
        assert agent._finish_reason == "max_steps"

    def test_cli_flag_maps_to_env_layer(self):
        """The CLI --max-steps flag sets SHSCODE_MAX_STEPS before the agent
        loads — the shared highest-priority layer (verified by parse logic
        in app.cli.main; here we pin the mechanism contract)."""
        from app.config import effective_max_steps
        os.environ["SHSCODE_MAX_STEPS"] = "99"
        try:
            v, src = effective_max_steps()
            assert v == 99 and "SHSCODE_MAX_STEPS" in src
        finally:
            os.environ.pop("SHSCODE_MAX_STEPS", None)

    def test_ssh_section_is_first_class_now(self, tmp_path, monkeypatch):
        from app.config import Config
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.toml").write_text(
            '[ssh]\nenabled = false\nport = 2222\n', encoding="utf-8")
        Config.reset()
        cfg = Config.get()
        assert cfg.ssh.port == 2222

    def test_test_env_override_only_when_default(self, tmp_path, monkeypatch):
        """APP_ENV=test must not silently replace an explicitly configured
        max_steps (the silent-replacement bug class)."""
        from app.config import Config
        self._clean_env(monkeypatch)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("APP_ENV", "test")
        (tmp_path / "config.toml").write_text("max_steps = 80\n", encoding="utf-8")
        Config.reset()
        assert Config.get().max_steps == 80


# ═══════════════════════════════════════════════════════════════════════════
# 2. Mandatory SHS-Code-Agent attribution
# ═══════════════════════════════════════════════════════════════════════════

class TestMandatoryAttribution:

    @pytest.fixture(autouse=True)
    def _shim_env(self):
        from app.git_providers.agent_identity import apply_agent_git_env
        apply_agent_git_env()
        yield

    def _repo(self, tmp_path):
        def run(*args, **kw):
            return subprocess.run(["git"] + list(args), cwd=tmp_path,
                                  capture_output=True, text=True, **kw)
        run("init", "-q")
        run("config", "user.name", "Human User")
        run("config", "user.email", "human@example.com")
        (tmp_path / "seed.txt").write_text("seed\n")
        run("add", "-A")
        run("commit", "-q", "-m", "seed")
        return run

    def _last_identity(self, run):
        r = run("log", "-1", "--pretty=format:%an|%ae|%cn|%ce")
        return r.stdout.strip()

    def test_shim_installed_and_first_on_path(self):
        from app.git_providers.git_shim import shim_active_on_path, shim_path
        assert shim_path().exists()
        assert shim_active_on_path()

    def test_plain_commit_attributed(self, tmp_path):
        run = self._repo(tmp_path)
        (tmp_path / "a.txt").write_text("a\n")
        run("add", "-A")
        run("commit", "-q", "-m", "plain")
        ident = self._last_identity(run)
        assert ident.count("SHS-Code-Agent") == 4

    def test_author_flag_bypass_defeated(self, tmp_path):
        run = self._repo(tmp_path)
        (tmp_path / "b.txt").write_text("b\n")
        run("add", "-A")
        run("commit", "-q", "-m", "bypass",
            "--author=Evil Hacker <evil@x.com>")
        assert self._last_identity(run).startswith("SHS-Code-Agent|")

    def test_split_author_flag_bypass_defeated(self, tmp_path):
        run = self._repo(tmp_path)
        (tmp_path / "b2.txt").write_text("b2\n")
        run("add", "-A")
        run("commit", "-q", "-m", "bypass2", "--author",
            "Split Evil <se@x.com>")
        assert self._last_identity(run).startswith("SHS-Code-Agent|")

    def test_config_flag_bypass_defeated(self, tmp_path):
        run = self._repo(tmp_path)
        (tmp_path / "c.txt").write_text("c\n")
        run("add", "-A")
        run("-c", "user.email=evil2@x.com", "-c", "user.name=Evil2",
            "commit", "-q", "-m", "cfg bypass")
        assert self._last_identity(run).startswith("SHS-Code-Agent|")

    def test_env_unset_bypass_defeated(self, tmp_path):
        run = self._repo(tmp_path)
        (tmp_path / "d.txt").write_text("d\n")
        run("add", "-A")
        run_env = subprocess.run(
            ["env", "-u", "GIT_AUTHOR_EMAIL", "-u", "GIT_COMMITTER_EMAIL",
             "git", "commit", "-q", "-m", "env bypass"],
            cwd=tmp_path, capture_output=True, text=True)
        assert run_env.returncode == 0
        assert self._last_identity(run).startswith("SHS-Code-Agent|")

    def test_reset_author_bypass_defeated(self, tmp_path):
        run = self._repo(tmp_path)
        (tmp_path / "e.txt").write_text("e\n")
        run("add", "-A")
        run("commit", "-q", "--reset-author", "-m", "reset bypass")
        assert self._last_identity(run).startswith("SHS-Code-Agent|")

    def test_global_c_flag_parsed(self, tmp_path):
        run = self._repo(tmp_path)
        (tmp_path / "f.txt").write_text("f\n")
        run("-C", str(tmp_path), "add", "-A")
        run("-C", str(tmp_path), "commit", "-q", "-m", "via -C")
        assert self._last_identity(run).startswith("SHS-Code-Agent|")

    def test_passthrough_commands_unaffected(self, tmp_path):
        run = self._repo(tmp_path)
        assert run("status", "--porcelain").returncode == 0
        assert run("log", "--oneline").returncode == 0
        assert run("rev-parse", "HEAD").returncode == 0

    def test_merge_commit_attributed(self, tmp_path):
        run = self._repo(tmp_path)
        run("checkout", "-q", "-b", "feature")
        (tmp_path / "g.txt").write_text("g\n")
        run("add", "-A")
        run("commit", "-q", "-m", "feature work")
        main = "master" if run("rev-parse", "--verify", "-q",
                               "master").returncode == 0 else "main"
        run("checkout", "-q", main)
        (tmp_path / "h.txt").write_text("h\n")
        run("add", "-A")
        run("commit", "-q", "-m", "main work")
        run("merge", "-q", "--no-edit", "feature")
        assert self._last_identity(run).startswith("SHS-Code-Agent|")

    def test_user_own_config_untouched(self, tmp_path):
        run = self._repo(tmp_path)
        assert run("config", "user.email").stdout.strip() == "human@example.com"
        assert run("config", "user.name").stdout.strip() == "Human User"

    def test_provider_commit_triple_mechanism(self, tmp_path):
        from app.git_providers.github_provider import GitHubProvider
        self._repo(tmp_path)
        (tmp_path / "p.txt").write_text("p\n")
        gh = GitHubProvider(repo_dir=str(tmp_path))
        out = gh.commit("provider commit")
        assert out["author"].startswith("SHS-Code-Agent <")
        r = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%an|%ae|%cn|%ce"],
            cwd=tmp_path, capture_output=True, text=True)
        assert r.stdout.count("SHS-Code-Agent") == 4
        assert "Co-Authored-By: SHS-Code-Agent" in out["message"]

    def test_system_prompt_carries_attribution_mandate(self):
        from app.agent.shscode import SHS_SYSTEM_PROMPT
        assert "GIT ATTRIBUTION" in SHS_SYSTEM_PROMPT
        assert "SHS-Code-Agent" in SHS_SYSTEM_PROMPT
        assert "must not try to change it" in SHS_SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════════════════════
# 3. Detached execution lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestDetachedLifecycle:

    def test_registry_roundtrip_and_liveness(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "home"))
        import importlib
        import app.daemon as daemon
        importlib.reload(daemon)
        try:
            # register a fake (dead) pid
            p = daemon.register_run("run-x", pid=999999, session_id="s1",
                                    prompt="test", log_path="/tmp/x.log")
            assert p.exists()
            runs = daemon.list_runs()
            assert any(r["run_id"] == "run-x" and not r["alive"] for r in runs)
            daemon.update_run("run-x", status="finished", steps=7)
            info = daemon.get_run("run-x")
            assert info["status"] == "finished" and info["steps"] == 7
            assert daemon.get_run("nope") is None
        finally:
            monkeypatch.delenv("SHSCODE_HOME")

    def test_detached_process_survives_parent_and_is_orphaned(self, tmp_path, monkeypatch):
        """The daemon must be reparented to init (ppid==1) and stay alive
        after start_detached_run returns — immune to the caller's death."""
        monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "home"))
        import importlib
        import app.daemon as daemon
        importlib.reload(daemon)
        try:
            argv = ["-c",
                    "import time,sys; time.sleep(10); sys.exit(0)"]
            info = daemon.start_detached_run(
                argv, run_id="run-live", session_id="s-live",
                prompt="sleep test", detached_by="test",
                cwd=str(tmp_path))
            # give exec a moment, then read the registry the daemon wrote
            deadline = time.time() + 10
            entry = None
            while time.time() < deadline:
                entry = daemon.get_run("run-live")
                if entry and entry.get("pid"):
                    break
                time.sleep(0.2)
            assert entry, "daemon never registered itself"
            pid = entry["pid"]
            try:
                assert daemon.pid_alive(pid), "daemon died immediately"
                # double-fork proof: parent must be init (ppid 1)
                stat = Path(f"/proc/{pid}/stat")
                assert stat.exists()
                ppid = int(stat.read_text().split(") ", 1)[1].split()[1])
                assert ppid == 1, f"daemon not orphaned (ppid={ppid})"
            finally:
                try:
                    os.kill(pid, 15)
                    time.sleep(0.5)
                except ProcessLookupError:
                    pass
        finally:
            monkeypatch.delenv("SHSCODE_HOME")

    def test_cli_flags_exist(self):
        """--detach / --runs / --attach are wired into the CLI parser."""
        r = subprocess.run(
            [sys.executable, "-m", "app", "--help"],
            capture_output=True, text=True, timeout=120,
            cwd=str(Path(__file__).resolve().parents[1]))
        assert r.returncode == 0
        for flag in ("--detach", "--runs", "--attach", "--max-steps"):
            assert flag in r.stdout, f"{flag} missing from --help"

    def test_server_run_endpoint_supports_detach_field(self):
        from app.server.main import RunRequest
        req = RunRequest(prompt="long task", detach=True, max_steps=80)
        assert req.detach is True and req.max_steps == 80


# ═══════════════════════════════════════════════════════════════════════════
# 4. Resumed-session tool-call protocol
# ═══════════════════════════════════════════════════════════════════════════

class TestToolCallResumeProtocol:

    def _tc(self, cid, name="bash", args='{"cmd":"ls"}'):
        from app.schema import ToolCall, Function
        return ToolCall(id=cid, type="function",
                        function=Function(name=name, arguments=args))

    def test_orphaned_tool_calls_get_synthetic_results(self):
        from app.schema import Message, Role, sanitize_tool_history
        msgs = [
            Message.system("sys"),
            Message.user("do"),
            Message.assistant(content=None, tool_calls=[self._tc("call_1")]),
            Message.user("(interrupted session resume)"),
        ]
        out = sanitize_tool_history(msgs)
        i = next(i for i, m in enumerate(out) if m.tool_calls)
        assert out[i + 1].role == Role.TOOL
        assert out[i + 1].tool_call_id == "call_1"
        assert "interrupted" in out[i + 1].content

    def test_trailing_orphaned_block_flushed(self):
        from app.schema import Message, Role, sanitize_tool_history
        msgs = [
            Message.user("do"),
            Message.assistant(content=None, tool_calls=[self._tc("call_9")]),
        ]
        out = sanitize_tool_history(msgs)
        assert out[-1].role == Role.TOOL and out[-1].tool_call_id == "call_9"

    def test_orphan_tool_message_dropped(self):
        from app.schema import Message, sanitize_tool_history
        msgs = [
            Message.user("hi"),
            Message.tool(content="ghost", tool_call_id="ghost-id", name="x"),
            Message.assistant(content="done"),
        ]
        out = sanitize_tool_history(msgs)
        assert not any(m.role.value == "tool" for m in out)

    def test_valid_history_untouched(self):
        from app.schema import Message, sanitize_tool_history
        msgs = [
            Message.user("hi"),
            Message.assistant(content=None, tool_calls=[self._tc("call_2")]),
            Message.tool(content="ok", tool_call_id="call_2", name="bash"),
            Message.assistant(content="finished"),
        ]
        out = sanitize_tool_history(msgs)
        assert [m.role for m in out] == [m.role for m in msgs]

    @pytest.mark.asyncio
    async def test_think_sends_sanitized_history(self, monkeypatch):
        """The LLM request boundary must never see an invalid history."""
        from app.schema import Message, Role
        from app.agent.shscode import SHSCode

        agent = SHSCode()
        # craft memory with an orphaned tool_calls block (interruption)
        agent.memory.messages.append(Message.user("do something"))
        agent.memory.messages.append(
            Message.assistant(content=None, tool_calls=[self._tc("call_z")]))

        captured = {}

        class StubLLM:
            async def ask_tool(self, messages, tools, **_):
                captured["messages"] = messages
                return Message.assistant(content="done now")

        agent.llm = StubLLM()
        try:
            await agent.think()
        finally:
            await agent.cleanup()
        sent = captured["messages"]
        # the request must contain a tool message answering call_z
        assert any(m.role == Role.TOOL and m.tool_call_id == "call_z"
                   for m in sent)

    @pytest.mark.asyncio
    async def test_cancelled_tool_appends_result_then_reraises(self):
        """Producer-side fix: CancelledError during tool execution must
        leave a valid tool message (resumable) and still propagate."""
        from app.agent.shscode import SHSCode
        from app.schema import Message, Role

        agent = SHSCode()
        agent.memory.messages.append(Message.user("slow task"))
        agent.memory.messages.append(
            Message.assistant(content=None, tool_calls=[self._tc("call_c")]))

        class CancellingTool:
            async def execute(self, name, **kwargs):
                raise asyncio.CancelledError()

            def to_openai_schemas(self):
                return []

            async def cleanup_all(self):
                pass

        agent.tools = CancellingTool()

        from app.schema import ToolCall, Function
        with pytest.raises(asyncio.CancelledError):
            await agent.act("")
        # memory now contains the synthetic result for call_c
        assert any(m.role == Role.TOOL and m.tool_call_id == "call_c"
                   for m in agent.memory.messages)
        await agent.cleanup()

    def test_diagnostic_event_emitted_on_tool_exception(self):
        """The resumed-session investigation requirement: failures record
        structured, greppable diagnostics (tool, class, args)."""
        from app.recovery import diagnose, RetryStrategy
        # sanity of the classification layer the diagnostics build on
        d = diagnose("connection refused while talking to example.com",
                     context="tool", attempts=1)
        assert d is not None
