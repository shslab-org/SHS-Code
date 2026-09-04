from __future__ import annotations

"""
SHS Code — Rolling-Window Rate Limiter
======================================
(spec §18 / §41) Provider-specific request pacing using a true rolling
window of request timestamps — NOT a naive "wait 60s after each request".

How it works (4 RPM example):
    Timestamps in window: 12:00:05, 12:00:15, 12:00:30, 12:00:50
    A 5th request becomes available at 12:01:05 — the instant the OLDEST
    timestamp (12:00:05) leaves the 60-second rolling window. It does NOT
    wait a fixed 60s after the last request.

Guarantees (spec §19):
    - acquire() only sleeps; it never mutates caller state, so task context,
      conversation history and tool results survive every rate-limit wait.
    - Waits are emitted on the ActivityBus (rate_limit_wait / rate_limit_resume)
      so the UI can show "Rate limited. Waiting for capacity..." and then
      "Capacity available. Continuing...".
    - The wait itself is cancellable: acquire() is a plain asyncio.sleep, so
      cancelling the surrounding task cancels the wait cleanly.

Usage:
    from app.llm.rate_limiter import get_limiter
    await get_limiter("nvidia-nim", rpm=40).acquire()   # before every request

Configuration:
    [llm.rate_limit]
    enabled = true
    rpm     = 0    # 0/absent => automatic: provider default, else unlimited

    Per-provider custom limits (override the global + provider default for
    that provider only) live in the provider registry
    (~/.shscode/providers.json, via `/provider add ... [rpm]`):
      /provider add my-nim openai-compat https://... model key 30

    RPM resolution order (per request):
      1. per-provider custom RPM (registry entry rpm > 0)
      2. global custom RPM ([llm.rate_limit].rpm > 0)
      3. provider default (NVIDIA NIM endpoints => 40)
      4. 0 => unlimited (no limiter; only server 429s throttle)

    The limiter NEVER delays a request while the rolling window has
    capacity — it only engages when the limit is actually reached.
"""

import asyncio
import time
from collections import deque
from typing import Deque, Dict, Optional

from app.activity import emit

# Provider defaults: RPM for well-known hosted endpoints. 0 = unlimited.
DEFAULT_RPM: Dict[str, int] = {
    "nvidia-nim": 40,   # NVIDIA NIM personal-key tier (40 RPM)
    "nvidia": 40,
    "nim": 40,
}

_WINDOW_SECONDS = 60.0


def detect_nim(base_url: Optional[str], provider: Optional[str]) -> bool:
    """True when the endpoint looks like NVIDIA NIM."""
    if base_url and "nvidia" in base_url.lower():
        return True
    if provider and ("nim" in provider.lower() or "nvidia" in provider.lower()):
        return True
    return False


def resolve_rpm(provider: Optional[str], base_url: Optional[str],
                custom_rpm: int = 0) -> int:
    """Effective RPM for a provider (custom > provider default > unlimited).

    - custom_rpm > 0            -> custom user-configured limit (wins)
    - provider default known    -> e.g. NVIDIA NIM => 40
    - otherwise                 -> 0 (unlimited; no artificial throttling)
    """
    custom_rpm = int(custom_rpm or 0)
    if custom_rpm > 0:
        return custom_rpm
    p = (provider or "").strip().lower()
    if p in DEFAULT_RPM:
        return DEFAULT_RPM[p]
    if detect_nim(base_url, provider):
        return DEFAULT_RPM["nvidia-nim"]
    return 0


