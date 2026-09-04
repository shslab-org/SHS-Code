#!/usr/bin/env python3
"""Forensic benchmark harness — runs identical tasks across 5 agent configs.

Every agent: same model (minimaxai/minimax-m3 via NVIDIA NIM), same task prompt,
same starting repo state, same time budget. Each agent routes through its own
local forensic proxy (wire-level trace capture + fault injection for R2/R3).

Run inside a single tool call per batch:  python3 harness.py run task-01 task-02 ...
Outputs: benchmark/runs/<task>/<agent>/{trace.jsonl,proxy.jsonl,diff.patch,result.json}
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/benchmark")
from tasks import TASKS  # noqa: E402

BASE = Path("/home/z/my-project/benchmark")
RUNS = BASE / "runs"
TEMPLATE = BASE / "template"
PROXY_SCRIPT = "/home/z/my-project/scripts/bench_proxy.py"
SHS_DIR = "/home/z/my-project/SHS-Code"
NIM_KEY = None
for line in open("/home/z/my-project/SHS-Code/.env"):
    if line.startswith("LLM_API_KEY="):
        NIM_KEY = line.strip().split("=", 1)[1]

SECRET_RES = [
    re.compile(r"nvapi-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
]


def redact(text: str) -> str:
    for r in SECRET_RES:
        text = r.sub("[REDACTED]", text)
    return text


AGENT_PORTS = {
    "opencode": 8391,
    "openhands": 8392,
    "hermes": 8393,
    "shs-single": 8394,
    "shs-multi": 8395,
}
AGENTS = ["opencode", "openhands", "hermes", "shs-single", "shs-multi"]
SWITCH_MODEL = {
    "opencode": "nim/openai/gpt-oss-20b",
    "openhands": "openai/openai/gpt-oss-20b",
    "hermes": "openai/gpt-oss-20b",
    "shs-single": "openai/gpt-oss-20b",
    "shs-multi": "openai/gpt-oss-20b",
}


def base_env(agent: str, port: int, extra: dict | None = None) -> dict:
    e = dict(os.environ)
    e["PATH"] = "/home/z/.local/bin:/home/z/.npm-global/bin:/home/z/.venv/bin:" + e.get("PATH", "")
    e["HOME"] = "/home/z"
    e["LLM_API_KEY"] = NIM_KEY
    e["NVIDIA_API_KEY"] = NIM_KEY
    e["NVIDIA_BASE_URL"] = f"http://127.0.0.1:{port}"
    e["LLM_BASE_URL"] = f"http://127.0.0.1:{port}"
    e["LLM_MODEL"] = "openai/minimaxai/minimax-m3"
    e["GH_TOKEN"] = "[REDACTED-GITHUB-TOKEN]"
    e["GITHUB_USER"] = "shslab-org"
    e["GIT_TERMINAL_PROMPT"] = "0"
    e["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    e["OPENCODE_DISABLE_TELEMETRY"] = "1"
    if extra:
        e.update(extra)
    return e


def build_cmd(agent: str, prompt: str, workdir: str, turn2: bool = False,
              new_session: bool = False, model_switch: bool = False,
              session_ref: str | None = None) -> list[str]:
    if agent == "opencode":
        cmd = ["opencode", "run", prompt, "--format", "json"]
        if turn2 and not new_session:
            cmd.append("--continue")
        if model_switch:
            cmd += ["--model", SWITCH_MODEL[agent]]
        return cmd
    if agent == "openhands":
        cmd = ["/home/z/.venv-openhands/bin/openhands", "--headless", "--json",
               "--override-with-envs"]
        if turn2 and not new_session:
            cmd += ["--resume", session_ref or "--last"]
        cmd += ["-t", prompt]
        return cmd
    if agent == "hermes":
        cmd = ["/home/z/.local/bin/hermes", "-z", prompt, "--yolo"]
        if turn2 and not new_session:
            cmd.append("--continue")
        if model_switch:
            cmd += ["-m", SWITCH_MODEL[agent]]
        return cmd
    if agent == "shs-single":
        cmd = ["/home/z/.venv/bin/shscode", "--no-color"]
        if model_switch:
            cmd += ["--model", SWITCH_MODEL[agent]]
        cmd.append(prompt)
        return cmd
    if agent == "shs-multi":
        return ["/home/z/.venv/bin/python3", f"{SHS_DIR}/run_multi_agent.py", prompt]
    raise ValueError(agent)


def run_turn(agent: str, prompt: str, workdir: str, out_dir: Path, proxy_log: Path,
             timeout: float, kill_at: float | None, turn2=False, new_session=False,
             model_switch=False, session_ref=None, task_env=None):
    """Run one CLI turn, capture trace, return (exit_code, killed, wall, session_ref, final_text)."""
    trace_fh = open(out_dir / "trace.jsonl", "a")
    start = time.time()

    def emit(ev: dict):
        ev["ts"] = round(time.time() - start, 2)
        trace_fh.write(redact(json.dumps(ev, default=str)) + "\n")
        trace_fh.flush()

    emit({"event": "turn_start", "agent": agent, "prompt": prompt,
          "turn2": turn2, "model_switch": model_switch, "timeout": timeout})

    env = base_env(agent, AGENT_PORTS[agent], task_env)
    if model_switch and agent == "openhands":
        env["LLM_MODEL"] = SWITCH_MODEL[agent]
    if model_switch and agent == "shs-multi":
        env["LLM_MODEL_OVERRIDE"] = SWITCH_MODEL[agent]

    cmd = build_cmd(agent, prompt, workdir, turn2, new_session, model_switch, session_ref)
    env["PWD"] = workdir  # opencode resolves project config via PWD, not cwd
    emit({"event": "spawn", "cmd": redact(" ".join(cmd))[:500], "cwd": workdir})

    proc = subprocess.Popen(
        cmd, cwd=workdir, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True,
        text=True, errors="replace", bufsize=1)

    killed = False
    final_lines = []

    def reader():
        for line in proc.stdout:
            line = line.rstrip("\n")
            emit({"event": "stream", "stream": "out", "text": redact(line)})
            if line.strip():
                final_lines.append(line)

    rt = threading.Thread(target=reader, daemon=True)
    rt.start()

    deadline = start + timeout
    kill_deadline = start + kill_at if kill_at else None
    while True:
        ret = proc.poll()
        if ret is not None:
            break
        now = time.time()
        if kill_deadline and now >= kill_deadline:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                killed = True
                emit({"event": "injected_kill", "at_s": round(now - start, 1)})
            except ProcessLookupError:
                pass
            break
        if now >= deadline:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                killed = True
                emit({"event": "timeout_kill", "at_s": round(now - start, 1)})
            except ProcessLookupError:
                pass
            break
        time.sleep(0.5)

    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)

    rt.join(timeout=10)
    wall = round(time.time() - start, 1)

    session_ref = None
    for l in final_lines:
        m = re.search(r"Conversation ID:\s*([0-9a-f\-]{36})", l)
        if m:
            session_ref = m.group(1)

    emit({"event": "turn_end", "exit_code": proc.returncode, "killed": killed,
          "wall_s": wall})
    trace_fh.close()
    return proc.returncode, killed, wall, session_ref, "\n".join(final_lines[-25:])


def proxy_stats(proxy_log: Path) -> dict:
    stats = {"requests": 0, "responses": 0, "ok": 0, "429": 0, "502": 0,
             "injected_429": 0, "injected_502": 0, "errors": 0, "chat_calls": 0,
             "total_wait_events": 0}
    if not proxy_log.exists():
        return stats
    for line in open(proxy_log):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        ev = e.get("event")
        if ev == "request":
            stats["requests"] += 1
            if e.get("path", "").endswith("chat/completions"):
                stats["chat_calls"] += 1
        elif ev == "response":
            stats["responses"] += 1
            s = e.get("status")
            if s == 200:
                stats["ok"] += 1
            elif s == 429:
                stats["429"] += 1
            elif s == 502:
                stats["502"] += 1
        elif ev == "injected_429":
            stats["injected_429"] += 1
        elif ev == "injected_502":
            stats["injected_502"] += 1
        elif ev == "proxy_error":
            stats["errors"] += 1
    return stats


def run_agent_task(task, agent: str, proxy_mode: str):
    """Full task pipeline for one agent: turns + artifacts + verify + result.json."""
    out_dir = RUNS / task["id"] / agent
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir = out_dir / "repo"
    if workdir.exists():
        shutil.rmtree(workdir)
    shutil.copytree(TEMPLATE, workdir)
    subprocess.run(["git", "checkout", "-q", "-- ."], cwd=workdir, capture_output=True)
    # clean untracked from template runs
    subprocess.run(["git", "clean", "-qfdx"], cwd=workdir, capture_output=True)

    # opencode per-workdir config: route to this agent's proxy port
    if agent == "opencode":
        (workdir / "opencode.json").write_text(json.dumps({
            "provider": {"nim": {"options": {
                "baseURL": f"http://127.0.0.1:{AGENT_PORTS[agent]}"}}}}))

    # start dedicated proxy for this agent (this round)
    proxy_log = out_dir / "proxy.jsonl"
    if proxy_log.exists():
        proxy_log.unlink()
    port = AGENT_PORTS[agent]
    # fair-share pacing in passthrough mode: the shared NIM per-model limit
    # (~10 RPM effective, burst ~2-3) is oversubscribed by 5 concurrent agents;
    # pacing divides capacity equally so capability tasks measure capability.
    # Fault-injection rounds (Cat 5) run UNPACED to measure raw retry behavior.
    pace = "34" if proxy_mode == "passthrough" else "0"
    proxy = None
    for attempt in range(3):
        proxy = subprocess.Popen(
            ["/home/z/.venv/bin/python3", PROXY_SCRIPT,
             "--port", str(port), "--mode", proxy_mode,
             "--n", "2", "--m", "3", "--pace", pace,
             "--log", str(proxy_log)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        time.sleep(1.5)
        # our proxy must be alive (a bind failure kills it) and port accepting
        try:
            import socket
            s = socket.create_connection(("127.0.0.1", port), timeout=3)
            s.close()
            if proxy.poll() is None:
                break  # our proxy owns the port
        except OSError:
            pass
        # our proxy died (bind conflict with stale holder) or port dead — kill stale, retry
        print(f"  [WARN] port {port} conflict (stale holder?) — killing and retrying", flush=True)
        subprocess.run(["pkill", "-9", "-f", f"bench_proxy.py"], capture_output=True)
        try:
            proxy.kill()
        except Exception:
            pass
        time.sleep(1.5)
    else:
        raise RuntimeError(f"could not bind proxy for {agent} on port {port}")

    kind = task["kind"]
    t1_timeout = task["timeout"]
    t2_timeout = min(task["timeout"], 150)
    kill_at = None
    session_ref = None
    t1_exit = t2_exit = None
    t1_killed = t2_killed = False
    t1_wall = t2_wall = 0.0

    prompts = task["turns"]
    task_env = dict(task.get("extra_env") or {})
    if task["id"] == "task-17":
        prompts = [p.replace("{REPO_NAME}", f"bench-{agent}") for p in prompts]

    if kind == "single":
        t1_exit, t1_killed, t1_wall, session_ref, _ = run_turn(
            agent, prompts[0], str(workdir), out_dir, proxy_log,
            t1_timeout, None, task_env=task_env)
    elif kind in ("two-turn", "two-turn-newsession"):
        new_session = kind == "two-turn-newsession"
        t1_exit, t1_killed, t1_wall, session_ref, _ = run_turn(
            agent, prompts[0], str(workdir), out_dir, proxy_log,
            t1_timeout, None, task_env=task_env)
        t2_exit, t2_killed, t2_wall, _, _ = run_turn(
            agent, prompts[1], str(workdir), out_dir, proxy_log,
            t2_timeout, None, turn2=True, new_session=new_session,
            model_switch=(task["id"] == "task-25"), session_ref=session_ref,
            task_env=task_env)
    elif kind == "two-turn-kill":
        kill_at = 70.0
        t1_exit, t1_killed, t1_wall, session_ref, _ = run_turn(
            agent, prompts[0], str(workdir), out_dir, proxy_log,
            t1_timeout, kill_at, task_env=task_env)
        time.sleep(3)
        t2_exit, t2_killed, t2_wall, _, _ = run_turn(
            agent, prompts[1], str(workdir), out_dir, proxy_log,
            t2_timeout, None, turn2=True, session_ref=session_ref,
            task_env=task_env)

    # stop proxy
    try:
        os.killpg(os.getpgid(proxy.pid), signal.SIGKILL)
    except ProcessLookupError:
        proxy.terminate()

    # artifacts: git status + diff
    subprocess.run(["git", "add", "-A"], cwd=workdir, capture_output=True)
    diff = subprocess.run(["git", "diff", "HEAD"], cwd=workdir,
                          capture_output=True, text=True).stdout
    status = subprocess.run(["git", "status", "--porcelain"], cwd=workdir,
                            capture_output=True, text=True).stdout
    (out_dir / "diff.patch").write_text(redact(diff))
    glog = subprocess.run(["git", "log", "--oneline"], cwd=workdir,
                          capture_output=True, text=True).stdout

    # verification
    try:
        checks = task["verify"](str(workdir))
    except Exception as e:
        checks = {"verify_error": str(e)[:300]}

    # GitHub task post-hoc verification
    gh_check = None
    if task["id"] == "task-17":
        repo_name = f"bench-{agent}"
        rc = subprocess.run(
            ["gh", "api", f"repos/shslab-org/{repo_name}", "-q", ".private,.html_url"],
            capture_output=True, text=True,
            env={"PATH": "/home/z/.local/bin:" + os.environ["PATH"],
                 "GH_TOKEN": "[REDACTED-GITHUB-TOKEN]"})
        iss = subprocess.run(
            ["gh", "api", f"repos/shslab-org/{repo_name}/issues", "-q", ".[0].number,.[0].title"],
            capture_output=True, text=True,
            env={"PATH": "/home/z/.local/bin:" + os.environ["PATH"],
                 "GH_TOKEN": "[REDACTED-GITHUB-TOKEN]"})
        gh_check = {"repo_api": rc.stdout.strip() or rc.stderr.strip()[:120],
                    "issue_api": iss.stdout.strip() or iss.stderr.strip()[:120]}

    result = {
        "task": task["id"], "agent": agent, "title": task["title"],
        "category": task["category"],
        "turns": {"t1": {"exit": t1_exit, "killed": t1_killed, "wall_s": t1_wall},
                  "t2": {"exit": t2_exit, "killed": t2_killed, "wall_s": t2_wall}},
        "proxy": proxy_stats(proxy_log),
        "git": {"status_lines": len(status.strip().splitlines()) if status.strip() else 0,
                "commits": len(glog.strip().splitlines()) if glog.strip() else 0},
        "gh": gh_check,
        "checks": checks,
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=1, default=str))
    return result


def run_round(task_id: str) -> list[dict]:
    task = next(t for t in TASKS if t["id"] == task_id)
    idx = TASKS.index(task)
    proxy_mode = "passthrough"
    if task.get("extra_env", {}).get("PROXY_MODE") == "fault502":
        proxy_mode = "fault502"
    elif task.get("extra_env", {}).get("PROXY_MODE") == "rate429":
        proxy_mode = "rate429"

    order = AGENTS[idx % 5:] + AGENTS[:idx % 5]
    print(f"[round {task_id}] mode={proxy_mode} order={order}", flush=True)

    results = {}
    threads = []

    def launch(a, delay):
        def go():
            time.sleep(delay)
            try:
                results[a] = run_agent_task(task, a, proxy_mode)
                r = results[a]
                print(f"  [{task_id}/{a}] done t1={r['turns']['t1']['wall_s']}s "
                      f"t2={r['turns']['t2']['wall_s']}s reqs={r['proxy']['requests']} "
                      f"429={r['proxy']['429']}", flush=True)
            except Exception as e:
                import traceback
                results[a] = {"task": task_id, "agent": a, "error": traceback.format_exc()[-500:]}
                print(f"  [{task_id}/{a}] ERROR {e}", flush=True)
        return go

    t0 = time.time()
    for i, a in enumerate(order):
        th = threading.Thread(target=launch(a, i * 20.0))
        th.start()
        threads.append(th)
    for th in threads:
        th.join()
    print(f"[round {task_id}] complete in {round(time.time()-t0,1)}s", flush=True)

    out = []
    for a in AGENTS:
        if a in results:
            out.append(results[a])
    (RUNS / task_id / "round_summary.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        print("usage: harness.py run <task-id>...")
        sys.exit(1)
    # kill every stale proxy from previous runs — they squat agent ports
    subprocess.run(["pkill", "-9", "-f", "bench_proxy.py"], capture_output=True)
    time.sleep(1)
    for tid in sys.argv[2:]:
        run_round(tid)


if __name__ == "__main__":
    main()
