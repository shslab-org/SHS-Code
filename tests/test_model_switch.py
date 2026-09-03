"""SHS Code — Model/provider switch context tests (spec §4, §40, §17).

Verifies: switching model/provider rebuilds ONLY the reasoning backend.
Agent memory (conversation context), token budget reference and task state
are preserved — never "Starting from scratch...".
"""
import asyncio
import os

import pytest

os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def fresh_llm(monkeypatch, tmp_path):
    monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "home"))
    from app.config import Config
    Config.reset()
    from app.llm.llm import LLM
    llm = LLM()  # instance — config already resolved to mock in test env
    yield llm
    Config.reset()


class TestLLMSwitch:
    def test_switch_model_rebuilds_backend_preserves_budget(self, fresh_llm):
        llm = fresh_llm
        budget = llm.token_budget
        info = asyncio.run(llm.switch(model="test-model-b"))
        assert info["model"] == "test-model-b"
        assert llm.token_budget is budget  # same object — never reset

    def test_switch_provider_live(self, fresh_llm):
        llm = fresh_llm
        info = asyncio.run(llm.switch(provider="mock", model="m2"))
        assert info["provider"] == "mock"
        assert llm._provider == "mock"

    def test_switch_works_after_real_ask(self, fresh_llm):
        from app.schema import Message
        llm = fresh_llm
        msgs = [Message.system("sys"), Message.user("build a website")]
        r1 = asyncio.run(llm.ask(msgs))
        assert r1 is not None
        asyncio.run(llm.switch(model="model-b"))
        r2 = asyncio.run(llm.ask(msgs))  # same message list works
        assert r2 is not None

    def test_backend_info_shape(self, fresh_llm):
        info = fresh_llm.backend_info()
        assert {"provider", "model", "backend"} <= set(info.keys())


class TestAgentContextSurvivesSwitch:
    """Spec §40 end-to-end: Model A works → switch → Model B continues."""

    def test_agent_memory_untouched_by_llm_switch(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "home"))
        from app.config import Config
        Config.reset()
        try:
            from app.agent.shscode import SHSCode
            from app.schema import Message, AgentState

            agent = SHSCode()
            # Simulate a task in progress: user + assistant + tool result
            agent.memory.add(Message.user("Build a complete e-commerce website"))
            agent.memory.add(Message.assistant(
                "Plan: 1) frontend 2) backend 3) db 4) auth. Starting frontend."))
            agent.memory.add(Message.tool(
                content="created src/App.tsx", tool_call_id="tc1", name="str_replace_editor"))
            before = [m.to_dict() for m in agent.memory.messages]

            # Switch model (A → B) with full context in memory
            info = asyncio.run(agent.llm.switch(model="model-b-stronger"))

            after = [m.to_dict() for m in agent.memory.messages]
            assert after == before                      # context preserved
            assert agent.llm.backend_info()["model"] == "model-b-stronger"
            assert agent.state == AgentState.IDLE       # task state intact

            # Model B can continue the same conversation (mock backend)
            r = asyncio.run(agent.run("continue with the backend"))
            assert isinstance(r, str) and len(r) > 0
            asyncio.run(agent.cleanup())
        finally:
            Config.reset()

    def test_custom_provider_registry_overlay(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHSCODE_HOME", str(tmp_path / "home"))
        from app.config import Config
        Config.reset()
        try:
            from app.providers import ProviderRegistry, get_providers
            reg = ProviderRegistry(path=tmp_path / "providers.json")
            entry = reg.add(name="my-nim", api_type="openai-compat",
                            base_url="https://integrate.api.nvidia.com/v1",
                            model="meta/llama-3.1-70b-instruct",
                            api_key="nvapi-test-key", rpm=40)
            assert entry["api_type"] == "openai-compat"

            cfg = Config.get()
            assert reg.provider_overlay("my-nim", cfg) is True
            assert cfg.llm.provider == "universal"
            assert cfg.llm.base_url == "https://integrate.api.nvidia.com/v1"
            assert cfg.llm.model == "meta/llama-3.1-70b-instruct"

            # persistence across restart
            reg2 = ProviderRegistry(path=tmp_path / "providers.json")
            assert reg2.get("my-nim")["model"] == "meta/llama-3.1-70b-instruct"

            # masked display never leaks the raw key
            masked = reg2.list(masked=True)[0]["api_key"]
            assert "nvapi-test-key" not in masked
        finally:
            Config.reset()

    def test_models_command_catalog(self):
        from app.providers import KNOWN_MODELS
        assert "nvidia" in KNOWN_MODELS and len(KNOWN_MODELS["nvidia"]) >= 3
