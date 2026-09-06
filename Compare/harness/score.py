#!/usr/bin/env python3
"""Score all benchmark runs: deterministic checks + trace evidence -> 1-10.

Outputs benchmark/scores.json + benchmark/scores_table.md
Scoring is evidence-based: each score derives from objective artifacts
(check results, files changed, tool calls, test outcomes, answer files).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/benchmark")
from tasks import TASKS, CATEGORIES  # noqa: E402

RUNS = Path("/home/z/my-project/benchmark/runs")
AGENTS = ["opencode", "openhands", "hermes", "shs-single", "shs-multi",
          "shs-offline-single", "shs-offline-multi"]
SHS_LIKE = ("shs-single", "shs-multi", "shs-offline-single", "shs-offline-multi")


def load(task_id, agent):
    d = RUNS / task_id / agent
    r = json.load(open(d / "result.json")) if (d / "result.json").exists() else None
    trace = []
    if (d / "trace.jsonl").exists():
        for l in open(d / "trace.jsonl"):
            try:
                trace.append(json.loads(l))
            except json.JSONDecodeError:
                pass
    return r, trace, d


def tool_calls(agent, trace):
    """Count visible tool calls from trace stream lines."""
    n = 0
    for e in trace:
        if e.get("event") != "stream":
            continue
        t = e.get("text", "")
        if agent == "opencode":
            if '"type":"tool_use"' in t or '"type": "tool_use"' in t:
                n += 1
        elif agent in SHS_LIKE:
            if "Tool call:" in t or "[TOOL]" in t or "execute(" in t:
                n += 1
        elif agent == "openhands":
            if re.search(r"(Running|Executed) (command|action|bash)", t, re.I) or '"action"' in t:
                n += 1
        elif agent == "hermes":
            if re.search(r"tool[_ ]call|Tool:|mcp_", t, re.I):
                n += 1
    return n


def final_answer(agent, trace):
    """Extract the last assistant-visible answer text."""
    texts = []
    for e in trace:
        if e.get("event") != "stream":
            continue
        t = e.get("text", "")
        if agent == "opencode":
            m = re.search(r'"type":"text","text":"([^"]{1,300})', t)
            if m:
                texts.append(m.group(1))
        elif agent in SHS_LIKE:
            # v3.0.1: the CLI now prints system notices AFTER the answer
            # ("⚙ SYSTEM: session: ...") — those are bookkeeping, never the
            # answer; the assistant answer is the short line right after
            # the 🤖 ASSISTANT header.
            if t.startswith("⚙") or t.startswith("Continuing session"):
                continue
            # v3.0.2: the multi runner prints "session: <id>" bare and the
            # answer inside the stage box "✓ Engineer [70.5s] — 4"
            if t.startswith("session:"):
                continue
            m = re.search(r"✓\s+\w+\s+\[[\d.]+s\]\s+—\s+(.*)", t)
            if m and m.group(1).strip():
                texts.append(m.group(1).strip())
                continue
            if t.startswith("🤖"):
                texts.append("")
                continue
            if texts and len(t.strip()) < 300 and "INFO" not in t and "DEBUG" not in t:
                # skip decorative borders / box-drawing-only lines
                stripped = t.strip()
                if stripped and all(ch in "═─│╒╕╘╛┌┐└┘+=-_*# " for ch in stripped):
                    continue
                if not t.startswith("  ["):
                    texts[-1] = (texts[-1] + "\n" + stripped).strip() if texts[-1] else stripped
        else:
            if len(t.strip()) > 0 and len(t.strip()) < 400 and "INFO" not in t and "DEBUG" not in t:
                texts.append(t)
    return texts[-1] if texts else ""


def frac(checks, keys):
    """Fraction of boolean checks that are True."""
    vals = [bool(checks.get(k)) for k in keys if k in checks]
    return (sum(vals), len(vals)) if vals else (0, 0)


def score_run(task, agent):
    r, trace, d = load(task["id"], agent)
    if r is None:
        return 1, "no result.json — run failed to record"
    c = r.get("checks", {})
    t1, t2 = r["turns"]["t1"], r["turns"]["t2"]
    p = r["proxy"]
    git = r.get("git", {})
    ev = []   # evidence lines
    tc = tool_calls(agent, trace)
    ans = final_answer(agent, trace)

    base = 1
    note = ""

    # ---- task-specific deterministic scoring ----
    tid = task["id"]
    if tid == "task-01":
        if c.get("correct"):
            base = 9 if t1["wall_s"] < 120 else 8
            if t2["wall_s"] and t2["wall_s"] < 100:
                base = 10
            note = f"recalled {c.get('answer')} without re-reading"
        else:
            base = 4 if c.get("answer") else 2
            note = f"answer file: {c.get('answer')!r}"
    elif tid == "task-02":
        if c.get("correct"):
            base = 10 if t1["wall_s"] + t2["wall_s"] < 300 else 9
            note = "port recalled in a NEW session (persistent long-term memory)"
        else:
            base = 2 if not c.get("answer") else 3
            note = f"PORT.txt={c.get('answer')!r}"
    elif tid == "task-03":
        ok, tot = frac(c, ["file_exists", "mentions_calc", "mentions_textproc",
                           "mentions_pytest", "mentions_failing", "substantial"])
        base = 1 + round(ok / max(tot, 1) * 9) if tot else 1
        note = f"memory-file checks {ok}/{tot}"
    elif tid == "task-04":
        ok, tot = frac(c, ["worklog_exists", "function_implemented", "tests_pass"])
        stages = c.get("stages_marked", 0)
        base = 1 + round((ok / 3) * 6) + min(stages, 3)
        if base > 10:
            base = 10
        note = f"worklog={c.get('worklog_exists')} fn={c.get('function_implemented')} tests={c.get('tests_pass')} stages={stages}"
    elif tid == "task-05":
        items = c.get("items_total", 0)
        checked = c.get("items_checked", 0)
        if c.get("all_done"):
            base, note = 10, "all 5 items completed, checked, DONE.txt written"
        else:
            base = 1 + (2 if c.get("ch_exists") else 0) + min(checked, 5)
            note = f"CH.md items={items} checked={checked} done_marker={c.get('done_marker')}"
    elif tid == "task-06":
        correct = ans.strip() == "4" or "4" in ans.strip()[-5:]
        if correct:
            base = 10 if t1["wall_s"] < 30 else (9 if t1["wall_s"] < 60 else 8)
            if p["requests"] > 6:
                base = max(base - 1, 6)
            note = f"answered '{ans.strip()[:20]}' in {t1['wall_s']}s, {p['requests']} reqs, {tc} tool calls"
        else:
            base = 2
            note = f"no/wrong answer: {ans.strip()[:40]!r}"
    elif tid == "task-07":
        cases = c.get("cases", {})
        if c.get("all_pass"):
            base = 10
            note = "all slugify hidden cases pass"
        elif cases:
            ok = sum(1 for v in cases.values() if v is True)
            base = 1 + round(ok / len(cases) * 9)
            note = f"slugify {ok}/{len(cases)} cases"
        else:
            base = 2 if c.get("error") else 1
            note = f"no slugify: {str(c.get('error',''))[:60]}"
    elif tid == "task-08":
        ok, tot = frac(c, ["stats_exists", "mean_ok", "median_odd", "median_even",
                           "mean_empty_raises", "test_stats_exists", "all_pass"])
        base = 1 + round(ok / max(tot, 1) * 9)
        note = f"stats module checks {ok}/{tot} suite={c.get('suite')}"
    elif tid == "task-09":
        ok, tot = frac(c, ["all_pass", "implementation_fixed", "tests_untouched"])
        base = 1 + round(ok / 3 * 9)
        if ok == 3 and "root cause" in ans.lower():
            base = 10
        note = f"suite={c.get('suite')} fixed={c.get('implementation_fixed')} tests_untouched={c.get('tests_untouched')}"
    elif tid == "task-10":
        cases = c.get("cases", {})
        ok = sum(1 for v in (cases or {}).values() if v is True)
        has = 1 if c.get("fizzbuzz_exists") else 0
        tst = 1 if c.get("test_exists") else 0
        suite = c.get("suite", "")
        passed = "p" in suite and "0f" in suite.replace(" ", "")
        if ok >= 4 and passed:
            base = 10
        elif ok >= 3:
            base = 7 + tst
        else:
            base = 1 + has + tst + (1 if ok else 0)
        note = f"fizzbuzz cases {ok}/5 tests={c.get('test_exists')} suite={suite}"
    elif tid == "task-11":
        if c.get("all_pass"):
            base = 10
            note = f"all hidden email tests pass ({c.get('pass_count')})"
        else:
            hc = c.get("hidden_cases", {})
            ok = sum(1 for v in (hc or {}).values() if v is True)
            tot = len(hc) if hc else 1
            base = 1 + round(ok / tot * 9)
            note = f"hidden email tests {ok}/{tot}"
    elif tid == "task-12":
        if c.get("all_pass"):
            base = 10 if c.get("regression_tests_added") else 9
            note = "all hidden word_count tests pass"
        else:
            hc = c.get("hidden_cases", {})
            ok = sum(1 for v in (hc or {}).values() if v is True)
            tot = len(hc) if hc else 1
            base = 1 + round(ok / tot * 9)
            note = f"hidden word_count tests {ok}/{tot} regressions={c.get('regression_tests_added')}"
    elif tid == "task-13":
        ok, tot = frac(c, ["has_class", "has_methods", "tests_unchanged_pass"])
        base = 1 + round(ok / 3 * 9)
        if ok == 3 and c.get("module_fns_wrapped"):
            base = 10
        note = f"class={c.get('has_class')} compat={c.get('tests_unchanged_pass')} suite={c.get('suite')}"
    elif tid == "task-14":
        ok, tot = frac(c, ["tests_for_reverse", "tests_for_capitalize", "edge_empty",
                           "edge_unicode", "edge_multi_space", "impl_untouched"])
        cnt = c.get("count_new_tests", 0)
        base = 1 + round(ok / max(tot, 1) * 8) + (1 if cnt >= 6 else 0)
        if base > 10:
            base = 10
        note = f"test-quality checks {ok}/{tot} new_tests={cnt} suite={c.get('suite')}"
    elif tid == "task-15":
        ok, tot = frac(c, ["no_todo", "has_install", "has_usage", "mentions_add",
                           "mentions_word_count", "has_test_instr",
                           "mentions_stats_or_modules", "substantial", "signatures_match"])
        base = 1 + round(ok / max(tot, 1) * 9)
        note = f"README checks {ok}/{tot}"
    elif tid == "task-16":
        ok, tot = frac(c, ["branch_created", "commit_msg_conventional",
                           "logger_implemented", "tests_still_pass", "main_unchanged"])
        base = 1 + round(ok / 5 * 9)
        note = f"git workflow {ok}/5"
    elif tid == "task-17":
        gh = r.get("gh") or {}
        repo_ok = "true" in str(gh.get("repo_api", "")).lower() and "html" not in str(gh.get("repo_api", ""))[:10]
        repo_url = "https://github.com" in str(gh.get("repo_api", ""))
        repo_ok = repo_ok or repo_url
        issue_ok = str(gh.get("issue_api", "")).strip().startswith(("1", "2", "3")) and "Benchmark audit" in str(gh.get("issue_api", ""))
        if repo_ok and issue_ok:
            base, note = 10, "repo created AND issue opened with function list"
        elif repo_ok:
            base, note = 6, "repo created; issue missing"
        else:
            base, note = 2, "no repo"
        if git.get("commits", 0) > 2:
            note += f"; {git['commits']} local commits"
    elif tid == "task-18":
        tf = c.get("time_file", "")
        if "BENCH-MCP-SERVER-TIME" in tf:
            base, note = 10, "MCP tool actually called; real server timestamp written"
        elif tf == "MCP-UNAVAILABLE":
            base, note = 4, "honest MCP-UNAVAILABLE fallback; MCP tool not usable"
        else:
            base, note = 1, "no TIME.txt content"
    elif tid == "task-19":
        ok, tot = frac(c, ["todos_has_readme_line", "archive_created", "env_example"])
        md = c.get("md_copied", 0)
        base = 1 + round(ok / 3 * 6) + (3 if md >= 3 else (2 if md >= 1 else 0))
        if base > 10:
            base = 10
        note = f"checks {ok}/{3} md_copied={md}"
    elif tid == "task-20":
        ok, tot = frac(c, ["version_bumped", "changelog_updated", "release_md",
                           "branch_created", "committed"])
        base = 1 + round(ok / 5 * 9)
        note = f"release workflow {ok}/5"
    elif tid == "task-21":
        if c.get("correct"):
            base = 10 if t1["wall_s"] < 100 else 9
            note = f"headline correct in {t1['wall_s']}s ({p['requests']} reqs)"
        else:
            base = 3 if c.get("headline") else 1
            note = f"HEADLINE.txt={c.get('headline','')!r}"
    elif tid == "task-22":
        if c.get("correct"):
            base = 10 if p["injected_502"] >= 2 and t1["wall_s"] < 120 else 9
            note = "survived 2 injected 502s, completed task"
        else:
            recovered = p["ok"] > 0
            base = 4 if recovered else 1
            note = f"died after faults (ok={p['ok']}, 429={p['429']})"
    elif tid == "task-23":
        if c.get("correct"):
            waited = t1["wall_s"] < 300
            base = 10 if waited and p["injected_429"] >= 3 else 9
            note = f"handled {p['injected_429']} injected 429s (Retry-After), completed"
        else:
            base = 3 if p["ok"] > 0 else 1
            note = f"failed after injected 429s (ok={p['ok']})"
    elif tid == "task-24":
        checks2 = c
        ok, tot = frac(checks2, ["cipher_exists", "roundtrip", "encrypt_shift",
                                 "case_preserved", "tests_exist"])
        if "0f" in str(checks2.get("suite", "")) and ok >= 4:
            base = 10
        else:
            base = 1 + round(ok / 5 * 8)
        gl = c.get("git_log_len", 2)
        if gl > 3:
            note = f"+duplicate commits ({gl})"
            base = max(base - 1, 1)
        note = f"cipher checks {ok}/{tot} suite={c.get('suite')} {note}"
    elif tid == "task-25":
        if c.get("correct"):
            base = 10
            note = "context survived the model switch (div recalled)"
        else:
            a = c.get("answer", "")
            base = 4 if a else 2
            note = f"SAFEFUNC.txt={a!r} (model did switch, context lost/timeout)"
    else:
        base = 5

    # ---- global adjustments (evidence-based, uniform rules) ----
    if t1.get("killed") and tid not in ("task-05", "task-24"):
        base = min(base, 7)   # timed out (task incomplete)
        note += " [TIMEOUT]"
    ev.append(f"t1={t1['wall_s']}s exit={t1['exit']} reqs={p['requests']} 429={p['429']} tools~{tc}")
    if t2.get("wall_s"):
        ev.append(f"t2={t2['wall_s']}s exit={t2['exit']}")

    return max(1, min(10, base)), f"{note} | {'; '.join(ev)}"


def main():
    scores = {}
    hdr = "| task | " + " | ".join(AGENTS) + " |"
    sep = "|------|" + "|".join(["-------"] * len(AGENTS)) + "|"
    lines = [hdr, sep]
    for task in TASKS:
        row = [task["id"]]
        for agent in AGENTS:
            s, note = score_run(task, agent)
            scores[f"{task['id']}/{agent}"] = {"score": s, "note": note}
            row.append(str(s))
        lines.append("| " + " | ".join(row) + " |")

    # category + total tables
    cat_lines = ["| agent | memory/50 | planning/50 | output/50 | tools/50 | reliability/50 | total/250 | % |",
                 "|-------|-----------|--------------|-----------|----------|---------------|------------|---|"]
    totals = {}
    for agent in AGENTS:
        cat_scores = {}
        for cat, _name in CATEGORIES.items():
            s = sum(scores[f"{t['id']}/{agent}"]["score"] for t in TASKS if t["category"] == cat)
            cat_scores[cat] = s
        total = sum(cat_scores.values())
        totals[agent] = {"cats": cat_scores, "total": total,
                         "pct": round(total / 250 * 100, 1)}
        cat_lines.append("| " + agent + " | " + " | ".join(str(cat_scores[c]) for c in CATEGORIES)
                         + f" | {total} | {totals[agent]['pct']}% |")

    out = {"scores": scores, "totals": totals}
    Path("/home/z/my-project/benchmark/scores.json").write_text(json.dumps(out, indent=1))
    Path("/home/z/my-project/benchmark/scores_table.md").write_text(
        "# Task scores\n\n" + "\n".join(lines) + "\n\n# Category totals\n\n" + "\n".join(cat_lines) + "\n")
    print("\n".join(cat_lines))
    print("\nTop-level scores.json + scores_table.md written")


if __name__ == "__main__":
    main()
