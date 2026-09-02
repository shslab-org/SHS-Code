from __future__ import annotations

"""
SHS Code — Error Intelligence + Retry Intelligence (spec §44, §45)
===================================================================
Error classification (12 classes) and strategy-driven retry decisions.

classify_error(text, context) →
  ENVIRONMENT_ERROR | DEPENDENCY_ERROR | CODE_ERROR | CONFIGURATION_ERROR |
  NETWORK_ERROR | PROVIDER_ERROR | RATE_LIMIT_ERROR | TOOL_ERROR |
  PERMISSION_ERROR | BUILD_ERROR | TEST_ERROR | GIT_ERROR

retry_decision(class, text, attempts) →
  RETRYABLE (backoff) | WAIT_AND_RETRY (rate limit, with wait_s) |
  NON_RETRYABLE | REQUIRES_FIX (fix code/config, retry after) |
  REQUIRES_USER (missing credential, decision) | EXTERNAL_BLOCKER

Rate limits → WAIT + RETRY (never destroys state). Compilation errors →
REQUIRES_FIX. Missing API key → REQUIRES_USER. Used by the agent tool
retry loop, provider failover, and /status last-error rendering.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class ErrorClass(str, Enum):
    ENVIRONMENT = "ENVIRONMENT_ERROR"
    DEPENDENCY = "DEPENDENCY_ERROR"
    CODE = "CODE_ERROR"
    CONFIGURATION = "CONFIGURATION_ERROR"
    NETWORK = "NETWORK_ERROR"
    PROVIDER = "PROVIDER_ERROR"
    RATE_LIMIT = "RATE_LIMIT_ERROR"
    TOOL = "TOOL_ERROR"
    PERMISSION = "PERMISSION_ERROR"
    BUILD = "BUILD_ERROR"
    TEST = "TEST_ERROR"
    GIT = "GIT_ERROR"
    UNKNOWN = "UNKNOWN_ERROR"


class RetryStrategy(str, Enum):
    RETRYABLE = "RETRYABLE"
    WAIT_AND_RETRY = "WAIT_AND_RETRY"
    NON_RETRYABLE = "NON_RETRYABLE"
    REQUIRES_FIX = "REQUIRES_FIX"
    REQUIRES_USER = "REQUIRES_USER"
    EXTERNAL_BLOCKER = "EXTERNAL_BLOCKER"


@dataclass
class ErrorDiagnosis:
    error_class: ErrorClass
    strategy: RetryStrategy
    confidence: float
    wait_s: float = 0.0
    reason: str = ""
    patterns: List[str] = None

    def __post_init__(self) -> None:
        if self.patterns is None:
            self.patterns = []

    def render(self) -> str:
        w = f" wait={self.wait_s:.0f}s" if self.wait_s else ""
        p = f" [{', '.join(self.patterns[:3])}]" if self.patterns else ""
        return (f"{self.error_class.value} → {self.strategy.value}{w} "
                f"({self.confidence:.0%}){p} {self.reason}")


# (regex, class, confidence boost)
_PATTERNS: List[Tuple[str, ErrorClass, float]] = [
    (r"\b429\b|rate.?limit|too many requests|quota exceeded|rpm\b", ErrorClass.RATE_LIMIT, 3.0),
    (r"retry.?after", ErrorClass.RATE_LIMIT, 2.0),
    (r"module not found|no module named|importerror|cannot import|modulenotfound", ErrorClass.DEPENDENCY, 3.0),
    (r"package not found|npm err|yarn err|pnpm err|unmet dependency|peer dependency", ErrorClass.DEPENDENCY, 2.5),
    (r"dependency resolution|version conflict|incompatible.*version", ErrorClass.DEPENDENCY, 2.0),
    (r"syntaxerror|indentationerror|nameerror|typeerror.*expected|attributeerror", ErrorClass.CODE, 3.0),
    (r"traceback \(most recent", ErrorClass.CODE, 1.0),
    (r"assertionerror|assertion failed|expected .* but got", ErrorClass.TEST, 2.5),
    (r"\btest failed\b|failed \d+ test|failing test|pytest.*failed", ErrorClass.TEST, 2.0),
    (r"build failed|compilation error|compile error|error ts\d+|cannot find symbol", ErrorClass.BUILD, 3.0),
    (r"execution failed for task|gradle.*failed", ErrorClass.BUILD, 2.5),
    (r"merge conflict|conflict.*marker|<<<<<<<", ErrorClass.GIT, 3.0),
    (r"not a git repo|fatal:.*git|git.*error|detached head|bad revision", ErrorClass.GIT, 2.0),
    (r"permission denied|access denied|eacces|eperm|403 forbidden", ErrorClass.PERMISSION, 3.0),
    (r"unauthorized|invalid api key|missing api key|api.?key.*(missing|invalid|required)|no credentials", ErrorClass.CONFIGURATION, 3.0),
    (r"config.*missing|missing.*config|invalid.*config|configparseerror|toml.*error|yaml.*error", ErrorClass.CONFIGURATION, 2.5),
    (r"timeout|timed out|connection reset|connection refused|broken pipe|network|dns|getaddrinfo|socket", ErrorClass.NETWORK, 2.5),
    (r"502|503|504|bad gateway|service unavailable|gateway timeout", ErrorClass.NETWORK, 2.0),
    (r"model not found|invalid model|provider.*error|api.*error|overloaded", ErrorClass.PROVIDER, 2.0),
    (r"command not found|no such file or directory.*executable|not installed", ErrorClass.ENVIRONMENT, 3.0),
    (r"unsupported python|python version|runtime.*not (found|supported)", ErrorClass.ENVIRONMENT, 2.0),
    (r"no such file or directory", ErrorClass.ENVIRONMENT, 1.5),
    (r"disk full|out of memory|oom|killed", ErrorClass.ENVIRONMENT, 2.5),
]

# Context hints add evidence when the caller knows the origin
_CONTEXT_HINTS = {
    "llm": [ErrorClass.PROVIDER, 1.0],
    "provider": [ErrorClass.PROVIDER, 1.5],
    "tool": [ErrorClass.TOOL, 1.0],
    "git": [ErrorClass.GIT, 1.5],
    "build": [ErrorClass.BUILD, 1.0],
    "test": [ErrorClass.TEST, 1.0],
}


def classify_error(text: str, context: str = "") -> Tuple[ErrorClass, float, List[str]]:
    """Classify an error string → (class, confidence 0..1, matched patterns)."""
    if not text:
        return ErrorClass.UNKNOWN, 0.0, []
    low = str(text).lower()
    scores = {c: 0.0 for c in ErrorClass}
    matched: List[str] = []
    for rx, cls, boost in _PATTERNS:
        m = re.search(rx, low)
        if m:
            scores[cls] += boost
            matched.append(m.group(0)[:40])
    if context.lower() in _CONTEXT_HINTS:
        cls, boost = _CONTEXT_HINTS[context.lower()]
        scores[cls] += boost
    # specific overrides
    if re.search(r"429|rate.?limit|too many requests", low) and context == "llm":
        scores[ErrorClass.RATE_LIMIT] += 3.0
    if not any(scores.values()):
        return ErrorClass.UNKNOWN, 0.1, []
    best = max(scores, key=lambda c: scores[c])  # type: ignore[arg-type]
    conf = min(1.0, scores[best] / 5.0)
    return best, conf, matched


def retry_strategy(error_class: ErrorClass, text: str = "",
                    attempts: int = 1) -> RetryStrategy:
    """Decide what to do with a failure (spec §45)."""
    if error_class == ErrorClass.RATE_LIMIT:
        return RetryStrategy.WAIT_AND_RETRY
    if error_class == ErrorClass.NETWORK:
        return RetryStrategy.RETRYABLE
    if error_class in (ErrorClass.CODE, ErrorClass.TEST, ErrorClass.BUILD):
        return RetryStrategy.REQUIRES_FIX
    if error_class in (ErrorClass.CONFIGURATION, ErrorClass.PERMISSION):
        # missing key / access denied usually needs the user
        if re.search(r"(missing|no|not set).*(api.?key|credential|token)", str(text).lower()):
            return RetryStrategy.REQUIRES_USER
        return RetryStrategy.REQUIRES_FIX
    if error_class == ErrorClass.DEPENDENCY:
        return RetryStrategy.REQUIRES_FIX
    if error_class == ErrorClass.ENVIRONMENT:
        return RetryStrategy.EXTERNAL_BLOCKER
    if error_class == ErrorClass.PROVIDER:
        return RetryStrategy.RETRYABLE      # failover to another provider
    if error_class in (ErrorClass.GIT, ErrorClass.TOOL, ErrorClass.UNKNOWN):
        return RetryStrategy.RETRYABLE if attempts < 2 else RetryStrategy.REQUIRES_FIX
    return RetryStrategy.RETRYABLE


def extract_retry_after(text: str) -> Optional[float]:
    """Pull Retry-After seconds from an error string."""
    m = re.search(r"retry.?after[=:\s]+(\d+(?:\.\d+)?)", str(text).lower())
    if m:
        return float(m.group(1))
    return None


def diagnose(text: str, context: str = "", attempts: int = 1) -> ErrorDiagnosis:
    """Full diagnosis: class + strategy + wait + reason. One call."""
    cls, conf, patterns = classify_error(text, context)
    strat = retry_strategy(cls, text, attempts)
    wait = extract_retry_after(text) or (60.0 if strat == RetryStrategy.WAIT_AND_RETRY else 0.0)
    reason = {
        ErrorClass.RATE_LIMIT: "rate limited — wait for capacity, state preserved",
        ErrorClass.NETWORK: "transient network issue — retry with backoff",
        ErrorClass.CODE: "code error — fix the code before retrying",
        ErrorClass.TEST: "test failure — diagnose regression, fix, rerun",
        ErrorClass.BUILD: "build failure — fix compile error, rebuild",
        ErrorClass.CONFIGURATION: "configuration problem — fix config or provide key",
        ErrorClass.DEPENDENCY: "dependency problem — install/align dependency",
        ErrorClass.PERMISSION: "insufficient permission — needs user or config",
        ErrorClass.ENVIRONMENT: "environment missing required tool/service",
        ErrorClass.PROVIDER: "provider issue — retry or failover provider",
        ErrorClass.GIT: "git operation problem — inspect repo state",
        ErrorClass.TOOL: "tool execution problem — correct tool/args",
        ErrorClass.UNKNOWN: "unclassified — inspect full error",
    }[cls]
    return ErrorDiagnosis(cls, strat, conf, wait, reason, patterns)


REPEATED_FAILURE_ADVICE = (
    "Repeated identical failures detected (spec §17: do not blindly rerun). "
    "CHANGE STRATEGY: different tool, different arguments, or different approach."
)


def should_change_strategy(attempt: int, same_error_count: int,
                           strategy: RetryStrategy) -> bool:
    """Spec §17: detect repeated failures and force a strategy change."""
    if strategy in (RetryStrategy.REQUIRES_USER, RetryStrategy.EXTERNAL_BLOCKER):
        return False
    if same_error_count >= 3:
        return True
    if strategy == RetryStrategy.RETRYABLE and attempt >= 3:
        return True
    if strategy == RetryStrategy.REQUIRES_FIX and same_error_count >= 2:
        return True
    return False
