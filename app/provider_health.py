from __future__ import annotations

"""
SHS Code — Provider Health Monitor (spec §21, §24)
====================================================
Per-provider health + usage registry:

  availability    🟢 available | 🟡 rate-limited | 🔴 failing / cooldown
  requests / errors / success rate
  latency (EMA, p50-ish)
  input/output tokens + cost estimate where the API reports usage
  rate-limit state (from the rolling-window limiter)
  cooldown_until (after hard failures)
  recent errors (masked, last 5)

Recorded from the live LLM call path (LLM._call_with_retry) — no fake
data. Used by: provider routing hints (spec §20), /usage, /status,
/doctor. Survives nothing needs to — it's operational telemetry, not
task state; a fresh process starts a fresh health window (the journal
remains the source of truth for task state).
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.logger import logger

# Rough price estimates USD / 1M tokens (only used for display when the
# provider does not report cost; clearly approximate).
_PRICE_HINTS = {
    "gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.15, 0.60),
    "claude": (3.00, 15.00), "gemini": (1.25, 5.00),
    "llama": (0.20, 0.30), "deepseek": (0.14, 0.28),
    "qwen": (0.20, 0.40), "mistral": (0.50, 1.50),
}


@dataclass
class ProviderStats:
    provider: str
    model: str = ""
    requests: int = 0
    successes: int = 0
    errors: int = 0
    rate_limited: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ema_s: float = 0.0            # seconds
    last_latency_s: float = 0.0
    last_request_at: float = 0.0
    last_error_at: float = 0.0
    last_error: str = ""
    cooldown_until: float = 0.0
    recent_errors: List[str] = field(default_factory=list)

    def to_dict(self, masked: bool = True) -> Dict[str, Any]:
        ok_rate = (self.successes / self.requests) if self.requests else 1.0
        return {
            "provider": self.provider, "model": self.model,
            "requests": self.requests, "errors": self.errors,
            "success_rate": round(ok_rate, 3),
            "rate_limited": self.rate_limited,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_avg_s": round(self.latency_ema_s, 2),
            "latency_last_s": round(self.last_latency_s, 2),
            "last_request_ago_s": int(time.time() - self.last_request_at) if self.last_request_at else None,
            "last_error_ago_s": int(time.time() - self.last_error_at) if self.last_error_at else None,
            "last_error": (self.last_error[:160] if not masked else _mask_error(self.last_error)),
            "cooldown": self.cooldown_until > time.time(),
            "status": self.status(),
            "cost_estimate_usd": self.cost_estimate(),
        }

    def status(self) -> str:
        if self.cooldown_until > time.time():
            return "🔴"
        if self.rate_limited and time.time() - self.last_request_at < 120:
            return "🟡"
        if self.requests >= 3 and self.successes / self.requests < 0.5:
            return "🔴"
        if self.errors and time.time() - self.last_error_at < 300 \
                and not self.successes:
            return "🔴"
        if self.requests == 0:
            return "⚪"
        return "🟢"

    def cost_estimate(self) -> Optional[float]:
        if not (self.input_tokens or self.output_tokens):
            return None
        key = (self.model or self.provider or "").lower()
        for k, (pin, pout) in _PRICE_HINTS.items():
            if k in key:
                return round(self.input_tokens / 1e6 * pin
                             + self.output_tokens / 1e6 * pout, 4)
        # generic fallback
        return round(self.input_tokens / 1e6 * 0.5 + self.output_tokens / 1e6 * 1.5, 4)


_SECRET_RX = None


def _mask_error(text: str) -> str:
    global _SECRET_RX
    if _SECRET_RX is None:
        import re
        _SECRET_RX = re.compile(
            r"(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|gho_[A-Za-z0-9]{8,}|"
            r"hf_[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._\-]{8,}|"
            r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,})",
            re.IGNORECASE)
    return _SECRET_RX.sub("[REDACTED]", text or "")[:160]


class ProviderHealth:
    """Thread-safe registry of live provider stats. Singleton via get_health()."""

    _instance: Optional["ProviderHealth"] = None
    _lock = threading.Lock()

    LATENCY_ALPHA = 0.25

    def __init__(self) -> None:
        self._stats: Dict[str, ProviderStats] = {}
        self._rlock = threading.RLock()

    @classmethod
    def get(cls) -> "ProviderHealth":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _key(self, provider: str, model: str = "") -> str:
        return f"{(provider or '?').lower()}|{(model or '').lower()}"

    def record_call(self, provider: str, model: str = "",
                    latency_s: float = 0.0, ok: bool = True,
                    input_tokens: int = 0, output_tokens: int = 0) -> None:
        key = self._key(provider, model)
        with self._rlock:
            s = self._stats.setdefault(key, ProviderStats(provider=provider, model=model))
            s.requests += 1
            s.last_request_at = time.time()
            s.last_latency_s = latency_s
            if s.latency_ema_s == 0:
                s.latency_ema_s = latency_s
            else:
                s.latency_ema_s += self.LATENCY_ALPHA * (latency_s - s.latency_ema_s)
            if ok:
                s.successes += 1
                s.rate_limited = 0      # a successful call means we're not limited now
            else:
                s.errors += 1
                s.last_error_at = time.time()
            if input_tokens:
                s.input_tokens += input_tokens
            if output_tokens:
                s.output_tokens += output_tokens

    def record_error(self, provider: str, model: str = "", error: str = "",
                     rate_limited: bool = False) -> None:
        key = self._key(provider, model)
        with self._rlock:
            s = self._stats.setdefault(key, ProviderStats(provider=provider, model=model))
            s.errors += 1
            s.last_error_at = time.time()
            s.last_error = (error or "")[:300]
            s.recent_errors.append(_mask_error(error)[:160])
            s.recent_errors = s.recent_errors[-5:]
            if rate_limited:
                s.rate_limited += 1
            else:
                # escalating cooldown after consecutive hard failures
                recent_fail = (time.time() - s.last_request_at) < 60
                if s.errors >= 4 and s.successes == 0:
                    s.cooldown_until = time.time() + min(300, 30 * s.errors)

    def clear_rate_limit(self, provider: str, model: str = "") -> None:
        key = self._key(provider, model)
        with self._rlock:
            if key in self._stats:
                self._stats[key].cooldown_until = 0.0

    def cooldown_remaining(self, provider: str, model: str = "") -> float:
        key = self._key(provider, model)
        with self._rlock:
            s = self._stats.get(key)
            if s:
                return max(0.0, s.cooldown_until - time.time())
        return 0.0

    def is_available(self, provider: str, model: str = "") -> bool:
        return self.cooldown_remaining(provider, model) <= 0

    def stats(self) -> Dict[str, Dict[str, Any]]:
        with self._rlock:
            return {k: v.to_dict() for k, v in self._stats.items()}

    def healthy_providers(self) -> List[str]:
        """Providers with no cooldown + non-red status (routing candidates)."""
        with self._rlock:
            return [s.provider for k, s in self._stats.items()
                    if s.status() in ("🟢", "⚪", "🟡")]

    def recommend_provider(self, candidates: List[str]) -> Optional[str]:
        """Routing hint (spec §20): pick best available candidate by
        success rate, then fewer errors, then latency, then volume.
        Matching is by PROVIDER name (any model) — callers usually don't
        know the model of a candidate provider."""
        with self._rlock:
            scored = []
            for c in candidates:
                entries = [s for s in self._stats.values()
                           if s.provider == c.lower()]
                if not entries:
                    scored.append((0.8, 0, 0.0, 0, c))  # neutral for unseen
                    continue
                s = max(entries, key=lambda x: x.requests)  # primary model
                if s.cooldown_until > time.time():
                    continue
                if s.requests >= 3:
                    ok = s.successes / s.requests
                    scored.append((ok, -s.errors, -s.latency_ema_s,
                                   s.requests, c))
                elif s.requests == 0 and s.errors > 0:
                    # never succeeded, already failing — degrading candidate
                    scored.append((0.2, -s.errors, 0.0, 0, c))
                else:
                    scored.append((0.8, 0, 0.0, s.requests, c))
            if not scored:
                return None
            scored.sort(reverse=True)
            return scored[0][-1]

    def render(self) -> str:
        """/usage style table (spec §42)."""
        rows = list(self.stats().values())
        if not rows:
            return "No provider usage recorded yet."
        lines = [f"{'STATUS':<8} {'PROVIDER':<16} {'MODEL':<26} {'REQ':>5} "
                 f"{'ERR':>4} {'RATE':>4} {'LAT':>7} {'IN':>9} {'OUT':>9} {'COST':>8}",
                 "-" * 100]
        total_in = total_out = 0
        total_cost = 0.0
        for r in sorted(rows, key=lambda x: -x["requests"]):
            total_in += r["input_tokens"]
            total_out += r["output_tokens"]
            total_cost += r.get("cost_estimate_usd") or 0
            lat = f"{r['latency_avg_s']}s" if r["latency_avg_s"] else "-"
            cost = "$" + str(r["cost_estimate_usd"]) if r.get("cost_estimate_usd") is not None else "-"
            lines.append(
                f"{r['status']:<8} {r['provider'][:15]:<16} {r['model'][:25]:<26} "
                f"{r['requests']:>5} {r['errors']:>4} {r['rate_limited']:>4} "
                f"{lat:>7} {r['input_tokens']:>9} {r['output_tokens']:>9} {cost:>8}")
        lines.append("-" * 100)
        lines.append(f"TOTAL: {len(rows)} backend(s) — in={total_in} out={total_out} "
                     f"tokens, est. cost ≈ ${round(total_cost, 4)} (approximate, where usage data is reported)")
        return "\n".join(lines)


def get_health() -> ProviderHealth:
    return ProviderHealth.get()