class RollingWindowRateLimiter:
    """Per-provider rolling-window request limiter (timestamps, spec §18).

    v3.0 ADAPTIVE LEARNING (benchmark finding: shared NIM endpoints enforce
    an EFFECTIVE rate far below the documented 40 RPM, and 429s arrive
    WITHOUT Retry-After headers — the plain rolling window kept refilling
    capacity every ~1.5s, so every retry hit another 429 until the retry
    budget died). The limiter now LEARNS the real capacity:

      - Every 429 (with or without Retry-After) increments a consecutive
        pressure counter and sets a penalty cooldown with exponential
        growth (2s → 4s → 8s … capped at ADAPTIVE_MAX_BLOCK_S).
      - Every 429 WITHOUT Retry-After also records occupancy timestamps
        in the window, so the assumed capacity is consumed faster and the
        next natural wait is longer.
      - Every SUCCESS decays the pressure: counter halves, penalty backoff
        halves — after a streak of successes the limiter converges back to
        the configured rolling-window rate.
    """

    ADAPTIVE_BASE_BLOCK_S = 2.0
    ADAPTIVE_MAX_BLOCK_S = 60.0

    def __init__(self, provider: str, rpm: int, window_s: float = _WINDOW_SECONDS) -> None:
        self.provider = provider or "unknown"
        self.rpm = int(rpm)
        self.window_s = float(window_s)
        self._timestamps: Deque[float] = deque()
        self._blocked_until: float = 0.0   # server-side 429 pressure (Retry-After)
        self._total_requests = 0
        self._total_wait_s = 0.0
        self._last_wait_s = 0.0
        # v3.0 adaptive learning state
        self._pressure: int = 0            # consecutive 429 pressure level
        self._success_streak: int = 0
        self._consecutive_429: int = 0
        self._adaptive_block_until: float = 0.0
        self._total_429: int = 0

    # ------------------------------------------------------------------
    # Pure calculation (unit-testable without sleeping)
    # ------------------------------------------------------------------

    def _evict(self, now: float) -> None:
        """Drop timestamps that have left the rolling window."""
        cutoff = now - self.window_s
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()

    def wait_seconds(self, now: Optional[float] = None) -> float:
        """Seconds the NEXT request must wait, 0.0 if capacity is available.

        This is the heart of the rolling window: we wait only until the
        OLDEST in-window request expires, not a fixed cooldown. Server-side
        429 pressure (blocked_until) is respected even when rpm is unlimited.
        """
        now = time.monotonic() if now is None else now
        blocked = max(
            (self._blocked_until - now) if self._blocked_until else 0.0,
            (self._adaptive_block_until - now) if self._adaptive_block_until else 0.0,
        )
        if blocked < 0:
            blocked = 0.0
        if self.rpm <= 0:
            return blocked
        self._evict(now)
        if len(self._timestamps) < self.rpm:
            return blocked
        # Oldest timestamp leaves the window at ts + window_s.
        available_at = self._timestamps[0] + self.window_s
        return max(blocked, available_at - now)

    def record(self, now: Optional[float] = None) -> None:
        """Record that a request was sent (called by acquire())."""
        self._timestamps.append(time.monotonic() if now is None else now)
        self._total_requests += 1

    # ------------------------------------------------------------------
    # Async acquisition (the real gate)
    # ------------------------------------------------------------------

    async def acquire(self) -> float:
        """Wait until the rolling window permits one more request.

        Returns the seconds actually waited (0.0 if no wait was needed).
        Never raises (except CancelledError propagating from sleep, which is
        desired so task cancellation stays responsive).
        """
        wait = self.wait_seconds()
        if wait > 0:
            emit(
                "rate_limit_wait",
                provider=self.provider,
                rpm=self.rpm,
                wait_s=round(wait, 2),
                in_window=len(self._timestamps),
            )
            # Sleep in small slices so long waits stay cancellable and the
            # remaining time can be recomputed if the window shifts.
            deadline = time.monotonic() + wait
            self._last_wait_s = wait
            self._total_wait_s += wait
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(remaining, 1.0))
            emit("rate_limit_resume", provider=self.provider, waited_s=round(wait, 2))

        self.record()
        if self._blocked_until and self._blocked_until <= time.monotonic():
            self._blocked_until = 0.0
        return max(0.0, self._last_wait_s) if wait > 0 else 0.0

    def on_rate_limit_response(self, retry_after_s: Optional[float] = None,
                               now: Optional[float] = None) -> None:
        """Server told us 429. Record the request in the window AND (when the
        server told us Retry-After) block until that moment — this works even
        for unlimited (rpm=0) limiters, mirroring server-side pressure.

        v3.0 ADAPTIVE: a 429 without Retry-After is REAL evidence the endpoint
        is more congested than the rolling window assumes — instead of
        refilling capacity after ~1.5s and walking straight into the next
        429, the limiter grows an exponential penalty cooldown (decayed on
        every subsequent success). The 429 also occupies window capacity so
        the natural rolling wait lengthens too."""
        now = time.monotonic() if now is None else now
        self._consecutive_429 += 1
        self._total_429 += 1
        self._success_streak = 0
        if retry_after_s and retry_after_s > 0:
            self._blocked_until = max(self._blocked_until,
                                      now + float(retry_after_s))
        else:
            # No Retry-After: grow adaptive penalty (2s → 4s → 8s → … cap 60s)
            self._pressure = min(self._pressure + 1, 8)
            block = min(self.ADAPTIVE_BASE_BLOCK_S * (2 ** (self._pressure - 1)),
                        self.ADAPTIVE_MAX_BLOCK_S)
            self._adaptive_block_until = max(self._adaptive_block_until,
                                             now + block)
        # The 429'd request still consumed server capacity — occupy the window.
        if self.rpm > 0:
            self._timestamps.append(now)

    def on_success(self) -> None:
        """v3.0 ADAPTIVE: decay pressure after a successful request so the
        limiter converges back to the configured rate once contention
        clears. Called by the LLM retry loop on every 2xx response."""
        self._success_streak += 1
        if self._consecutive_429 > 0:
            self._consecutive_429 = max(0, self._consecutive_429 - 1)
        if self._pressure > 0 and self._success_streak >= 2:
            self._pressure = max(0, self._pressure - 1)
            # shrink any outstanding adaptive penalty
            now = time.monotonic()
            if self._adaptive_block_until > now:
                remaining = self._adaptive_block_until - now
                self._adaptive_block_until = now + remaining / 2

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        now = time.monotonic()
        self._evict(now)
        return {
            "provider": self.provider,
            "rpm": self.rpm,
            "in_window": len(self._timestamps),
            "next_wait_s": round(self.wait_seconds(now), 2),
            "total_requests": self._total_requests,
            "total_wait_s": round(self._total_wait_s, 1),
            "adaptive_pressure": self._pressure,
            "consecutive_429": self._consecutive_429,
            "total_429": self._total_429,
        }

    def reset(self) -> None:
        self._timestamps.clear()
        self._blocked_until = 0.0
        self._adaptive_block_until = 0.0
        self._pressure = 0
        self._consecutive_429 = 0
        self._success_streak = 0


