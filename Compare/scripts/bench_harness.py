#!/usr/bin/env python3
"""
Controlled CLI benchmark harness: SHS Code vs OpenCode vs OpenHands vs Hermes
on NVIDIA NIM (same endpoint, same key, same model ids per category).

Policies:
- Same prompt for every CLI on a given task
- Fresh workspace per run (copy of git-baselined template)
- Objective filesystem verification only
- Full stdout/stderr captured to per-run trace log
- Anything a CLI does not expose (tokens/steps/tool calls) is recorded as
  "NOT EXPOSED BY CLI" - never fabricated
"""
import os, sys, json, time, shutil, subprocess, datetime, re

BENCH = "/home/z/my-project/bench"
TPL = f"{BENCH}/template-ws"
SHS = "/home/z/my-project/shs-code-live/.venv/bin/SHSCode"
OH = "/home/z/my-project/openhands-live/.venv/bin/openhands"
HER = "/home/z/my-project/hermes-live/.venv/bin/hermes"
COMPARE = "/home/z/my-project/Compare"
TRACES = f"{COMPARE}/traces"
NIM = "https://integrate.api.nvidia.com/v1"

for d in (COMPARE, TRACES):
    os.makedirs(d, exist_ok=True)

def api_key():
    for line in open("/home/z/my-project/.secrets/nim.env"):
        line = line.strip()
        if line.startswith("export NVIDIA_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("no key")

KEY = api_key()

MODELS = {
    "fast": {"label": "openai/gpt-oss-20b", "timeout": 600, "gap": 10},
    "agentic": {"label": "minimaxai/minimax-m3", "timeout": 900, "gap": 45},
}

# per-CLI wall clock cap (seconds); agentic runs get x1.5
# openhands: 320 so the agentic cap (480s) fits the 10-min tool window
CLI_TIMEOUT = {"shs-code": 300, "opencode": 420, "openhands": 320, "hermes": 420}

TASKS = {
    "T1": {
        "title": "create-and-run",
        "prompt": "Create file greet.py that prints exactly BENCH-T1-OK, then run it with python3 and confirm the output.",
        "verify": None,  # filled below
    },
    "T2": {
        "title": "bugfix-tests",
        "prompt": "src/calc.py has a bug: add() returns the wrong result. Fix add() so tests/test_calc.py passes. Do NOT modify anything under tests/. Run: python3 -m pytest tests/test_calc.py -q",
        "verify": None,
    },
    "T3": {
        "title": "multi-file-package",
        "prompt": "Create a package pkgmath/ (with __init__.py) exposing multiply(a,b) and power(a,b). Create tests/test_pkgmath.py with at least 3 test functions covering both. Run: python3 -m pytest tests/test_pkgmath.py -q",
        "verify": None,
    },
    "T4": {
        "title": "refactor-tests-pass",
        "prompt": "Refactor slugify in src/string_utils.py so ALL tests in tests/test_strings.py pass (hint: trim whitespace and collapse multiple spaces). Do NOT modify anything under tests/. Run: python3 -m pytest tests/test_strings.py -q",
        "verify": None,
    },
    "T5": {
        "title": "data-output",
        "prompt": "Write a script analyze.py that reads data/sales.csv and writes output.txt containing exactly two lines: TOTAL=<sum of amount> and TOP=<region name with the highest total amount>. Run it and confirm output.txt.",
        "verify": None,
    },
}

def sh(cmd, cwd, timeout=60):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)

