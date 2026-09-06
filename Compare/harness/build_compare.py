#!/usr/bin/env python3
"""Generate per-run human-readable trace.md files into Compare/ structure.

Structure: benchmark/Compare/<agent-dir>/<task-id>/{trace.md,trace.jsonl,proxy.jsonl,diff.patch,result.json}
Agent dirs: opencode/ openhands/ hermes/ shs-code/single-agent/ shs-code/multi-agent/
"""
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/benchmark")
from tasks import TASKS, CATEGORIES  # noqa: E402

RUNS = Path("/home/z/my-project/benchmark/runs")
COMPARE = Path("/home/z/my-project/benchmark/Compare")
SCORES = json.load(open("/home/z/my-project/benchmark/scores.json"))

AGENT_DIRS = {
    "opencode": "opencode",
    "openhands": "openhands",
    "hermes": "hermes",
    "shs-single": "shs-code/single-agent",
    "shs-multi": "shs-code/multi-agent",
    "shs-offline-single": "shs-offline/single-agent",
    "shs-offline-multi": "shs-offline/multi-agent",
}
AGENT_LABELS = {
    "opencode": "OpenCode 1.18.27",
    "openhands": "OpenHands CLI 1.13.1",
    "hermes": "Hermes Agent v0.21.0",
    "shs-single": "SHS Code v3.1.0 (single agent)",
    "shs-multi": "SHS Code v3.1.0 (multi-agent: PM/Architect/Engineer/QA)",
    "shs-offline-single": "SHS Code v3.1.0 OFFLINE (single agent, local 1B model)",
    "shs-offline-multi": "SHS Code v3.1.0 OFFLINE (multi-agent, local 1B model)",
}
SHS_LIKE = ("shs-single", "shs-multi", "shs-offline-single", "shs-offline-multi")