# ──────────────────────────────────────────────────────────────────────────────
# Registry — one limiter per provider identity
# ──────────────────────────────────────────────────────────────────────────────

_limiters: Dict[str, RollingWindowRateLimiter] = {}


def limiter_key(provider: str, base_url: Optional[str], model: str = "") -> str:
    """Stable identity for a limiter: provider + endpoint + model."""
    p = (provider or "unknown").strip().lower()
    b = (base_url or "").strip().rstrip("/").lower()
    if b:
        # Strip scheme so http/https of same host share the limiter.
        b = b.replace("https://", "").replace("http://", "")
    return f"{p}|{b}|{(model or '').strip().lower()}"


def get_limiter(provider: str, base_url: Optional[str] = None, model: str = "",
                rpm: Optional[int] = None) -> RollingWindowRateLimiter:
    """Get-or-create the limiter for this provider/endpoint/model.

    RPM resolution order:
      1. explicit rpm argument (custom: per-provider or global config)
      2. provider default (NVIDIA NIM => 40)
      3. 0 = unlimited
    """
    key = limiter_key(provider, base_url, model)
    if key in _limiters:
        # Allow live RPM adjustment (config reload / provider switch).
        if rpm is not None and rpm != _limiters[key].rpm:
            _limiters[key].rpm = int(rpm)
            if rpm <= 0:
                _limiters[key].reset()
        return _limiters[key]

    if rpm is None:
        rpm = resolve_rpm(provider, base_url)

    lim = RollingWindowRateLimiter(provider=key.split("|")[0], rpm=rpm)
    _limiters[key] = lim
    return lim


def all_stats() -> Dict[str, dict]:
    return {k: v.stats() for k, v in _limiters.items()}


def reset_all() -> None:
    _limiters.clear()