def run_py(code, cwd, timeout=60):
    r = subprocess.run([sys.executable, "-c", code], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r

def v_T1(ws):
    checks = []
    ok = os.path.isfile(f"{ws}/greet.py")
    checks.append(("greet.py exists", True, ok))
    if ok:
        r = run_py("print(open('greet.py').read())", ws)  # noop warm
        p = subprocess.run([sys.executable, "greet.py"], cwd=ws, capture_output=True, text=True, timeout=60)
        good = p.stdout.strip() == "BENCH-T1-OK"
        checks.append(("python3 greet.py stdout == BENCH-T1-OK", "BENCH-T1-OK", p.stdout.strip()))
        ok = ok and good
    return ok, checks

def v_T2(ws):
    checks = []
    r = sh("python3 -m pytest tests/test_calc.py -q --tb=no", ws, timeout=120)
    ok = r.returncode == 0
    checks.append(("pytest test_calc exit==0", 0, r.returncode))
    t = sh("git status --porcelain tests/", ws).stdout.strip()
    checks.append(("tests/ unmodified", "", t))
    ok = ok and not t
    return ok, checks

def v_T3(ws):
    checks = []
    has_pkg = os.path.isfile(f"{ws}/pkgmath/__init__.py")
    checks.append(("pkgmath/__init__.py exists", True, has_pkg))
    r = run_py("from pkgmath import multiply, power\nassert multiply(3,4)==12, 'multiply'\nassert power(2,5)==32, 'power'\nprint('impl-ok')", ws, timeout=60)
    impl_ok = "impl-ok" in r.stdout
    checks.append(("multiply/power behave", True, impl_ok))
    r2 = sh("python3 -m pytest tests/test_pkgmath.py -q --tb=no", ws, timeout=120)
    tests_ok = r2.returncode == 0
    m = re.search(r"(\d+) passed", r2.stdout)
    n = int(m.group(1)) if m else 0
    checks.append(("pytest pkgmath exit==0 (>=3 cases)", ">=3 passed", f"{n} passed" if m else r2.stdout[-120:]))
    ok = has_pkg and impl_ok and tests_ok and n >= 3
    return ok, checks

def v_T4(ws):
    checks = []
    r = sh("python3 -m pytest tests/test_strings.py -q --tb=no", ws, timeout=120)
    ok = r.returncode == 0
    checks.append(("pytest test_strings exit==0", 0, r.returncode))
    t = sh("git status --porcelain tests/", ws).stdout.strip()
    checks.append(("tests/ unmodified", "", t))
    ok = ok and not t
    return ok, checks

def v_T5(ws):
    checks = []
    ok_file = os.path.isfile(f"{ws}/output.txt")
    checks.append(("output.txt exists", True, ok_file))
    good = False
    if ok_file:
        txt = open(f"{ws}/output.txt").read()
        lines = [l.strip() for l in txt.strip().splitlines() if l.strip()]
        total = sum([120,340,80,510,60,90,230,150,190,40])
        want = [f"TOTAL={total}", "TOP=sylhet"]
        good = lines == want
        checks.append(("output.txt lines", want, lines))
    return ok_file and good, checks

TASKS["T1"]["verify"] = v_T1
TASKS["T2"]["verify"] = v_T2
TASKS["T3"]["verify"] = v_T3
TASKS["T4"]["verify"] = v_T4
TASKS["T5"]["verify"] = v_T5

CLIS = {
    "shs-code": {"version": "2.2.0"},
    "opencode": {"version": "1.18.27"},
    "openhands": {"version": "1.16.0"},
    "hermes": {"version": "0.21.0"},
}

def build_cmd(cli, prompt, cat, run_ws):
    if cli == "shs-code":
        extra = ["--model", MODELS[cat]["label"]] if cat == "agentic" else []
        return [SHS, "--no-color"] + extra + [prompt]
    if cli == "opencode":
        return ["opencode", "run", "-m", "nim/" + MODELS[cat]["label"], prompt]
    if cli == "openhands":
        return [OH, "--headless", "--exit-without-confirmation", "--override-with-envs", "-t", prompt]
    if cli == "hermes":
        return [HER, "-z", prompt, "--yolo", "-m", MODELS[cat]["label"], "--in", run_ws]
    raise SystemExit(cli)

def build_env(cli, cat, ws=None):
    e = dict(os.environ)
    # CRITICAL: some CLIs resolve their workspace from $PWD (not cwd), which
    # would leak the harness shell's last cd into the run. Force PWD to the
    # run workspace for every CLI.
    if ws:
        e["PWD"] = ws
        e.pop("OLDPWD", None)
    e["NVIDIA_API_KEY"] = KEY
    if cli == "openhands":
        e["LLM_API_KEY"] = KEY
        e["LLM_BASE_URL"] = NIM
        # fast: double-prefix trick (litellm strips first "openai/");
        # agentic: custom_openai/ avoids litellm injecting prompt_cache_key,
        # which NIM rejects for minimax-m3 (400 Unsupported parameter).
        e["LLM_MODEL"] = ("openai/openai/gpt-oss-20b" if cat == "fast"
                          else "custom_openai/minimaxai/minimax-m3")
    if cli == "hermes":
        e["HERMES_CUSTOM_API_KEY"] = KEY
        e["CUSTOM_API_KEY"] = KEY
    return e

IGNORE_PREFIX = (".memory/", ".sessions/", ".task_queue/", ".git/")

def files_changed(ws):
    r = sh("git status --porcelain", ws)
    out = []
    for line in r.stdout.splitlines():
        p = line[3:].strip().strip('"')
        p = p.replace("-> ", "").split(" ")[0] if "-> " in p else p
        if not any(p.startswith(x) for x in IGNORE_PREFIX) and p:
            out.append(line[:2] + " " + p)
    return out

def fresh_ws(cli, task_id, cat):
    # Workspaces live under /tmp: opencode v1.18.27 hangs scanning when the
    # run dir sits under /home/z/my-project (a huge tree with its own .git at
    # the top). /tmp keeps every CLI's project root tiny. Same template,
    # same verifier - only the path differs.
    root = "/tmp/bench-ws"
    os.makedirs(root, exist_ok=True)
    name = f"{cli}-{task_id}-{cat}"
    ws = f"{root}/run-{name}"
    if os.path.exists(ws):
        shutil.rmtree(ws)
    shutil.copytree(TPL, ws)
    return ws, name

def set_hermes_cwd(ws):
    """Hermes integration: route via the local pacing proxy. The proxy (1)
    injects the API key (hermes strips auth for loopback base URLs) and (2)
    enforces >=11s spacing between chat POSTs — the same client-side pacing
    SHS Code applies via its rate_limit config — so hermes sees the same NIM
    token-bucket conditions as the other CLIs."""
    cfg = f'''provider: "custom"
base_url: "http://127.0.0.1:8899/v1"
model:
  default: "openai/gpt-oss-20b"
  streaming: false
rate_limit_delay: 12
terminal:
  cwd: "{ws}"
'''
    open("/home/z/.hermes/config.yaml", "w").write(cfg)
    os.chmod("/home/z/.hermes/config.yaml", 0o600)

def set_shs_rpm(cat):
    rpm = "5" if cat == "agentic" else "40"
    cfg = f"""llm:
  provider: universal
  base_url: "{NIM}"
  model: "openai/gpt-oss-20b"
  max_tokens: 4096
  temperature: 0.0
  max_retries: 2
  rate_limit:
    enabled: true
    rpm: {rpm}
conversation:
  max_iterations: 15
  confirmation_mode: "confirm_risky"
workspace_dir: "workspace"
"""
    open("/home/z/.shscode/config.yaml", "w").write(cfg)
    os.chmod("/home/z/.shscode/config.yaml", 0o600)

def already_done(run_id):
    try:
        with open(f"{COMPARE}/results.jsonl") as f:
            return any(json.loads(l).get("run_id") == run_id for l in f if l.strip())
    except FileNotFoundError:
        return False

def run_one(cli, task_id, cat):
    task = TASKS[task_id]
    if already_done(f"{cli}-{task_id}-{cat}"):
        print(f"[{cli}-{task_id}-{cat}] already recorded, skip", flush=True)
        return None
    note = ""
    for attempt in (1, 2):  # 1 retry allowed on total stall (no artifacts, verify fail)
        ws, name = fresh_ws(cli, task_id, cat)
        if cli == "hermes":
            set_hermes_cwd(ws)
        prompt = task["prompt"]
        cmd = build_cmd(cli, prompt, cat, ws)
        env = build_env(cli, cat, ws)
        trace = f"{TRACES}/{name}.log"
        t0 = time.time()
        timed_out = False
        cap = int(CLI_TIMEOUT[cli] * (1.5 if cat == "agentic" else 1.0))
        # IMPORTANT: redirect stdout/stderr to a FILE, never pipes.
        # opencode (v1.18.27) deadlocks when stdout is a pipe in non-interactive
        # `run` mode; file redirection works for every CLI.
        tf = open(trace, "w")
        tf.write(f"# cmd: {' '.join(cmd)}\n# cwd: {ws}\n# cap: {cap}s attempt: {attempt}\n\n=== OUTPUT ===\n")
        tf.flush()
        with open(trace, "a") as tf2:
            try:
                p = subprocess.run(cmd, cwd=ws, env=env, stdout=tf2, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, timeout=cap)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                rc = None
        tf.close()
        dur = round(time.time() - t0, 1)
        out, err = "", ""  # full output lives in the trace file
        try:
            ok, checks = task["verify"](ws)
        except Exception as ex:
            ok, checks = False, [("verifier crashed", "no-crash", str(ex)[:120])]
        # One retry allowed when attempt 1 failed FAST with zero task artifacts
        # (transient endpoint/model quirks, e.g. gpt-oss harmony leak 400s).
        stalled = (timed_out and not ok and not files_changed(ws)) or \
                  (dur < 90 and not ok and not files_changed(ws) and attempt == 1)
        if attempt == 1 and stalled:
            note = "attempt 1 hit wall-clock cap with zero task artifacts (stall); one retry allowed"
            print(f"[{name}] stall on attempt 1, retrying", flush=True)
            continue
        break
    rec = {
        "run_id": name,
        "task_id": task_id,
        "task_title": task["title"],
        "cli": cli,
        "cli_version": CLIS[cli]["version"],
        "category": cat,
        "model": MODELS[cat]["label"],
        "prompt": prompt,
        "cmd": " ".join(c for c in cmd if c),
        "exit_code": rc,
        "timed_out": timed_out,
        "duration_sec": dur,
        "verified_ok": ok,
        "verification": [{"check": c[0], "expected": str(c[1]), "actual": str(c[2])} for c in checks],
        "files_changed": files_changed(ws),
        "attempts": attempt,
        "notes": note,
        "tokens": "NOT EXPOSED BY CLI",
        "steps_iterations": "NOT EXPOSED BY CLI",
        "tool_calls": "NOT EXPOSED BY CLI",
        "trace_log": trace,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(f"{COMPARE}/results.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"[{name}] ok={ok} dur={dur}s rc={rc} timeout={timed_out}", flush=True)
    return ok

def main():
    cats = sys.argv[1].split(",") if len(sys.argv) > 1 else ["fast"]
    clis = sys.argv[2].split(",") if len(sys.argv) > 2 else list(CLIS.keys())
    tasks = sys.argv[3].split(",") if len(sys.argv) > 3 else list(TASKS.keys())
    if "hermes" in clis:
        sys.path.insert(0, "/home/z/my-project/scripts")
        from nim_pacing_proxy import start_proxy
        start_proxy()
        print("[harness] pacing proxy up on 127.0.0.1:8899", flush=True)
    for cat in cats:
        set_shs_rpm(cat)
        for task_id in tasks:
            for cli in clis:
                if cat == "agentic":
                    # NIM m3 token bucket (~5-6 RPM) refills slowly; settle
                    # before every agentic run so each CLI starts from a
                    # comparable bucket state (environment normalization).
                    time.sleep(60)
                run_one(cli, task_id, cat)
                time.sleep(MODELS[cat]["gap"])

if __name__ == "__main__":
    main()