SECRET_RES = [
    re.compile(r"nvapi-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"Authorization: Bearer [A-Za-z0-9_\-\.]{20,}"),
]


def redact(text: str) -> str:
    for r in SECRET_RES:
        text = r.sub("[REDACTED]", text)
    return text


def parse_proxy(proxy_path: Path):
    reqs = []
    if not proxy_path.exists():
        return reqs
    for l in open(proxy_path):
        try:
            e = json.loads(l)
        except json.JSONDecodeError:
            continue
        if e.get("event") == "request":
            m = re.search(r'"model":"([^"]+)"', e.get("body", "") or "")
            reqs.append({"id": e.get("id"), "method": e.get("method"),
                         "path": e.get("path"), "model": m.group(1) if m else "",
                         "action": e.get("action")})
        elif e.get("event") == "response" and reqs:
            reqs[-1].update({"status": e.get("status"), "dur_s": e.get("dur_s"),
                             "bytes": e.get("bytes")})
        elif e.get("event") in ("injected_429", "injected_502") and reqs:
            reqs[-1]["injected"] = e["event"]
        elif e.get("event") == "paced_wait" and reqs:
            reqs[-1]["paced_wait_s"] = e.get("wait_s")
    return reqs


def render_task(task, agent):
    rd = RUNS / task["id"] / agent
    if not (rd / "result.json").exists():
        return None
    r = json.load(open(rd / "result.json"))
    sc = SCORES["scores"].get(f"{task['id']}/{agent}", {})

    trace_lines = []
    if (rd / "trace.jsonl").exists():
        for l in open(rd / "trace.jsonl"):
            try:
                e = json.loads(l)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "stream":
                t = redact(str(e.get("text", "")))
                trace_lines.append((e.get("ts"), t))

    # visible tool calls per CLI
    tool_events = []
    for ts, t in trace_lines:
        if agent == "opencode":
            m = re.search(r'"tool":"([^"]+)"', t)
            if m and "tool_use" in t:
                tool_events.append((ts, f"tool:{m.group(1)}"))
        elif agent in SHS_LIKE:
            if "Tool call:" in t:
                tool_events.append((ts, t.split("Tool call:")[1][:80]))
            elif "[TOOL]" in t:
                tool_events.append((ts, t[:80]))
        elif agent == "openhands":
            m = re.search(r'"action":"([^"]+)"', t)
            if m:
                tool_events.append((ts, f"action:{m.group(1)}"))
            elif "Running command" in t or "EXECUTED" in t.upper():
                tool_events.append((ts, t[:80]))
        elif agent == "hermes":
            if re.search(r"tool[_ ]call|Tool:|mcp_", t, re.I):
                tool_events.append((ts, t[:80]))

    proxy = parse_proxy(rd / "proxy.jsonl")
    p = r["proxy"]
    turns = r["turns"]

    md = []
    md.append(f"# {task['id']} — {task['title']}")
    md.append("")
    md.append(f"- **Agent**: {AGENT_LABELS[agent]}")
    md.append(f"- **Category**: {CATEGORIES[task['category']]}")
    port = {"opencode": 8391, "openhands": 8392, "hermes": 8393,
            "shs-single": 8394, "shs-multi": 8395,
            "shs-offline-single": 8396, "shs-offline-multi": 8397}[agent]
    if agent.startswith("shs-offline"):
        model_line = ("inference-optimization/Qwen3.8-1.0B-A0.6B — local CPU server "
                      f"on :8090 via forensic proxy :{port} (offline round; "
                      "random-init create-tiny-model artifact, see README)")
    else:
        model_line = (f"minimaxai/minimax-m3 via NVIDIA NIM "
                      f"(http://127.0.0.1:{port} forensic proxy)")
    md.append(f"- **Model**: {model_line}")
    md.append(f"- **Score**: {sc.get('score','?')}/10")
    md.append("")
    md.append("## Canonical task prompt")
    md.append("")
    for i, prompt in enumerate(task["turns"], 1):
        md.append(f"**Turn {i}:**")
        md.append("")
        md.append("```")
        md.append(prompt)
        md.append("```")
        md.append("")
    md.append("## Execution summary")
    md.append("")
    md.append(f"- Turn 1: wall **{turns['t1']['wall_s']}s**, exit `{turns['t1']['exit']}`, "
              f"{'KILLED (timeout)' if turns['t1']['killed'] else 'finished'}")
    if turns.get("t2", {}).get("wall_s"):
        md.append(f"- Turn 2: wall **{turns['t2']['wall_s']}s**, exit `{turns['t2']['exit']}`, "
                  f"{'KILLED (timeout)' if turns['t2']['killed'] else 'finished'}")
    md.append(f"- Model requests (wire-level, via forensic proxy): **{p['requests']}** "
              f"total, {p.get('chat_calls', 0)} chat calls")
    md.append(f"- Upstream results: {p['ok']} OK, {p['429']} HTTP 429, {p['502']} HTTP 502"
              + (f", {p['injected_429']} injected-429, {p['injected_502']} injected-502"
                 if (p.get("injected_429") or p.get("injected_502")) else ""))
    md.append(f"- Git: {r['git']['status_lines']} changed paths, "
              f"{r['git']['commits']} commits")
    md.append(f"- Visible tool calls in trace: {len(tool_events)}")
    if task["id"] == "task-25":
        models = sorted({q["model"] for q in proxy if q.get("model")})
        md.append(f"- Models observed on the wire: {models if models else 'see trace.jsonl'}")
    md.append("")
    md.append("## Model request log (wire-level)")
    md.append("")
    md.append("| # | method/path | model | status | dur | injected | paced-wait |")
    md.append("|---|-------------|-------|--------|-----|----------|------------|")
    for q in proxy[:40]:
        md.append(f"| {q.get('id','')} | {q.get('method','')} {q.get('path','')} | "
                  f"{q.get('model','') or '—'} | {q.get('status','—')} | "
                  f"{q.get('dur_s','—')}s | {q.get('injected','—')} | "
                  f"{q.get('paced_wait_s','—')} |")
    if len(proxy) > 40:
        md.append(f"| … | ({len(proxy)-40} more in proxy.jsonl) | | | | | |")
    md.append("")
    if tool_events:
        md.append("## Tool calls (as visible in CLI output)")
        md.append("")
        for ts, t in tool_events[:60]:
            md.append(f"- `[{ts}s]` {redact(t)}")
        if len(tool_events) > 60:
            md.append(f"- … ({len(tool_events)-60} more, see trace.jsonl)")
        md.append("")
    md.append("## Final verification")
    md.append("")
    md.append("```json")
    md.append(redact(json.dumps(r["checks"], indent=1, default=str)))
    md.append("```")
    if r.get("gh"):
        md.append("")
        md.append("**GitHub post-hoc check (gh api):**")
        md.append("```")
        md.append(redact(json.dumps(r["gh"], indent=1)))
        md.append("```")
    md.append("")
    md.append(f"**Score justification:** {sc.get('note','')}")
    md.append("")
    md.append("## Artifacts")
    md.append("")
    md.append("- `trace.jsonl` — full CLI stdout/stderr stream with timestamps")
    md.append("- `proxy.jsonl` — wire-level request/response log (secrets redacted)")
    md.append("- `diff.patch` — cumulative git diff of the agent's repository changes")
    md.append("- `result.json` — machine-readable metrics + verification")
    return "\n".join(md)


def main():
    for task in TASKS:
        for agent, adir in AGENT_DIRS.items():
            md = render_task(task, agent)
            if md is None:
                continue
            out = COMPARE / adir / task["id"]
            out.mkdir(parents=True, exist_ok=True)
            (out / "trace.md").write_text(md)
            rd = RUNS / task["id"] / agent
            for fname in ("trace.jsonl", "proxy.jsonl", "diff.patch", "result.json"):
                src = rd / fname
                if src.exists():
                    txt = redact(src.read_text(errors="replace"))
                    (out / fname).write_text(txt)
    print("Compare/ per-task traces generated:",
          sum(1 for _ in COMPARE.rglob("trace.md")), "trace.md files")


if __name__ == "__main__":
    main()
