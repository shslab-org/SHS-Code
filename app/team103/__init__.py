"""SHS Code v4.0 — 103-agent architecture: 1 PM + 1 Architect + 100 dynamic Engineer workers + 1 QA.

Lightweight workers, bounded concurrency, lazy activation, reuse,
cancellation, task-specific context. NOT 103 full LLM loops.
"""
from app.team103.scheduler import Team103, TeamConfig, TeamResult
__all__ = ["Team103", "TeamConfig", "TeamResult"]
