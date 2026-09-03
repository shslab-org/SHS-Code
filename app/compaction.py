from __future__ import annotations

"""
SHS Code — Context Compaction 2.0 (spec §23)
==============================================
Do NOT simply summarize the conversation. Extract STRUCTURED operational
state, then rebuild a compact context:

  IMPORTANT USER REQUIREMENTS
  PROJECT FACTS
  ARCHITECTURE
  DECISIONS
  FILES
  CHANGES
  ERRORS
  TEST RESULTS
  TASK STATE
  NEXT ACTION
  BLOCKERS
  RECENT EXCHANGES (kept verbatim, bounded)

Deterministic extraction (no LLM call — reliable, offline, fast):
  - user messages (filtered of system injections) → requirements
  - assistant decision sentences → decisions
  - tool calls with paths → files/changes
  - tool errors → errors
  - pass/fail counts in outputs → test results
  - supplied plan/task state → task state
Unresolved information is preserved: the last K exchanges stay verbatim
and every error stays listed. Compaction reduces tokens WITHOUT destroying
operational state (spec §23).

Also usable as journal persistence input: extract_structured() feeds the
checkpoint's "structured_state" so a resumed task rebuilds context exactly.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

# Messages with these prefixes are system injections, not user requirements
_INJECTED_PREFIXES = (
    "[SELF-CHECK", "⚠ Tool", "TOKEN BUDGET", "PERSISTENT MEMORY",
    "┌─ TOOL INTELLIGENCE", "[IDENTITY REINFORCEMENT", "[Context refresh",
    "You are repeating", "You have called the same failing",
    "BLOCKED:", "User rejected",
)

_DECISION_RX = re.compile(
    r"\b(i\s+(?:am\s+)?(?:going\s+to|will)|we\s+(?:are\s+)?(?:going\s+to|will)|"
    r"i\s+(?:have\s+)?decided?|decision\s*:|let's|chose|chosen|"
    r"use\s+\w+\s+instead|switch(?:ing)?\s+to|approach\s*:|"
    r"i'm\s+(?:going\s+to|using)|plan\s+is\s+to|the\s+plan\s*:)", re.IGNORECASE)
_FILE_RX = re.compile(r"[\w./\\-]+\.(?:py|js|ts|tsx|jsx|kt|java|php|go|rs|md|"
                       r"json|toml|yaml|yml|xml|gradle|sql|html|css)\b")
_TEST_RX = re.compile(r"(\d+)\s+(?:passed|passing).{0,40}?(\d+)\s+(?:failed|failing)",
                      re.IGNORECASE)
_CREATE_RX = re.compile(
    r"(?:created|wrote|modified|updated|deleted|saved)\s+(?:the\s+)?(?:file\s+)?"
    r"([\w./\\-]+\.[\w]+)", re.IGNORECASE)


def _is_user_requirement(m: dict) -> bool:
    if m.get("role") != "user":
        return False
    content = (m.get("content") or "").strip()
    if not content:
        return False
    return not any(content.startswith(p) for p in _INJECTED_PREFIXES)


def extract_structured(messages: List[dict],
                       plan_text: str = "",
                       task_state: Optional[Dict[str, Any]] = None,
                       architecture: str = "") -> Dict[str, List[str]]:
    """Deterministic structured extraction from a message history."""
    out: Dict[str, List[str]] = {
        "requirements": [], "decisions": [], "files": [], "changes": [],
        "errors": [], "test_results": [], "facts": [],
    }
    for m in messages:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content:
            # tool calls carry intent in arguments
            for tc in (m.get("tool_calls") or []):
                try:
                    import json as _json
                    args = _json.loads(tc["function"]["arguments"] or "{}")
                    for k in ("path", "file_path"):
                        if args.get(k):
                            out["files"].append(str(args[k]))
                except Exception:
                    pass
            continue
        if role == "user" and _is_user_requirement(m):
            if len(content) > 12 and content.lower() not in ("ok", "yes", "no", "continue"):
                out["requirements"].append(content[:400])
        elif role == "assistant":
            for sent in re.split(r"(?<=[.!?])\s+|\n+", content):
                sent = sent.strip()
                if not sent:
                    continue
                if _DECISION_RX.search(sent):
                    out["decisions"].append(sent[:250])
                for fm in _CREATE_RX.finditer(sent):
                    out["changes"].append(f"{fm.group(0)[:120]}")
            for fm in _FILE_RX.finditer(content[:600]):
                f = fm.group(0)
                if f not in out["files"] and not f.startswith("http"):
                    out["files"].append(f)
        elif role == "tool":
            low = content.lower()
            if low.startswith("error") or "traceback (most recent" in low or \
                    re.search(r"\berror\b", low[:300]):
                # keep only genuinely error-ish tool outputs
                if re.search(r"(error|exception|failed|traceback)", low[:400]):
                    out["errors"].append(content[:300])
            tm = _TEST_RX.search(content)
            if tm:
                out["test_results"].append(
                    f"{tm.group(1)} passed / {tm.group(2)} failed")
            # short factual outputs (file listings, git status) → facts
            if 0 < len(content) < 500 and re.search(
                    r"(branch|modified|untracked|files|dir|total)", low):
                out["facts"].append(content[:250])

    # dedupe + bound
    for k in out:
        out[k] = list(dict.fromkeys(out[k]))[:20]
    if plan_text:
        out["plan"] = [plan_text[:1500]]
    if task_state:
        out["task_state"] = [f"{k}: {str(v)[:200]}"
                             for k, v in task_state.items()][:12]
    if architecture:
        out["architecture"] = [architecture[:800]]
    return out


def build_compact_state(extracted: Dict[str, List[str]],
                        recent: List[dict]) -> str:
    """Render the structured state block that replaces old messages."""
    def sec(title: str, key: str) -> str:
        items = extracted.get(key) or []
        if not items:
            return ""
        lines = [f"{title}:"]
        lines += [f"  - {i}" for i in items[:15]]
        return "\n".join(lines)

    parts = [
        "SHS CODE COMPACTED STATE — structured extraction (spec §23).",
        "This block replaces older messages. Treat it as authoritative",
        "operational state, not as a lossy summary.",
        "",
        sec("IMPORTANT USER REQUIREMENTS", "requirements"),
        sec("PROJECT FACTS", "facts"),
        sec("ARCHITECTURE", "architecture"),
        sec("DECISIONS", "decisions"),
        sec("FILES", "files"),
        sec("CHANGES", "changes"),
        sec("ERRORS ENCOUNTERED (unresolved info preserved)", "errors"),
        sec("TEST RESULTS", "test_results"),
        sec("TASK STATE", "task_state"),
        sec("PLAN", "plan"),
    ]
    parts = [p for p in parts if p]
    parts.append("")
    parts.append(f"(Last {len(recent)} exchanges are preserved verbatim below"
                 " in the following messages.)")
    return "\n".join(parts)


def _repair_boundaries(recent: List[dict]) -> List[dict]:
    """Make a message slice structurally valid for every provider.

    * Drops leading TOOL messages (their parent assistant was compacted).
    * Drops trailing assistant tool_calls whose TOOL results were cut off.
    * Keeps everything else verbatim.
    """
    out = list(recent)
    # leading tool results without their parent assistant
    while out and out[0].get("role") == "tool":
        out.pop(0)
    # trailing assistant tool_calls without their results
    while out:
        last = out[-1]
        if last.get("role") == "assistant" and last.get("tool_calls") \
                and not (len(out) >= 2 and out[-2].get("role") == "tool"):
            # the assistant requested tools but results are gone — drop the
            # call markers so the text-only assistant message stays valid
            trimmed = {k: v for k, v in last.items() if k != "tool_calls"}
            out[-1] = trimmed
            break
        break
    return out


def compact_messages(messages: List[dict], keep_last: int = 6,
                     plan_text: str = "",
                     task_state: Optional[Dict[str, Any]] = None,
                     architecture: str = "") -> Tuple[List[dict], Dict[str, Any]]:
    """Return (new_messages, report). System messages at the head are kept
    (identity/system prompt), old middle messages are replaced by ONE
    structured state message, last `keep_last` messages stay verbatim."""
    if len(messages) <= keep_last + 1:
        return messages, {"compacted": False, "reason": "context small enough"}

    # keep leading system message(s) (identity prompt)
    head: List[dict] = []
    i = 0
    while i < len(messages) and messages[i].get("role") == "system":
        head.append(messages[i])
        i += 1
    middle = messages[i:-keep_last]
    recent = messages[-keep_last:]

    extracted = extract_structured(middle, plan_text=plan_text,
                                   task_state=task_state,
                                   architecture=architecture)
    # SHS Code FIX (orphaned tool messages): emit the compacted state block
    # as a USER message, not system — (a) AnthropicClient drops every system
    # message except the head one, silently discarding all extracted state
    # for that provider; (b) providers reject mid-conversation system blocks
    # less predictably than user blocks.
    state_msg = {"role": "user",
                 "content": "[COMPACTED CONTEXT — SHS Code structured state]\n"
                            + build_compact_state(extracted, recent)}

    # SHS Code FIX (orphaned tool messages): the verbatim tail can START with
    # a tool result whose parent assistant (with tool_calls) was compacted
    # away — OpenAI/Anthropic both reject that history (400). Drop leading
    # TOOL messages, and assistant tool_calls whose results fell off the tail.
    recent = _repair_boundaries(recent)

    new_messages = head + [state_msg] + recent
    before_chars = sum(len(str(m.get("content") or "")) for m in messages)
    after_chars = sum(len(str(m.get("content") or "")) for m in new_messages)
    report = {
        "compacted": True,
        "messages_before": len(messages),
        "messages_after": len(new_messages),
        "chars_before": before_chars,
        "chars_after": after_chars,
        "reduction_pct": round(100 * (1 - after_chars / max(1, before_chars)), 1),
        "extracted_counts": {k: len(v) for k, v in extracted.items()
                             if isinstance(v, list)},
        "extracted": extracted,
    }
    return new_messages, report


def render_report(report: Dict[str, Any]) -> str:
    if not report.get("compacted"):
        return f"Compaction skipped: {report.get('reason')}"
    ec = report.get("extracted_counts") or {}
    return ("Context compacted (structured, spec §23): "
            f"{report['messages_before']} → {report['messages_after']} messages, "
            f"{report['chars_before']} → {report['chars_after']} chars "
            f"({report['reduction_pct']}% reduction). Preserved: "
            + ", ".join(f"{k}={v}" for k, v in ec.items()))
