"""SHS Code v4.0 — production wiring (OPT-1..20 -> live agent).

Single import point that binds the 20 isolated v4 modules into the live
agent without uncontrolled rewrites. All helpers are additive, lazy, and
reversible. Live paths call these helpers; v4 modules stay testable alone.

  from app.v4.wiring import (
      get_prefix_cache, get_semantic_cache, get_prefetcher,
      get_model_router, get_plan_cache, get_event_log,
      plan_with_cache, verify_with_risk, repair_tool_args,
  )
"""
from __future__ import annotations
import asyncio
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_singletons: Dict[str, Any] = {}

def get_prefix_cache():
    from app.v4.prefix_cache import PrefixCache
    return _singletons.setdefault("prefix", PrefixCache())

def get_semantic_cache():
    from app.v4.semantic_cache import SemanticCache
    threshold = float(os.getenv("SHSCODE_SEMCACHE_THRESHOLD", "0.82"))
    sc = _singletons.get("semcache")
    if sc is None:
        sc = SemanticCache(threshold=threshold)
        _singletons["semcache"] = sc
    return sc

def get_prefetcher():
    from app.v4.prefetch import BackgroundPrefetcher
    return _singletons.setdefault("prefetch", BackgroundPrefetcher())

def get_model_router():
    from app.v4.model_router import ModelRouter
    mode = os.getenv("SHSCODE_MODEL_MODE", "production")
    rt = _singletons.get("router")
    if rt is None:
        rt = ModelRouter(mode=mode if mode in ("benchmark", "production") else "production")
        _singletons["router"] = rt
    return rt

def get_plan_cache():
    from app.v4.plan_cache import PlanCache
    return _singletons.setdefault("plancache", PlanCache())

def get_event_log(path: str = "workspace/v4/agent_events.jsonl"):
    from app.v4.async_log import AsyncEventLog
    key = f"eventlog:{path}"
    if key not in _singletons:
        _singletons[key] = AsyncEventLog(path)
    return _singletons[key]

def get_browser_pool():
    from app.v4.browser_pool import BrowserPool
    max_b = int(os.getenv("SHSCODE_BROWSER_POOL", "4"))
    pool = _singletons.get("browserpool")
    if pool is None:
        pool = BrowserPool(max_browsers=max_b)
        _singletons["browserpool"] = pool
    return pool

def get_dedup():
    from app.v4.dedup import DedupRegistry
    return _singletons.setdefault("dedup", DedupRegistry())

def get_tiered_memory(db_path: str = "workspace/.memory/tiered.db"):
    from app.v4.memory_tiers import TieredMemory
    key = f"tiered:{db_path}"
    if key not in _singletons:
        _singletons[key] = TieredMemory(db_path=db_path)
    return _singletons[key]

def get_intel_memory():
    from app.v4.intel_memory import IntelligentMemory
    return _singletons.setdefault("intelmem", IntelligentMemory())

def get_speculative():
    from app.v4.speculative import SpeculativeExecutor
    return _singletons.setdefault("spec", SpeculativeExecutor())

def get_stream_parser():
    from app.v4.stream_parser import StreamToolParser
    # parsers are per-stream; return factory
    from app.v4.stream_parser import StreamToolParser as P
    return P()

# --- OPT-4: DAG-aware parallel tool dispatch (read-only fan-out, write serial) ---
async def dispatch_tools_dag(tasks, runner, limit: int = 8):
    from app.v4.parallel_tools import dispatch
    return await dispatch(tasks, runner, limit=limit)

def make_tool_tasks(calls):
    """Adapt (name, args, tc_id) triples to OPT-4 ToolTasks (no deps = full fan-out)."""
    from app.v4.parallel_tools import ToolTask
    return [ToolTask(id=tc_id or f"t{i}", name=n, args=a or {}) for i, (n, a, tc_id) in enumerate(calls)]

# --- OPT-12: plan cache wrapper (planner overhead) ---
def plan_cache_key(goal: str, project_hint: str, state_fingerprint: str) -> Optional[List[Dict[str, Any]]]:
    try:
        return get_plan_cache().get(goal, project_hint, state_fingerprint)
    except Exception:
        return None

def plan_cache_put(goal: str, project_hint: str, state_fingerprint: str, plan: List[Dict[str, Any]]):
    try:
        get_plan_cache().put(goal, project_hint, state_fingerprint, plan)
    except Exception:
        pass

