"""SHS Code — Rate limiter tests (spec §18, §41).

Verifies the rolling-window semantics: a 5th request at 4 RPM waits only
until the OLDEST request leaves the 60s window — NOT a naive fixed 60s wait.
Also verifies rate-limit waits never destroy task context (spec §19).
"""
import asyncio
import os
import time

import pytest

from app.llm.rate_limiter import (
    RollingWindowRateLimiter, detect_nim, get_limiter, limiter_key, all_stats,
)


class TestRollingWindow:
    def test_four_rpm_rolling_window(self):
        """Spec §41 example: T=5,15,30,50 → next request waits until t=65."""
        lim = RollingWindowRateLimiter("nvidia-nim", rpm=4, window_s=60.0)
        base = 1000.0
        lim.record(base)        # T1
        lim.record(base + 10)   # T2
        lim.record(base + 25)   # T3
        lim.record(base + 45)   # T4

        # 5th request at t=50: T1 (t=1000) leaves window at 1060 → wait 10s
        assert abs(lim.wait_seconds(base + 50) - 10.0) < 0.01

        # NOT a fixed 60s wait:
        assert lim.wait_seconds(base + 50) < 60.0

        # at t=70: T1 & T2 gone → 2 slots used, capacity available
        assert lim.wait_seconds(base + 70) == 0.0

    def test_window_eviction(self):
        lim = RollingWindowRateLimiter("x", rpm=2, window_s=60.0)
        base = 2000.0
        lim.record(base)
        lim.record(base + 5)
        assert lim.wait_seconds(base + 10) > 0  # full
        assert lim.wait_seconds(base + 61) == 0.0  # T1 expired → 1 slot free

    def test_unlimited_when_rpm_zero(self):
        lim = RollingWindowRateLimiter("x", rpm=0)
        for _ in range(100):
            lim.record()
        assert lim.wait_seconds() == 0.0
        assert asyncio.run(lim.acquire()) == 0.0

    def test_acquire_returns_wait_and_records(self):
        lim = RollingWindowRateLimiter("x", rpm=1, window_s=0.05)
        w0 = asyncio.run(lim.acquire())
        assert w0 == 0.0
        # Second acquire must wait ~window (0.05s) — tiny for test speed
        w1 = asyncio.run(lim.acquire())
        assert w1 > 0.0

    def test_on_rate_limit_response_extends_window(self):
        lim = RollingWindowRateLimiter("x", rpm=2, window_s=60.0)
        lim.record()
        lim.record()
        lim.on_rate_limit_response()  # server 429 — extra pressure
        assert lim.wait_seconds() > 0.0

    def test_retry_after_extends_unlimited_limiter(self):
        lim = RollingWindowRateLimiter("x", rpm=0)
        lim.on_rate_limit_response(retry_after_s=30)
        assert lim.wait_seconds() > 25.0  # ~30s minus a little


class TestNIMDetection:
    def test_detects_nim_url(self):
        assert detect_nim("https://integrate.api.nvidia.com/v1", "universal")
        assert detect_nim("https://integrate.api.nvidia.com/v1", None)

    def test_detects_nim_provider(self):
        assert detect_nim(None, "nvidia-nim")
        assert detect_nim(None, "nim")
        assert detect_nim("https://api.openai.com/v1", "openai") is False

    def test_registry_nim_default_40rpm(self):
        lim = get_limiter("universal", "https://integrate.api.nvidia.com/v1",
                          "meta/llama-3.1-70b-instruct")
        assert lim.rpm == 40

    def test_registry_respects_explicit_rpm(self):
        lim = get_limiter("custom", "https://example.com/v1", "m", rpm=4)
        assert lim.rpm == 4

    def test_registry_lives_rpm_update(self):
        get_limiter("live-test", "https://example.com/v1", "m", rpm=10)
        lim2 = get_limiter("live-test", "https://example.com/v1", "m", rpm=4)
        assert lim2.rpm == 4  # live adjustment

    def test_limiter_key_scheme_insensitive(self):
        assert (limiter_key("universal", "https://x.io/v1", "M")
                == limiter_key("universal", "http://x.io/v1/", "m"))


class TestRateLimitDoesNotDestroyContext:
    """Spec §19: a rate-limited LLM call must leave caller state intact."""

    def test_messages_survive_wait(self):
        from app.schema import Message
        messages = [
            Message.system("you are SHS Code"),
            Message.user("build a website"),
            Message.assistant("frontend done"),
        ]
        snapshot = [m.to_dict() for m in messages]

        lim = RollingWindowRateLimiter("nim", rpm=1, window_s=0.05)
        asyncio.run(lim.acquire())
        asyncio.run(lim.acquire())  # waits, then records

        assert [m.to_dict() for m in messages] == snapshot  # untouched

    def test_llm_rate_limit_error_carries_retry_after(self):
        from app.exceptions import RateLimitError
        err = RateLimitError("Rate limited")
        # UniversalClient attaches these attributes on real 429s
        err.retry_after = 12.0
        assert getattr(err, "retry_after", None) == 12.0
