"""Canonical benchmark task definitions — identical prompts for every agent.

Each task: id, category, turns (list of prompts), timeout, verify(workdir)->dict,
optional env/flags. Turn 2 runs only for two-turn tasks (resume/continue).
"""

import re
import subprocess
from pathlib import Path

QA = "What is 2+2? Reply with just the number."


def _read(workdir: str, name: str) -> str:
    p = Path(workdir) / name
    return p.read_text(errors="replace") if p.exists() else ""


def _run_pytest(workdir: str, extra_args=()):
    try:
        r = subprocess.run(
            ["/home/z/.venv/bin/python3", "-m", "pytest", "-q", "--tb=no", *extra_args],
            cwd=workdir, capture_output=True, text=True, timeout=120)
        out = r.stdout + r.stderr
        m = re.search(r"(\d+) passed", out)
        f = re.search(r"(\d+) failed", out)
        return {"passed": int(m.group(1)) if m else 0,
                "failed": int(f.group(1)) if f else 0,
                "ok": r.returncode == 0}
    except Exception as e:
        return {"passed": 0, "failed": 0, "ok": False, "error": str(e)[:200]}


def _import_fn(workdir: str, module: str, fn: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(module, str(Path(workdir) / f"{module}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, fn)


TASKS = []


def task(tid, cat, title, turns, timeout, verify, extra_env=None, kind="single"):
    TASKS.append({"id": tid, "category": cat, "title": title, "turns": turns,
                  "timeout": timeout, "verify": verify, "extra_env": extra_env or {},
                  "kind": kind})


# ═══════════════ CATEGORY 1: MEMORY & PERSISTENT WORK STATE ═══════════════

def v01(w):
    a = _read(w, "ANSWER.txt").strip()
    return {"answer": a, "correct": a == "7",
            "note": "7 defs = 4 calc + 3 textproc; must be recalled without re-reading"}

task("task-01", "memory", "M1 short-term context retention (2 turns, same session)",
     ["Read the files calc.py and textproc.py. Count the TOTAL number of function "
      "definitions (lines starting with 'def') across both files combined. Remember "
      "this number. Do not write it down anywhere yet. Reply with just the number.",
      "Without re-reading the files, write the total number of function definitions "
      "you counted in the previous step to a file named ANSWER.txt as plain digits "
      "only. Then reply with the number."],
     300, v01, kind="two-turn")

def v02(w):
    a = _read(w, "PORT.txt").strip()
    return {"answer": a, "correct": a == "7331"}

task("task-02", "memory", "M2 long-term memory across sessions (2 new sessions)",
     ["Important project fact to remember for future sessions: this project's "
      "deployment port is 7331 and the preferred test runner is pytest. Store this "
      "in your persistent long-term memory. Reply DONE when stored.",
      "Without asking me any question: what is this project's deployment port? If "
      "you know it or can find it from what you previously stored, write ONLY the "
      "port number to a file named PORT.txt. If you truly cannot determine it, "
      "write UNKNOWN."],
     240, v02, kind="two-turn-newsession")

def v03(w):
    content = _read(w, "AGENTS.md")
    if not content:
        content = _read(w, "CLAUDE.md")
    checks = {
        "file_exists": len(content) > 0,
        "mentions_calc": "calc" in content.lower(),
        "mentions_textproc": "textproc" in content.lower(),
        "mentions_pytest": "pytest" in content.lower() or "test" in content.lower(),
        "mentions_failing": "fail" in content.lower() or "bug" in content.lower(),
        "substantial": len(content) > 400,
    }
    return checks

task("task-03", "memory", "M3 project Markdown memory file",
     ["Create a project memory file named AGENTS.md (or CLAUDE.md if that is your "
      "convention) in the repository root, documenting for future agents: the "
      "repository architecture, what each module does, how to run the tests, and "
      "the known failing tests. Keep it under 60 lines."],
     300, v03)

def v04(w):
    log = _read(w, "WORKLOG.md")
    stages = len(re.findall(r"[Ss]tage\s*[123]|^##?\s*[123]\b|\b[123]\)\s", log, re.M))
    t = _run_pytest(w)
    has_fn = "is_palindrome" in _read(w, "textproc.py")
    return {"worklog_exists": len(log) > 50, "stages_marked": min(stages, 3),
            "function_implemented": has_fn, "tests_pass": t["ok"] and t["failed"] == 0}

task("task-04", "memory", "M4 work notebook progress journal",
     ["Add a function is_palindrome(s) to textproc.py that returns True when s reads "
      "the same forwards and backwards, ignoring case and non-alphanumeric characters. "
      "Work in exactly 3 stages: (1) implement the function, (2) add tests for it in "
      "test_textproc.py, (3) run the full test suite and fix the pre-existing word_count "
      "bug so everything passes. After EACH stage, append a progress note to WORKLOG.md "
      "stating the stage number, what was just done, and what remains."],
     330, v04)

def v05(w):
    ch = _read(w, "CH.md")
    items = re.findall(r"^[-*]\s*\[( |x|X)\]", ch, re.M)
    done = sum(1 for i in items if i.strip().lower() == "x")
    return {"ch_exists": len(ch) > 0, "items_total": len(items), "items_checked": done,
            "done_marker": _read(w, "DONE.txt").strip().upper() == "DONE",
            "all_done": len(items) == 5 and done == 5 and _read(w, "DONE.txt").strip().upper() == "DONE"}

task("task-05", "memory", "M5 interruption + resume (kill at 70s, then continue)",
     ["Create CH.md containing exactly these 5 checklist items, all unchecked:\n"
      "1. add strip_punct(s) to textproc.py (strips non-alphanumeric characters)\n"
      "2. add test_strip_punct to test_textproc.py\n"
      "3. create utils/dates.py with today_iso() returning today as YYYY-MM-DD\n"
      "4. update README.md with a module list\n"
      "5. run the full test suite\n"
      "Then execute the items in order, marking each with [x] in CH.md as you "
      "complete it. When all 5 are done and checked, write DONE.txt containing DONE.",
      "Continue your interrupted checklist task from where you left off. Complete "
      "every remaining item, checking each off in CH.md, and write DONE.txt "
      "containing DONE when finished."],
     330, v05, kind="two-turn-kill")

# ═══════════════ CATEGORY 2: PLANNING & AUTONOMOUS EXECUTION ═══════════════

def v06(w):
    return {"note": "scored from trace: correctness(4), speed, tool-spam, planning overhead"}

task("task-06", "planning", "P1 trivial Q&A sanity (no unnecessary planning)",
     [QA], 240, v06)

def v07(w):
    try:
        fn = _import_fn(w, "textproc", "slugify")
        cases = [("Hello World", "hello-world"), ("A B", "a-b"), ("", ""),
                 ("   ", ""), ("Hello,  World!!", "hello-world"),
                 ("café uno", "caf-uno") if False else ("abc  def", "abc-def")]
        results = {}
        for inp, exp in cases:
            try:
                results[repr(inp)] = (fn(inp) == exp)
            except Exception as e:
                results[repr(inp)] = f"err:{e}"
        return {"cases": results, "all_pass": all(v is True for v in results.values())}
    except Exception as e:
        return {"error": str(e)[:200], "all_pass": False}

task("task-07", "planning", "P2 simple coding task (slugify)",
     ["Add a function slugify(text) to textproc.py: convert to lowercase, replace "
      "any run of non-alphanumeric characters with a single hyphen, collapse "
      "multiple hyphens, strip leading/trailing hyphens. slugify('') and "
      "slugify('   ') must return empty strings. Do not change other functions."],
     300, v07)

def v08(w):
    ok_stats = True
    checks = {}
    p = Path(w) / "stats.py"
    checks["stats_exists"] = p.exists()
    if p.exists():
        try:
            mean = _import_fn(w, "stats", "mean")
            median = _import_fn(w, "stats", "median")
            checks["mean_ok"] = mean([1, 2, 3]) == 2
            checks["median_odd"] = median([3, 1, 2]) == 2
            checks["median_even"] = median([4, 1, 3, 2]) == 2.5
            try:
                mean([]); checks["mean_empty_raises"] = False
            except Exception:
                checks["mean_empty_raises"] = True
        except Exception as e:
            checks["import_error"] = str(e)[:150]
    checks["test_stats_exists"] = (Path(w) / "test_stats.py").exists()
    t = _run_pytest(w)
    checks["suite"] = f"{t['passed']}p/{t['failed']}f"
    checks["all_pass"] = t["ok"] and t["failed"] == 0
    return checks

task("task-08", "planning", "P3 multi-file implementation (stats module + tests)",
     ["Create a new module stats.py with mean(nums) and median(nums) functions "
      "(median must handle both odd and even length lists; raise ValueError on "
      "empty input). Add test_stats.py with tests covering normal cases, even/odd "
      "medians, and empty-input errors. Then run the FULL test suite and make "
      "everything pass, including fixing the pre-existing word_count bug."],
     330, v08)

def v09(w):
    t = _run_pytest(w)
    src = _read(w, "textproc.py")
    fixed = "def word_count" in src and ("re.split" in src or "re.findall" in src
              or "import string" in src or "split()" in src) and 'split(" ")' not in src
    test_unchanged = "Hello,  world!!" in _read(w, "test_textproc.py")
    return {"suite": f"{t['passed']}p/{t['failed']}f", "all_pass": t["ok"],
            "implementation_fixed": fixed, "tests_untouched": test_unchanged}

task("task-09", "planning", "P4 debugging task (root cause of failing tests)",
     ["Two tests in test_textproc.py are failing. Diagnose the root cause and fix "
      "the IMPLEMENTATION in textproc.py so both failing tests pass. Do NOT modify "
      "the test file. In your final reply, state the root cause in one sentence."],
     300, v09)

def v10(w):
    checks = {}
    p = Path(w) / "fizzbuzz.py"
    checks["fizzbuzz_exists"] = p.exists()
    if p.exists():
        try:
            fb = _import_fn(w, "fizzbuzz", "fizzbuzz")
            exp = {15: "fizzbuzz", 9: "fizz", 10: "buzz", 7: "7", 30: "fizzbuzz"}
            checks["cases"] = {n: fb(n) == e for n, e in exp.items()}
            try:
                fb(0); checks["zero_handled"] = True
            except Exception:
                checks["zero_handled"] = False
        except Exception as e:
            checks["error"] = str(e)[:150]
    checks["test_exists"] = (Path(w) / "test_fizzbuzz.py").exists()
    t = _run_pytest(w)
    checks["suite"] = f"{t['passed']}p/{t['failed']}f"
    return checks

task("task-10", "planning", "P5 implement + self-verify until green",
     ["Implement fizzbuzz(n) in a new file fizzbuzz.py: return 'fizzbuzz' if n is "
      "divisible by 15, 'fizz' if by 3, 'buzz' if by 5, otherwise str(n). Add "
      "test_fizzbuzz.py covering n=15, 9, 10, 7 and the edge case n=0. Run the "
      "tests and iterate until your new tests pass, then include the final pytest "
      "summary line in your reply."],
     330, v10)

# ═══════════ CATEGORY 3: OUTPUT / CODE QUALITY / VERIFICATION ═══════════

HIDDEN_EMAIL_TESTS = [
    ("user@example.com", "user@example.com", True),
    ("user.name+tag@domain.co", "user.name+tag@domain.co", True),
    ("a@b.io", "a@b.io", True),
    ("USER@EXAMPLE.COM", "user@example.com", True),
    ("user@example.c", None, False),           # TLD too short
    ("user@@example.com", None, False),
    ("@example.com", None, False),
    ("user@", None, False),
    ("user@exa mple.com", None, False),
    ("user@..com", None, False),
    (".user@example.com", None, False),        # leading dot local? allowed per spec? we say invalid start
    ("user.@example.com", None, False),
    ("user@-example.com", None, False),
    ("us er@example.com", None, False),
    ("us@er@example.com", None, False),
    ("user@example..com", None, False),
    ("user@EXAMPLE.com", "user@example.com", True),
]

def v11(w):
    try:
        fn = _import_fn(w, "validators", "validate_email")
        results = {}
        for inp, exp, ok in HIDDEN_EMAIL_TESTS:
            try:
                got = fn(inp)
                results[repr(inp)[:28]] = (got == exp) if ok else False
            except Exception:
                results[repr(inp)[:28]] = True if not ok else False
        return {"hidden_cases": results,
                "all_pass": all(results.values()),
                "pass_count": f"{sum(1 for v in results.values() if v)}/{len(results)}"}
    except Exception as e:
        return {"error": str(e)[:200], "all_pass": False}

task("task-11", "output", "O1 feature implementation (hidden-test email validator)",
     ["Create validators.py with a function validate_email(s) implementing this "
      "spec exactly: valid if it matches local@domain where local is 1-64 chars "
      "from [A-Za-z0-9._%+-] but must not start or end with a dot; domain is 1-255 "
      "chars from [A-Za-z0-9.-], must not start or end with '-' or '.', must "
      "contain no consecutive dots, must contain at least one dot, and the final "
      "label (TLD) must be 2+ letters. If valid, return the lowercased email; "
      "otherwise raise ValueError. Add your own tests in test_validators.py."],
     330, v11)

HIDDEN_WC_TESTS = [
    ("Hello,  world!!", 2), ("a...b", 2), ("", 0), ("   ", 0),
    ("one two three", 3), ("word.", 1), ("  leading", 1), ("trailing  ", 1),
    ("multiple   spaces here", 3), ("!@#$%", 0), ("don't stop", 2),
]

def v12(w):
    try:
        fn = _import_fn(w, "textproc", "word_count")
        results = {repr(t)[:24]: fn(t) == e for t, e in HIDDEN_WC_TESTS}
        has_tests = "word_count" in _read(w, "test_textproc.py") and len(
            re.findall(r"def test_.*word", _read(w, "test_textproc.py"))) >= 2
        return {"hidden_cases": results, "all_pass": all(results.values()),
                "regression_tests_added": has_tests}
    except Exception as e:
        return {"error": str(e)[:200], "all_pass": False}

task("task-12", "output", "O2 bug fix quality (word_count hidden tests)",
     ["The word_count function in textproc.py is broken: it splits on single "
      "spaces so punctuation attached to words and consecutive spaces miscount "
      "it. Fix it so words are sequences of non-whitespace characters with "
      "surrounding punctuation stripped (e.g. 'Hello,  world!!' -> 2, 'a...b' -> 2, "
      "'' -> 0, '!@#$%' -> 0). Add regression tests to test_textproc.py."],
     300, v12)

def v13(w):
    src = _read(w, "calc.py")
    checks = {
        "has_class": "class Calculator" in src,
        "has_methods": all(f"def {m}" in src for m in ("add", "sub", "mul", "div")),
        "module_fns_wrapped": all(
            re.search(rf"def {m}\(.*\).*:\s*\n\s*(?:return\s+)?Calculator\(\)\.{m}", src)
            for m in ("add", "sub", "mul", "div")) or
            all(f"def {m}" in src for m in ("add", "sub", "mul", "div")),
    }
    t = _run_pytest(w)
    checks["suite"] = f"{t['passed']}p/{t['failed']}f"
    checks["tests_unchanged_pass"] = t["ok"] and t["failed"] == 0
    return checks

task("task-13", "output", "O3 refactor (class-based Calculator, API compat)",
     ["Refactor calc.py so the arithmetic lives in a Calculator class with add, "
      "sub, mul, div methods, while KEEPING the existing module-level functions "
      "add/sub/mul/div as thin wrappers so the existing tests pass unchanged. "
      "Run the test suite to confirm."],
     300, v13)

def v14(w):
    tests = _read(w, "test_textproc.py")
    impl = _read(w, "textproc.py")
    cases = {
        "tests_for_reverse": "reverse_words" in tests,
        "tests_for_capitalize": "capitalize_words" in tests,
        "edge_empty": '""' in tests or "''" in tests,
        "edge_unicode": "caf" in tests.lower(),
        "edge_multi_space": "  " in tests or "spaces" in tests.lower(),
        "impl_untouched": 'split(" ")' in impl and "def word_count" in impl,
        "count_new_tests": len(re.findall(r"def test_", tests)),
    }
    t = _run_pytest(w)
    cases["suite"] = f"{t['passed']}p/{t['failed']}f"
    return cases

task("task-14", "output", "O4 test quality (thorough tests, no impl changes)",
     ["Write thorough pytest tests for reverse_words and capitalize_words in "
      "textproc.py, adding them to test_textproc.py. Cover edge cases: empty "
      "string, single word, multiple spaces, punctuation, and unicode like "
      "'café'. Do NOT change the implementation. Run the tests you added."],
     300, v14)

def v15(w):
    r = _read(w, "README.md")
    checks = {
        "no_todo": "TODO" not in r,
        "has_install": "install" in r.lower(),
        "has_usage": "usage" in r.lower() or "example" in r.lower(),
        "mentions_add": "add(" in r, "mentions_word_count": "word_count" in r,
        "has_test_instr": "pytest" in r.lower(),
        "mentions_stats_or_modules": "calc" in r.lower() and "textproc" in r.lower(),
        "substantial": len(r) > 500,
        "signatures_match": all(s in r for s in ("add(a", "word_count(text")),
    }
    return checks

task("task-15", "output", "O5 documentation (README rewrite)",
     ["Rewrite README.md as complete product documentation for this repository: "
      "overview, installation (pip install -e .), usage examples that match the "
      "actual function signatures, how to run the tests, and known issues (the "
      "failing tests). Remove the TODO line. Keep it under 80 lines."],
     330, v15)

# ══════════ CATEGORY 4: TOOLS / GITHUB / MCP / SKILLS / INTEGRATIONS ══════════

def v16(w):
    r = subprocess.run(["git", "branch", "--list", "feat/logger"], cwd=w,
                       capture_output=True, text=True)
    on_branch = "feat/logger" in r.stdout
    log = subprocess.run(["git", "log", "feat/logger", "--oneline", "-1"], cwd=w,
                         capture_output=True, text=True).stdout
    logger = _read(w, "logger.py")
    t = _run_pytest(w)
    main_log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=w,
                              capture_output=True, text=True).stdout
    return {"branch_created": on_branch,
            "commit_msg_conventional": "feat:" in log or "feat(" in log,
            "logger_implemented": "def log(" in logger and "app.log" in logger,
            "tests_still_pass": t["ok"],
            "main_unchanged": "docs: changelog entry" in main_log or "initial benchlib" in main_log}

task("task-16", "tools", "T1 git branch workflow",
     ["Create a git branch named feat/logger. On that branch, implement logger.py "
      "with a function log(level, message) that appends a line like "
      "'2026-01-01T00:00:00 [INFO] message' (ISO timestamp) to app.log. Commit only "
      "logger.py on the branch with the message 'feat: add structured logger'. "
      "Then switch back to main. Report the branch name and the commit hash."],
     330, v16)

def v17(w):
    # verified post-hoc via gh api by harness (repo creation)
    return {"note": "GitHub repo/issue verified via gh api post-hoc by harness"}

task("task-17", "tools", "T2 GitHub repo + issue creation",
     ["Using git and the GitHub CLI (gh, already installed and authenticated), "
      "create a NEW private GitHub repository named {REPO_NAME} under the "
      "authenticated account. Push all local branches to it. Then open an issue "
      "titled 'Benchmark audit' whose body lists every public function in calc.py "
      "with its one-line docstring. Report the repository URL and issue number."],
     390, v17, extra_env={"GIT_KIND": "github"})

def v18(w):
    t = _read(w, "TIME.txt").strip()
    ok = bool(re.match(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", t)) or bool(t)
    return {"time_file": t[:60], "nonempty": len(t) > 3, "plausible": ok}

task("task-18", "tools", "T3 MCP tool usage (get_time)",
     ["Use the MCP tool get_time provided by the configured MCP server 'bench' "
      "to obtain the current server time, and write exactly what the tool returns "
      "to a file named TIME.txt. If the MCP server is unavailable, write "
      "MCP-UNAVAILABLE instead."],
     330, v18, extra_env={"MCP_TASK": "1"})

def v19(w):
    todos = _read(w, "TODOS.txt")
    archive = Path(w) / "archive"
    md_files = sorted(p.name for p in archive.glob("*.md")) if archive.exists() else []
    envex = _read(w, ".env.example")
    return {"todos_has_readme_line": bool(re.search(r"README\.md:\d", todos)),
            "archive_created": archive.exists(),
            "md_copied": len(md_files), "md_list": md_files,
            "env_example": "FOO=bar" in envex}

task("task-19", "tools", "T4 terminal + filesystem operations",
     ["Do these steps in order: (1) find every TODO comment in the repository and "
      "write them to TODOS.txt as file:line entries. (2) create a directory named "
      "archive and copy every .md file from the repo root into it. (3) create a "
      "file .env.example containing exactly: FOO=bar. (4) show the final directory "
      "tree in your reply."],
     330, v19)

def v20(w):
    ver = ""
    try:
        ver = _import_fn(w, "pyproject", "__version__") if False else ""
        import tomllib
        with open(Path(w) / "pyproject.toml", "rb") as f:
            ver = tomllib.load(f)["project"]["version"]
    except Exception:
        pass
    ch = _read(w, "CHANGELOG.md")
    rel = _read(w, "RELEASE.md")
    r = subprocess.run(["git", "branch", "--list", "chore/release-0.2.0"], cwd=w,
                       capture_output=True, text=True)
    log = subprocess.run(["git", "log", "chore/release-0.2.0", "--oneline", "-3"], cwd=w,
                         capture_output=True, text=True).stdout if "chore/release" in r.stdout else ""
    return {"version_bumped": ver == "0.2.0", "changelog_updated": "0.2.0" in ch,
            "release_md": len(rel) > 100, "branch_created": "chore/release-0.2.0" in r.stdout,
            "committed": len(log) > 0}

task("task-20", "tools", "T5 combined release workflow",
     ["Release preparation: (1) bump the version to 0.2.0 in pyproject.toml. "
      "(2) append a section for 0.2.0 to CHANGELOG.md summarizing the repository "
      "state. (3) make the full test suite pass (fix the word_count bug). "
      "(4) create a branch named chore/release-0.2.0 and commit all changes "
      "there. (5) write RELEASE.md summarizing every step you performed."],
     390, v20)

# ═════════ CATEGORY 5: RELIABILITY / RATE LIMIT / RECOVERY ═════════

def v21(w):
    h = _read(w, "HEADLINE.txt").strip()
    return {"headline": h, "correct": h == "# benchlib — small utility library used for agent benchmarking" or "benchlib" in h}

task("task-21", "reliability", "R1 normal execution + timing",
     ["Read README.md and write its first heading (the line starting with #) to "
      "HEADLINE.txt exactly as it appears. Then reply with the heading."],
     300, v21)

def v22(w):
    b = _read(w, "BRANCH.txt").strip()
    return {"branch": b, "correct": b in ("main", "master")}

task("task-22", "reliability", "R2 provider fault resilience (2 injected 502s)",
     ["Write the name of the current git branch to BRANCH.txt, then reply with "
      "the branch name."],
     330, v22, extra_env={"PROXY_MODE": "fault502"})

def v23(w):
    m = _read(w, "MODULES.txt").strip()
    return {"modules": m, "correct": "calc" in m and "textproc" in m and "test" not in m.split()[0].lower()[:4]}

task("task-23", "reliability", "R3 rate-limit injection (429 + Retry-After)",
     ["Write the names of the Python modules (files, not tests) in this repository "
      "to MODULES.txt, one per line, then reply with them."],
     390, v23, extra_env={"PROXY_MODE": "rate429"})

def v24(w):
    checks = {}
    p = Path(w) / "cipher.py"
    checks["cipher_exists"] = p.exists()
    if p.exists():
        try:
            enc = _import_fn(w, "cipher", "encrypt")
            dec = _import_fn(w, "cipher", "decrypt")
            checks["roundtrip"] = dec(enc("attack at dawn", 3), 3) == "attack at dawn"
            checks["encrypt_shift"] = enc("abc", 3) == "def"
            checks["case_preserved"] = enc("AbC", 3) in ("DeF", "def")
        except Exception as e:
            checks["error"] = str(e)[:150]
    checks["tests_exist"] = (Path(w) / "test_cipher.py").exists()
    t = _run_pytest(w)
    checks["suite"] = f"{t['passed']}p/{t['failed']}f"
    dup = subprocess.run(["git", "log", "--oneline"], cwd=w, capture_output=True, text=True)
    checks["git_log_len"] = len(dup.stdout.strip().splitlines())
    return checks

task("task-24", "reliability", "R4 kill + resume reliability (kill at 75s)",
     ["Implement a Caesar cipher: create cipher.py with encrypt(text, shift) and "
      "decrypt(text, shift) that shift letters (a-z, A-Z) by the given amount, "
      "preserving case and leaving non-letters untouched. Create test_cipher.py "
      "with at least 4 tests including a round-trip test. Run the full suite and "
      "make it pass.",
      "Continue your interrupted cipher task from where you left off and finish "
      "it completely."],
     360, v24, kind="two-turn-kill")

def v25(w):
    s = _read(w, "SAFEFUNC.txt").strip()
    return {"answer": s, "correct": s == "div"}

task("task-25", "reliability", "R5 model switch mid-conversation (2 turns)",
     ["Read calc.py. Which function performs safe division (raising on zero "
      "divisor)? Remember its exact name. Reply with just the function name.",
      "Write the name of the function you identified in the previous turn to "
      "Write the name of the function you identified in the previous turn to a file named SAFEFUNC.txt (create it). Reply with the function name."],
     300, v25, kind="two-turn-newsession")

CATEGORIES = {
    "memory": "Category 1: Memory & Persistent Work State",
    "planning": "Category 2: Planning & Autonomous Execution",
    "output": "Category 3: Output / Code Quality / Verification",
    "tools": "Category 4: Tools / GitHub / MCP / Skills / Integrations",
    "reliability": "Category 5: Reliability / Rate Limit / Recovery",
}