# --- OPT-13: risk-aware verification wrapper ---
def risk_tier_for(changed_files: List[str], diff_size: int = 0, touches_core: bool = False) -> str:
    from app.v4.risk_verify import risk_of
    try:
        return risk_of(changed_files, diff_size, touches_core)
    except Exception:
        return "medium"

def kinds_for_risk_tier(risk: str, milestone: bool = False) -> List[str]:
    from app.v4.risk_verify import kinds_for_risk
    try:
        return kinds_for_risk(risk, milestone)
    except Exception:
        return ["build", "test"]

# --- OPT-14: malformed JSON repair (H4) ---
def repair_tool_args(text: str) -> Optional[Any]:
    from app.v4.recovery import repair_json
    try:
        return repair_json(text)
    except Exception:
        return None

async def retry_with_backoff(fn: Callable[[], Any], attempts: int = 5, base_s: float = 0.5):
    from app.v4.recovery import retry_async
    return await retry_async(fn, attempts=attempts, base_s=base_s)

# --- OPT-7: background prefetch ---
def start_project_prefetch(root: str | Path = "."):
    """Fire-and-forget background refresh of intel index + git + profile."""
    root_p = Path(root)
    jobs: Dict[str, Callable[[], Any]] = {}
    def _intel():
        try:
            from app.intelligence import get_intelligence
            intel = get_intelligence(root_p)
            return intel.ensure_indexed()
        except Exception as e:
            return {"error": str(e)[:200]}
    def _git():
        try:
            from app.intelligence.project import git_state
            return git_state(root_p)
        except Exception as e:
            return {"error": str(e)[:200]}
    jobs["intel"] = _intel
    jobs["git"] = _git
    try:
        get_prefetcher().start(jobs)
    except RuntimeError:
        # no running loop (sync context) — run inline cheap path
        pass

# --- OPT-10: context helpers (re-export with stable names) ---
def summarize_tool_output(ref: str, text: str, budget: int = 4000):
    from app.v4.context_mgmt import summarize_output
    return summarize_output(ref, text, budget=budget)

# --- OPT-16: structured event emit (async, buffered) ---
def emit_event(task_id: str, worker_id: str, correlation_id: str, tool: str, detail: str,
               path: str = "workspace/v4/agent_events.jsonl"):
    try:
        get_event_log(path).emit(task_id, worker_id, correlation_id, tool, detail)
    except Exception:
        pass

def wiring_stats() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in _singletons.items():
        try:
            if hasattr(v, "stats"):
                out[k] = v.stats()
            elif hasattr(v, "metrics"):
                out[k] = v.metrics.to_dict() if hasattr(v.metrics, "to_dict") else str(v.metrics)
            else:
                out[k] = type(v).__name__
        except Exception as e:
            out[k] = f"stats-error: {e}"
    return out

# --- 103-agent team: live entry (PM->Architect->100 Engineers->QA) ---
def get_team103(engine_fn=None, **cfg_kw):
    """Lazy Team103 factory. engine_fn required on first use; cached per engine."""
    from app.team103.scheduler import Team103, TeamConfig
    key = f"team103:{id(engine_fn)}:{sorted(cfg_kw.items())}"
    if key not in _singletons:
        cfg = TeamConfig(**{k: v for k, v in cfg_kw.items() if hasattr(TeamConfig, k)})
        if engine_fn is None:
            # default engine: single SHSCode agent per TaskSpec (bounded, journaled)
            async def _default_engine(spec, wid):
                from app.agent.shscode import SHSCode
                from app.v4.merger import WorkerResult
                try:
                    agent = SHSCode()
                    out = await agent.run(f"{spec.title}\nContext: {spec.context_slice[:2000]}\nFiles: {','.join(spec.files[:5])}")
                    return WorkerResult(wid, list(spec.files), [], out[:3000], [], [], 0.75)
                except Exception as e:
                    from app.v4.merger import WorkerResult as _WR
                    return _WR(wid, [], [], f"error: {e}", [], [spec.title], 0.2)
            engine_fn = _default_engine
        _singletons[key] = Team103(engine_fn, cfg)
    return _singletons[key]

async def run_team103(goal: str, specs=None, engine_fn=None, correlation_id=None, **cfg_kw):
    """One-call Team103 run: PM decompose -> Architect waves -> Engineers -> QA gate."""
    team = get_team103(engine_fn, **cfg_kw)
    return await team.run(goal, specs=specs, correlation_id=correlation_id)
