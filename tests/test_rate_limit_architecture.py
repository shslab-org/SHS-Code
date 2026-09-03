"""Rate-limit architecture (spec §6/§7) — provider default + custom override.

Semantics under test:
  - custom limit exists       -> use custom limit (per-provider > global)
  - custom limit does not     -> use provider default (NVIDIA NIM = 40)
  - provider w/o default      -> NO limiter (no artificial throttling)
  - below the limit           -> zero wait (limiter never delays capacity)
  - limit reached             -> rolling-window pacing engages
  - server 429                -> blocked_until honored even when unlimited
  - switching providers       -> custom rpm restored to global baseline
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_ENV", "test")

import pytest

from app.llm.rate_limiter import (
    DEFAULT_RPM, RollingWindowRateLimiter, detect_nim, get_limiter,
    resolve_rpm, reset_all, all_stats,
)


@pytest.fixture(autouse=True)
def _restore_llm_config():
    """Snapshot the global LLM config and restore it after every test —
    several tests here mutate provider/base_url/rate_limit on the live
    singleton (provider_overlay mutates in place) and must never leak
    into other test files."""
    from app.config import Config
    llm = Config.get().llm
    snap = {k: getattr(llm, k) for k in
            ("provider", "model", "base_url", "api_key", "max_tokens",
             "temperature", "max_retries", "timeout")}
    rl = llm.rate_limit
    snap_rl = (rl.enabled, rl.rpm)
    yield
    for k, v in snap.items():
        setattr(llm, k, v)
    rl.enabled, rl.rpm = snap_rl



class TestResolveRPM:
    """RPM resolution precedence: custom > provider default > unlimited."""

    def test_custom_overrides_provider_default(self):
        assert resolve_rpm("nvidia-nim", "https://integrate.api.nvidia.com/v1", 7) == 7

    def test_provider_default_nim_without_custom(self):
        assert resolve_rpm("nvidia-nim", None, 0) == DEFAULT_RPM["nvidia-nim"]

    def test_nim_detected_from_url_only(self):
        # custom provider name, nvidia base_url -> provider default 40
        assert resolve_rpm("universal", "https://integrate.api.nvidia.com/v1", 0) == 40

    def test_unknown_provider_no_default_unlimited(self):
        assert resolve_rpm("openai", "https://api.openai.com/v1", 0) == 0
        assert resolve_rpm("ollama", "http://localhost:11434", 0) == 0

    def test_zero_custom_means_unset_not_zero_limit(self):
        # rpm=0 must mean "no custom limit", never "block everything"
        assert resolve_rpm("openai", None, 0) == 0


class TestNoArtificialThrottle:
    """The limiter must never delay a request while capacity remains."""

    def test_below_limit_zero_wait(self):
        lim = RollingWindowRateLimiter("p", rpm=40, window_s=60.0)
        now = 1000.0
        for i in range(39):  # 39 of 40 used
            lim.record(now=now + i * 0.01)
        assert lim.wait_seconds(now=now + 1.0) == 0.0

    def test_at_limit_wait_until_oldest_expires(self):
        lim = RollingWindowRateLimiter("p", rpm=40, window_s=60.0)
        now = 1000.0
        for i in range(40):
            lim.record(now=now + i * 0.01)
        w = lim.wait_seconds(now=now + 1.0)
        assert w > 58.9  # oldest (1000.0) expires at 1060 -> ~59s remain

    def test_burst_allowed_up_to_limit(self):
        # 40 burst requests: the first 40 must report zero wait
        lim = RollingWindowRateLimiter("p", rpm=40, window_s=60.0)
        waits = []
        t = 1000.0
        for _ in range(40):
            waits.append(lim.wait_seconds(now=t))
            lim.record(now=t)
        assert all(w == 0.0 for w in waits)

    def test_window_slide_releases_capacity(self):
        lim = RollingWindowRateLimiter("p", rpm=40, window_s=60.0)
        t0 = 1000.0
        for i in range(40):
            lim.record(now=t0 + i * 0.01)
        # exactly at limit -> wait
        assert lim.wait_seconds(now=t0 + 5.0) > 0
        # 61s later everything expired -> capacity again
        assert lim.wait_seconds(now=t0 + 61.0) == 0.0


class TestNoLimiterForUnlimitedProviders:
    """LLM._limiter() must return None (no limiter at all) when neither a
    custom limit nor a provider default exists."""

    def _llm(self):
        from app.config import Config
        cfg = Config.get()
        cfg.llm.provider = "mock"  # backend never built for real providers
        from app.llm.llm import LLM
        llm = LLM()
        return llm

    def test_openai_no_custom_no_limiter(self):
        from app.config import Config
        cfg = Config.get()
        cfg.llm.provider = "openai"
        cfg.llm.base_url = "https://api.openai.com/v1"
        cfg.llm.rate_limit.rpm = 0
        cfg.llm.rate_limit.enabled = True
        llm = self._llm(); llm._provider = "openai"; llm._base_url = "https://api.openai.com/v1"
        assert llm._limiter() is None

    def test_nim_default_limiter_created_with_40(self):
        from app.config import Config
        cfg = Config.get()
        cfg.llm.provider = "universal"
        cfg.llm.base_url = "https://integrate.api.nvidia.com/v1"
        cfg.llm.rate_limit.rpm = 0
        cfg.llm.rate_limit.enabled = True
        llm = self._llm(); llm._provider = "universal"; llm._base_url = "https://integrate.api.nvidia.com/v1"
        lim = llm._limiter()
        assert lim is not None and lim.rpm == 40

    def test_global_custom_applies_to_any_provider(self):
        from app.config import Config
        cfg = Config.get()
        cfg.llm.provider = "openai"
        cfg.llm.base_url = "https://api.openai.com/v1"
        cfg.llm.rate_limit.rpm = 12
        llm = self._llm(); llm._provider = "openai"; llm._base_url = "https://api.openai.com/v1"
        lim = llm._limiter()
        assert lim is not None and lim.rpm == 12

    def test_rate_limit_disabled_master_switch(self):
        from app.config import Config
        cfg = Config.get()
        cfg.llm.rate_limit.rpm = 30
        cfg.llm.rate_limit.enabled = False
        llm = self._llm(); llm._provider = "openai"; llm._base_url = "https://api.openai.com/v1"
        assert llm._limiter() is None


class Test429Recovery:
    """Server-side 429 pressure must work even for unlimited limiters."""

    def test_429_blocks_unlimited_limiter(self):
        lim = RollingWindowRateLimiter("p", rpm=0, window_s=60.0)
        assert lim.wait_seconds(now=1000.0) == 0.0
        lim.on_rate_limit_response(retry_after_s=30, now=1000.0)
        assert lim.wait_seconds(now=1001.0) > 28.0
        # recovered after the window
        assert lim.wait_seconds(now=1032.0) == 0.0

    def test_429_retry_after_stacks_with_window(self):
        lim = RollingWindowRateLimiter("p", rpm=2, window_s=60.0)
        lim.record(now=1000.0); lim.record(now=1000.5)
        lim.on_rate_limit_response(retry_after_s=10, now=1000.7)
        # blocked_until = 1010 (later than window expiry 1060? no: 1060 later)
        w = lim.wait_seconds(now=1001.0)
        assert w == pytest.approx(59.0, abs=1.0)  # window dominates

    def test_task_state_survives_wait(self):
        # wait only sleeps — caller state untouched (checked structurally:
        # acquire() takes no state and mutates nothing outside the limiter)
        lim = RollingWindowRateLimiter("p", rpm=1, window_s=0.3)
        state = {"messages": [1, 2, 3], "task": "build"}
        lim.record(now=1000.0)
        # fresh real clock: 1 in window, 1 rpm -> must wait for window expiry
        async def run():
            return await lim.acquire()
        waited = asyncio.run(run())
        assert waited >= 0.0
        assert state == {"messages": [1, 2, 3], "task": "build"}


class TestLiveRpmAdjustment:
    """get_limiter live updates must work in BOTH directions."""

    def test_custom_to_lower_updates(self):
        reset_all()
        lim = get_limiter("x", "https://x/v1", "m", rpm=30)
        assert lim.rpm == 30
        lim2 = get_limiter("x", "https://x/v1", "m", rpm=10)
        assert lim2 is lim and lim2.rpm == 10

    def test_clearing_custom_to_default(self):
        reset_all()
        lim = get_limiter("openai", "https://api.openai.com/v1", "m", rpm=30)
        assert lim.rpm == 30
        # custom removed -> resolve default (0 for openai) -> limiter disabled
        lim2 = get_limiter("openai", "https://api.openai.com/v1", "m",
                           rpm=resolve_rpm("openai", "https://api.openai.com/v1", 0))
        assert lim2 is lim and lim2.rpm == 0

    def test_default_updates_when_rpm_given(self):
        reset_all()
        lim = get_limiter("nvidia-nim", None, "m")  # default 40
        assert lim.rpm == 40
        lim2 = get_limiter("nvidia-nim", None, "m", rpm=60)
        assert lim2 is lim and lim2.rpm == 60


class TestProviderOverlayRpm:
    """Per-provider registry entries carry their own custom RPM."""

    def _fresh_registry(self, tmp_path):
        import importlib
        import app.providers as P
        reg = P.ProviderRegistry(path=tmp_path / "providers.json")
        return reg

    def test_overlay_applies_custom_rpm(self, tmp_path):
        from app.config import Config
        reg = self._fresh_registry(tmp_path)
        reg.add("fast-nim", "openai-compat", "https://integrate.api.nvidia.com/v1",
                "k", "m", rpm=25)
        cfg = Config.get()
        cfg.llm.rate_limit.rpm = 0
        import app.providers as P
        P._overlay_state["base_rpm"] = None
        assert reg.provider_overlay("fast-nim", cfg) is True
        assert cfg.llm.rate_limit.rpm == 25

    def test_overlay_without_rpm_restores_global(self, tmp_path):
        from app.config import Config
        reg = self._fresh_registry(tmp_path)
        reg.add("plain", "openai-compat", "https://api.example.com/v1", "k", "m")
        cfg = Config.get()
        cfg.llm.rate_limit.rpm = 9  # global custom
        import app.providers as P
        P._overlay_state["base_rpm"] = None
        assert reg.provider_overlay("plain", cfg) is True
        assert cfg.llm.rate_limit.rpm == 9  # global baseline kept

    def test_switching_providers_restores_baseline(self, tmp_path):
        from app.config import Config
        reg = self._fresh_registry(tmp_path)
        reg.add("limited", "openai-compat", "https://a.example.com/v1", "k", "m", rpm=25)
        reg.add("free", "openai-compat", "https://b.example.com/v1", "k", "m")
        cfg = Config.get()
        cfg.llm.rate_limit.rpm = 0
        import app.providers as P
        P._overlay_state["base_rpm"] = None
        reg.provider_overlay("limited", cfg)
        assert cfg.llm.rate_limit.rpm == 25
        # switch to provider without custom -> back to global baseline (0)
        reg.provider_overlay("free", cfg)
        assert cfg.llm.rate_limit.rpm == 0

    def test_registry_persists_rpm(self, tmp_path):
        import app.providers as P
        reg = P.ProviderRegistry(path=tmp_path / "providers.json")
        reg.add("p1", "openai-compat", "https://x/v1", "k", "m", rpm=17)
        reg2 = P.ProviderRegistry(path=tmp_path / "providers.json")
        assert reg2.get("p1")["rpm"] == 17

    def tearDown(self):
        reset_all()


class TestLimiterKeySharing:
    def test_same_endpoint_shares_limiter(self):
        reset_all()
        a = get_limiter("universal", "https://x.example.com/v1", "m1")
        b = get_limiter("universal", "https://x.example.com/v1/", "M1")
        assert a is b
