from __future__ import annotations

"""
SHS Code CLI — Persistent Autonomous Coding Shell
=================================================
Type: SHSCode

SHS Code is part of the SHS Lab ecosystem (Sazzad Hussain Shobuj).

The interactive shell is a persistent agent environment:
  - Memory, task journal and checkpoints survive restarts
  - /model and /provider switch the reasoning backend LIVE — context,
    memory, files and task progress are never destroyed
  - NVIDIA NIM (and any provider) paced by a true rolling-window limiter
    — rate-limit waits preserve all state
  - Interrupted tasks are detected and resumable on next launch

Slash commands — all backed by real functionality:
  /help /status /version /tasks /task /resume /pause /stop /continue
  /model /models /providers /provider /skills /skill /mcp /tools
  /channels /connectors /config /context /checkpoint /history /files
  /search /git /doctor /log /debug /clear /new /bg /sessions /compress
  /branch /exit

Plain `exit` also exits. Ctrl+C during a run interrupts the task (state is
checkpointed); at the prompt it exits cleanly.
"""

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional
from app import env

# ──────────────────────────────────────────────────────────────────────────────
# Version / branding
# ──────────────────────────────────────────────────────────────────────────────

VERSION = "3.0.3"           # SHS Code — chat-mode directive, clean console, any-dir env

SHS_BANNER = r"""
███████╗██╗  ██╗███████╗  ██████╗ ██████╗ ██████╗ ██████╗
██╔════╝██║  ██║██╔════╝ ██╔════╝██╔═══██╗██╔══██╗██╔══██╗
███████╗███████║███████╗ ██║     ██║   ██║██████╔╝██████╔╝
╚════██║██╔══██║╚════██║ ██║     ██║   ██║██╔══██╗██╔═══╝
███████║██║  ██║███████╗ ╚██████╗╚██████╔╝██║  ██║██║
╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝
"""

# ──────────────────────────────────────────────────────────────────────────────
# Skins
# ──────────────────────────────────────────────────────────────────────────────

SKINS = {
    "default": {"border": "gold1",          "accent": "yellow",  "user": "cyan",     "agent": "green",  "tool": "magenta", "error": "red"},
    "ares":    {"border": "red1",            "accent": "red",     "user": "white",    "agent": "red",    "tool": "orange1", "error": "bright_red"},
    "mono":    {"border": "white",           "accent": "white",   "user": "white",    "agent": "bright_white", "tool": "grey70", "error": "white"},
    "slate":   {"border": "steel_blue1",     "accent": "blue",    "user": "sky_blue1","agent": "pale_green1","tool": "orchid","error": "red"},
}

ROLE_EMOJI = {"user": "👤", "assistant": "🤖", "tool": "🔧", "system": "⚙"}

SLASH_COMMANDS = [
    "/help", "/status", "/version", "/tasks", "/task", "/resume", "/pause",
    "/stop", "/continue", "/model", "/models", "/providers", "/provider",
    "/skills", "/skill", "/mcp", "/tools", "/channels", "/connectors",
    "/config", "/context", "/checkpoint", "/history", "/files", "/search",
    "/git", "/doctor", "/log", "/debug", "/clear", "/new", "/bg",
    "/sessions", "/compress", "/branch", "/exit",
    # Phase 2 (spec §40-§43, §28, §33, §36, §37)
    "/plan", "/usage", "/project", "/env", "/mode", "/profile",
    "/rollback", "/verify",
    # Stabilization pass: previously-advertised commands that did not exist
    "/undo", "/retry", "/browser",
]


def _get_skin(name: str = "default") -> dict:
    """Load skin: check ~/.shscode/skins/<name>.yaml first, then built-ins."""
    from pathlib import Path
    import os
    skin_file = Path(env.home_dir()) / "skins" / f"{name}.yaml"
    if skin_file.exists():
        try:
            import yaml
            data = yaml.safe_load(skin_file.read_text()) or {}
            if data:
                return {**SKINS.get("default", {}), **data}
        except Exception:
            pass
    return SKINS.get(name, SKINS["default"])


# ──────────────────────────────────────────────────────────────────────────────
# Rich-based output helpers
# ──────────────────────────────────────────────────────────────────────────────

def _console():
    try:
        from rich.console import Console
        return Console()
    except ImportError:
        return None


def _print_banner(skin: dict, model_name: str = "", provider: str = "") -> None:
    """Print the SHS Code ASCII activation banner (spec §2)."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        console = Console()
        banner_text = Text()
        banner_text.append(SHS_BANNER, style=f"bold {skin['accent']}")
        banner_text.append("\nSHS Code initialized.", style="bold white")
        banner_text.append("\nSazzad Hussain Shobuj · SHS Lab", style="dim")
        if provider or model_name:
            banner_text.append(f"\nProvider: {provider or '-'}  Model: {model_name or '-'}", style="dim")
        banner_text.append(f"\nPersistent memory ON · task journal ON · rate limiter ON", style="dim")
        banner_text.append("\nType your task naturally. /help for commands.", style="dim")
        console.print(Panel(banner_text, border_style=skin["border"], expand=False, padding=(0, 2)))
    except ImportError:
        print(SHS_BANNER)
        print("SHS Code initialized.  (Sazzad Hussain Shobuj · SHS Lab)")
        if provider or model_name:
            print(f"Provider: {provider or '-'}  Model: {model_name or '-'}")
        print("Type your task naturally. /help for commands.\n")


def _print_header(skin: dict, model: str, session_id: str, step: int = 0) -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
        console = Console()
        console.print(Panel(
            f"[bold {skin['accent']}]SHS Code[/] | model: {model} | session: {session_id[:8] if session_id else '-'} | step: {step}",
            border_style=skin["border"],
            expand=True,
        ))
    except ImportError:
        print(f"=== SHS Code | {model} | {session_id[:8] if session_id else '-'} ===")


def _print_message(role: str, content: str, skin: dict) -> None:
    emoji = ROLE_EMOJI.get(role, "•")
    color = skin.get(role if role in ("user", "tool", "error") else "agent", "white")
    try:
        from rich.console import Console
        from rich.markdown import Markdown
        console = Console()
        label = f"[{color}]{emoji} {role.upper()}[/{color}]"
        if role == "assistant":
            console.print(f"{label}")
            console.print(Markdown(content))
        else:
            console.print(f"{label}: {content[:4000]}")
    except ImportError:
        print(f"{emoji} {role.upper()}: {content[:500]}")


def _print_tool_activity(tool_name: str, args_preview: str, skin: dict) -> None:
    try:
        from rich.console import Console
        console = Console()
        console.print(f"  [{skin['tool']}]🔧 {tool_name}[/] — {args_preview[:80]}")
    except ImportError:
        print(f"  [TOOL] {tool_name}: {args_preview[:80]}")


# ──────────────────────────────────────────────────────────────────────────────
# Live activity display (spec §32) — subscribes to the ActivityBus
# ──────────────────────────────────────────────────────────────────────────────

def _make_activity_printer(skin: dict, enabled: bool = True):
    """Return a subscriber fn for ActivityBus that prints concise live lines:
    Thinking... / ⚒ bash — cmd / ✓ done / ⏳ rate-limit wait / 💾 checkpoint."""
    if not enabled:
        return lambda kind, data: None

    console = _console()
    a = skin.get("accent", "yellow")
    t = skin.get("tool", "magenta")
    e = skin.get("error", "red")

    def printer(kind: str, data: dict) -> None:
        try:
            if kind == "llm_start":
                line = f"[dim {a}]▸ thinking ({data.get('model', '')})…[/]"
            elif kind == "tool_start":
                preview = (data.get("args_preview") or "")[:70]
                line = f"[{t}]⚒ {data.get('tool', '?')}[/] — {preview}"
            elif kind == "tool_end":
                ok = data.get("success", True)
                mark = "✓" if ok else "✗"
                style = a if ok else e
                prev = (data.get("preview") or "")[:60].replace("\n", " ")
                line = f"[{style}]{mark} {data.get('tool', '?')}[/][dim] {prev}[/]"
            elif kind == "rate_limit_wait":
                line = (f"[{e}]⏳ Rate limited. Waiting for capacity…[/]"
                        f"[dim] {data.get('provider', '')} {data.get('rpm', '')}rpm, "
                        f"{data.get('wait_s', '')}s (rolling window — state preserved)[/]")
            elif kind == "rate_limit_resume":
                line = f"[{a}]▲ Capacity available. Continuing…[/][dim] waited {data.get('waited_s', '')}s[/]"
            elif kind == "checkpoint":
                line = f"[dim]💾 checkpoint saved (step {data.get('step', '?')})[/]"
            elif kind == "model_switch":
                line = f"[{a}]⇄ model switched → {data.get('model', '')}[/][dim] context preserved[/]"
            elif kind == "provider_switch":
                line = f"[{a}]⇄ provider switched → {data.get('provider', '')} {data.get('model', '')}[/][dim] context preserved[/]"
            elif kind == "memory_recall":
                line = f"[dim]🧠 recalled {data.get('count', 0)} persistent memories[/]"
            # ── Phase 2 (spec §58: user-facing activity) ──
            elif kind == "analyzing":
                line = f"[{a}]⏳ Analyzing repository…[/][dim] {data.get('project', '')}[/]"
            elif kind == "indexing":
                line = f"[{a}]🔍 Indexing project…[/][dim] {data.get('project', '')}[/]"
            elif kind == "indexed":
                line = (f"[dim]🔍 Indexed {data.get('files', 0):,} files, "
                        f"{data.get('symbols', 0):,} symbols ({data.get('ms', 0)}ms, incremental)[/]")
            elif kind == "plan_created":
                line = f"[{a}]📋 Plan created: {data.get('nodes', 0)} tasks[/][dim] dependency-aware, persisted[/]"
            elif kind == "verifying":
                line = (f"[{a}]✓ Verifying…[/][dim] {data.get('level', '')} "
                        f"{str(data.get('kinds') or '')[:40]}[/]")
            elif kind == "parallel_tools":
                line = (f"[{t}]⚡ parallel tools x{data.get('count', 0)}[/][dim] "
                        f"{', '.join((data.get('tools') or [])[:4])}[/]")
            elif kind == "review_phase":
                line = f"[{a}]🔍 Code review phase[/][dim] after {data.get('file_edits', 0)} file edits[/]"
            elif kind == "rollback_snapshot":
                line = (f"[dim]🛟 rollback snapshot: {data.get('file', '')}[/]")
            elif kind == "subagent_start":
                line = f"[{t}]Spawn subagent {data.get('sub_id', '')}[/][dim] {data.get('role', '')}[/]"
            elif kind == "subagent_end":
                line = f"[{t}]Subagent {data.get('sub_id', '')} {data.get('status', '')}[/]"
            elif kind == "blocked":
                line = f"[{e}]⏸ Blocked: {str(data.get('reason', ''))[:80]}[/]"
            else:
                return
            if console is not None:
                console.print(line)
            else:
                import re as _re
                print("  " + _re.sub(r"\[/?[^\]]+\]", "", line))
        except Exception:
            pass

    return printer


# ──────────────────────────────────────────────────────────────────────────────
# Spinner (preserved; used in single-shot mode)
# ──────────────────────────────────────────────────────────────────────────────

class Spinner:
    """Contextual spinner using Rich if available, otherwise plain text."""

    def __init__(self, verb: str = "thinking", skin: Optional[dict] = None) -> None:
        self.verb = verb
        self.skin = skin or SKINS["default"]
        self._status = None
        self._console = None
        self._start_time = None

    def __enter__(self):
        import time as _time
        self._start_time = _time.monotonic()
        try:
            from rich.console import Console
            self._console = Console()
            self._status = self._console.status(
                f"[{self.skin['accent']}]{self.verb}...[/]", spinner="dots"
            )
            self._status.__enter__()
        except ImportError:
            print(f"  {self.verb}...", end="", flush=True)
        return self

    def update(self, verb: str = None, elapsed: float = None) -> None:
        if verb:
            self.verb = verb
        try:
            if self._status and self._console:
                msg = f"[{self.skin['accent']}]{self.verb}...[/]"
                if elapsed and elapsed > 30:
                    mins, secs = divmod(int(elapsed), 60)
                    msg += f" [{min(secs, 59)}s elapsed]"
                    if elapsed > 120:
                        msg = f"[{self.skin['accent']}]{self.verb}...[/] [{mins}m {secs}s elapsed]"
                self._status.update(msg)
        except Exception:
            pass

    def __exit__(self, *args):
        if self._status:
            self._status.__exit__(*args)
        else:
            print(" done")


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers for slash commands
# ──────────────────────────────────────────────────────────────────────────────

def _journal():
    try:
        from app.state import Journal
        return Journal.get()
    except Exception:
        return None


def _fmt_ts(ts: Optional[float]) -> str:
    if not ts:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return str(ts)


def _rel_ts(ts: Optional[float]) -> str:
    if not ts:
        return "-"
    d = time.time() - ts
    if d < 60:
        return f"{int(d)}s ago"
    if d < 3600:
        return f"{int(d // 60)}m ago"
    if d < 86400:
        return f"{int(d // 3600)}h ago"
    return f"{int(d // 86400)}d ago"


def _mask(value: Optional[str]) -> str:
    if not value:
        return "(not set)"
    v = str(value)
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:5]}…{v[-4:]}"


# ──────────────────────────────────────────────────────────────────────────────
# Slash command handler (spec §10-§13) — every command is REAL functionality
# Returns: string to print, or sentinels "EXIT" / "NEW_SESSION" / "SPAWN_TASK:<t>"
# ──────────────────────────────────────────────────────────────────────────────

async def _handle_slash(cmd: str, agent=None, session_id: str = "",
                        task_queue=None, runtime: Optional[dict] = None) -> Optional[str]:
    runtime = runtime or {}
    parts = cmd.strip().split(None, 1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    # ------------------------------------------------------------------ help
    if command in ("/help", "/?"):
        return (
            "SHS Code Commands:\n"
            "  Session & Tasks\n"
            "    /status            — full state: task, progress, provider, memory\n"
            "    /tasks [status]    — list tasks (all|active|completed|failed|interrupted)\n"
            "    /task [id]         — detailed task state (files, commands, errors)\n"
            "    /resume [id]       — resume interrupted task (restores full context)\n"
            "    /pause             — interrupt current run (state checkpointed)\n"
            "    /stop              — cancel current run\n"
            "    /continue          — re-submit the last prompt\n"
            "    /checkpoint        — force a persistent checkpoint now\n"
            "    /history           — recent journal events\n"
            "    /files             — files changed by current/last task\n"
            "  Model & Providers\n"
            "    /model [name]      — show/switch model (context preserved!)\n"
            "    /models            — available models\n"
            "    /providers         — configured providers (built-in + custom)\n"
            "    /provider <n> [model] — switch provider (optionally set model)\n"
            "    /provider add|remove|set-key ... — manage custom providers\n"
            "  Memory\n"
            "    /memory            — persistent long-term memory entries\n"
            "    /remember <text>   — store a persistent memory\n"
            "    /forget <text|all> — remove matching memories\n"
            "  Skills / Tools / MCP\n"
            "    /skills            — list skills   · /skill info|enable|disable <n>\n"
            "    /tools             — list agent tools\n"
            "    /mcp               — list/inspect/enable/disable MCP servers\n"
            "  Platform\n"
            "    /connectors        — platform connectors (github, gitlab, …)\n"
            "    /channels          — configured messaging channels\n"
            "    /git               — repository state (branch, changes)\n"
            "    /search <query>    — search sessions + journal (FTS)\n"
            "  System\n"
            "    /config            — effective config (secrets masked)\n"
            "    /context           — context window usage of current session\n"
            "    /doctor            — diagnostics\n"
            "    /log [n]           — last n log lines\n"
            "    /debug on|off      — toggle debug logging\n"
            "    /version           — version info\n"
            "    /clear             — clear screen\n"
            "    /new               — fresh session (memory persists on disk)\n"
            "    /bg <task>         — background queue   · /tasks to monitor\n"
            "    /sessions …        — list|history|send|spawn|switch|rename|archive|delete\n"
            "    /compress          — structured context compaction (state-preserving)\n"
            "    /branch            — branch current session\n"
            "  Phase 2 — Intelligence & Autonomy\n"
            "    /plan              — persisted dependency-aware plan + resume check\n"
            "    /verify [level]    — project-aware build/test verification NOW\n"
            "    /project [action]  — project intelligence: summary|architecture|entry|git|refresh\n"
            "    /env               — development environment (tools, runtimes)\n"
            "    /usage             — provider usage: requests, latency, tokens, cost\n"
            "    /mode [name]       — agent modes: coding|debugging|reviewer|research|autonomous|planning\n"
            "    /profile …         — custom agent profiles (list|use|create|remove|off)\n"
            "    /rollback [task]   — snapshots + restore agent-changed files\n"
            "    /exit              — quit (or just type: exit)"
        )

    if command in ("/exit", "/quit"):
        return "EXIT"

    if command == "/version":
        return (f"SHS Code v{VERSION} (SHS Lab — Sazzad Hussain Shobuj)\n"
                f"Python {sys.version.split()[0]}")

    if command == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        return None

    # ------------------------------------------------------------------ status
    if command == "/status":
        lines = ["SHS Code Status", "=" * 58]
        try:
            from app.git_intel import GitIntelligence
            gi = GitIntelligence()
            gs = gi.state()
            branch = gs.get("branch", "(not a git repo)") if gs.get("is_repo") else "(not a git repo)"
        except Exception:
            branch = "(git unavailable)"
        lines.append(f"Project:   {os.path.basename(os.getcwd())}  [{branch}]")
        j = _journal()
        if j is not None:
            st = await j.current_status()
            t = st.get("active_task")
            if t:
                prog = t.get("progress") or {}
                comp = len(prog.get("completed") or [])
                pend = len(prog.get("pending") or [])
                lines.append(f"Task:      {t.get('goal', '')[:60]}")
                lines.append(f"Status:    {t.get('status')} | steps: {t.get('step_count')} | "
                             f"tools: {t.get('tool_calls')}")
                if comp or pend:
                    lines.append(f"Progress:  {comp} done / {pend} pending "
                                 f"({j.progress_percent(t)}%)")
                if t.get("phase"):
                    lines.append(f"Phase:     {t.get('phase')}")
                files = t.get("files_changed") or []
                if files:
                    lines.append(f"Files:     {len(files)} changed by this task")
                tests = t.get("test_results") or []
                if tests:
                    tp = sum(1 for x in tests if x.get("passed"))
                    tf = len(tests) - tp
                    lines.append(f"Tests:     {tp} passed, {tf} failed")
                verif = t.get("verification") or {}
                if verif:
                    mark = "✓" if verif.get("ok") else "✗"
                    lines.append(f"Verify:    {mark} {(verif.get('summary') or '')[:60]}")
                lines.append(f"Last ok:   {(t.get('last_success') or '-')[:70]}")
                lines.append(f"Last err:  {(t.get('last_error') or '-')[:70]}")
                if t.get("blocked_reason"):
                    lines.append(f"BLOCKED:   {t.get('blocked_reason')[:70]}")
                lines.append(f"Checkpoint: {_rel_ts(st.get('last_checkpoint_ts'))}")
                if t.get("next_action"):
                    lines.append(f"Next:      {str(t.get('next_action'))[:70]}")
            else:
                lines.append("Task:      (none active)")
            bs = st.get("tasks_by_status") or {}
            lines.append("Tasks:     " + ", ".join(f"{k}={v}" for k, v in sorted(bs.items())))
        # provider/model
        try:
            info = agent.llm.backend_info()
            lines.append(f"Provider:  {info['provider']}  ({info['backend']})")
            lines.append(f"Model:     {info['model']}")
            if info.get("base_url"):
                lines.append(f"Endpoint:  {info['base_url']}")
        except Exception:
            from app.config import Config
            c = Config.get()
            lines.append(f"Provider:  {c.llm.provider}  Model: {c.llm.model}")
        # provider health (Phase 2, spec §21)
        try:
            from app.provider_health import get_health
            hs = list(get_health().stats().values())
            if hs:
                cur = hs[0]
                lines.append(f"Health:    {cur['status']} success={cur['success_rate']} "
                             f"latency={cur['latency_avg_s']}s req={cur['requests']}")
        except Exception:
            pass
        # rate limiter
        try:
            from app.llm.rate_limiter import all_stats
            stats = all_stats()
            if stats:
                for v in stats.values():
                    lines.append(f"RateLimit: {v['provider']} rpm={v['rpm']} "
                                 f"in_window={v['in_window']} next_wait={v['next_wait_s']}s")
        except Exception:
            pass
        # memory
        try:
            if agent is not None and getattr(agent, "long_term_memory", None):
                cnt = await agent.long_term_memory.count()
                lines.append(f"Memory:    persistent ({cnt} entries, SQLite)")
            else:
                lines.append("Memory:    persistent (0 entries)")
        except Exception:
            lines.append("Memory:    persistent")
        lines.append(f"Context:   {len(agent.memory.messages) if agent else 0} messages "
                     f"(~{agent.memory.token_estimate() if agent else 0} tokens)")
        lines.append(f"Session:   {session_id[:12] or '-'}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ tasks
    if command == "/tasks":
        j = _journal()
        if j is None:
            return "Journal unavailable."
        filt = arg.strip().lower() or "all"
        if filt in ("active", "running"):
            # SHS Code FIX: 'active'/'running' omitted in_progress — the
            # actually-running task was invisible to /tasks active.
            rows = (await j.list_tasks("in_progress")
                    + await j.list_tasks("interrupted")
                    + await j.list_tasks("paused"))
        else:
            rows = await j.list_tasks() if filt == "all" else await j.list_tasks(filt)
        if not rows:
            return f"No {filt} tasks."
        lines = [f"{'TASK':<14} {'STATUS':<12} {'STEPS':<6} {'GOAL'}", "-" * 70]
        for t in rows[:30]:
            lines.append(f"  {t['task_id']:<14} {t['status']:<12} {t.get('step_count', 0):<6} "
                         f"{(t.get('goal') or '')[:44]}")
        lines.append(f"\n{len(rows)} task(s). /task <id> for details, /resume <id> to continue.")
        return "\n".join(lines)

    if command == "/task":
        j = _journal()
        if j is None:
            return "Journal unavailable."
        tid = arg.strip() or (agent._journal_task_id if agent else None)
        if not tid:
            t = (await j.current_status()).get("active_task")
            tid = t["task_id"] if t else None
        if not tid:
            return "No task id given and none active."
        t = await j.get_task(tid)
        if not t:
            return f"Task {tid} not found."
        prog = t.get("progress") or {}
        lines = [f"Task {t['task_id']}", "=" * 58, f"Goal:    {t.get('goal', '')}",
                 f"Status:  {t.get('status')}",
                 f"Steps:   {t.get('step_count')} | tool calls: {t.get('tool_calls')}",
                 f"Created: {_fmt_ts(t.get('created_at'))}  Updated: {_rel_ts(t.get('updated_at'))}"]
        if prog.get("completed"):
            lines.append("Completed:")
            lines += [f"  [x] {x}" for x in prog["completed"][:10]]
        if prog.get("in_progress"):
            lines.append("In progress:")
            lines += [f"  [~] {x}" for x in prog["in_progress"][:5]]
        if prog.get("pending"):
            lines.append("Pending:")
            lines += [f"  [ ] {x}" for x in prog["pending"][:10]]
        files = t.get("files_changed") or []
        if files:
            lines.append("Files changed:")
            lines += [f"  {f.get('op', '?'): <9} {f.get('path', '')}" for f in files[:15]]
        cmds = t.get("commands") or []
        if cmds:
            lines.append(f"Commands run: {len(cmds)} (last: {(cmds[-1].get('cmd') or '')[:50]})")
        lines.append(f"Last success: {(t.get('last_success') or '-')[:70]}")
        lines.append(f"Last error:   {(t.get('last_error') or '-')[:70]}")
        evs = await j.events(tid, limit=8)
        if evs:
            lines.append("Recent events:")
            lines += [f"  {_rel_ts(e['ts'])} {e['kind']} {e.get('tool') or ''}" for e in evs]
        return "\n".join(lines)

    # ------------------------------------------------------------------ resume
    if command == "/resume":
        j = _journal()
        if j is None or agent is None:
            return "Journal/agent unavailable."
        tid = arg.strip()
        if not tid:
            t = await j.last_interrupted()
            tid = t["task_id"] if t else None
            if not tid:
                rows = await j.list_tasks("paused")
                tid = rows[0]["task_id"] if rows else None
                if not tid:
                    rows = await j.list_tasks("blocked")
                    tid = rows[0]["task_id"] if rows else None
        if not tid:
            return "No interrupted/paused/blocked task to resume. /tasks to list."
        t = await j.get_task(tid)
        cp = await j.load_checkpoint(tid)
        if not t:
            return f"Task {tid} not found."
        # SHS Code Phase 2 (spec §10 EXACT RESUME): verify stored state against
        # the real filesystem + git BEFORE continuing — never trust a stale
        # checkpoint blindly. Also detects already-done work (spec §11).
        resume_report = ""
        try:
            from app.planner import verify_resume_state, render_resume_report
            report = await verify_resume_state(j, tid)
            resume_report = render_resume_report(report)
        except Exception as e:
            resume_report = f"(resume verification unavailable: {e})"
        from app.schema import Message
        restored = 0
        if cp and cp.get("memory"):
            agent.memory.messages = [Message.from_dict(m) for m in cp["memory"]]
            restored = len(cp["memory"])
        prog = t.get("progress") or {}
        comp = len(prog.get("completed") or [])
        total = comp + len(prog.get("in_progress") or []) + len(prog.get("pending") or [])
        pct = int(100 * comp / total) if total else 0
        summary = (
            f"TASK RESUMED — continue from existing state, do NOT restart from zero.\n"
            f"Goal: {t.get('goal', '')}\nStatus was: {t.get('status')} | steps done: {t.get('step_count')}\n"
            f"Progress: {pct}% ({comp}/{total} items) | phase: {t.get('phase') or '-'}\n"
            f"Last successful action: {t.get('last_success') or '-'}\n"
            f"Last failed action: {t.get('last_error') or '-'}\n"
            f"\nEXACT-RESUME VERIFICATION (real state checked against the checkpoint):\n"
            f"{resume_report[:1800]}\n"
            f"\nRules: inspect the filesystem before repeating any operation;\n"
            f"completed work must not be redone; verify claimed-but-missing work first."
        )
        agent.memory.add(Message.system(summary))
        await j.task_update(tid, status="in_progress")
        agent._journal_task_id = tid
        # SHS Code Phase 2 (spec §26): recover subagent state for this task
        try:
            from app.subagents import mark_interrupted_subagents, list_subagents, render_subagents
            await mark_interrupted_subagents(j, tid)
            subs = await list_subagents(j, tid)
            if subs:
                agent.memory.add(Message.system(
                    "SUBAGENT STATE (recovered):\n" + render_subagents(subs)[:1200]))
        except Exception:
            pass
        # SHS Code Phase 2 (spec §22): the resumed plan graph rides along
        try:
            from app.task_dag import TaskGraph
            g = await TaskGraph(j, tid).load()
            if g.nodes():
                agent._plan_graph = g
                agent.memory.add(Message.system(
                    "PLAN (restored, persisted):\n" + g.to_prompt()))
        except Exception:
            pass
        from app.schema import AgentState
        agent.state = AgentState.IDLE
        agent._step_count = 0
        return (f"Resumed task {tid}.\nGoal: {t.get('goal', '')[:60]}\n"
                f"Progress: {pct}% | restored {restored} context messages.\n\n"
                f"{resume_report[:1500]}\n\n"
                f"Continue by describing the next step, or /continue to re-run the last prompt.")

    # ------------------------------------------------------------------ run control
    if command == "/pause":
        task = runtime.get("current_run_task")
        if task and not task.done():
            task.cancel()
            return "Pause requested — the current run will be interrupted at the next await. State is checkpointed; use /resume or /continue."
        return "No run in progress."

    if command == "/stop":
        task = runtime.get("current_run_task")
        if task and not task.done():
            task.cancel()
            if runtime.get("last_prompt"):
                return "Stopped. State checkpointed. /resume to continue later."
            return "Stopped."
        return "No run in progress."

    if command == "/continue":
        last = runtime.get("last_prompt")
        if not last:
            return "Nothing to continue."
        return f"SPAWN_PROMPT:{last}"

    # ------------------------------------------------------------------ model switch
    if command == "/model":
        if agent is None or not hasattr(agent, "llm"):
            return "No agent active."
        if arg:
            info = await agent.llm.switch(model=arg.strip())
            from app.config import Config
            Config.get().save_llm()
            return (f"Model switched to {info['model']}.\n"
                    f"Context, memory, task state and files are all preserved —\n"
                    f"the model is only the reasoning engine (spec §4).")
        try:
            info = agent.llm.backend_info()
            return f"Current model: {info['model']} (provider: {info['provider']})"

        except Exception:
            from app.config import Config
            c = Config.get()
            return f"Current model: {c.llm.model} (provider: {c.llm.provider})"

    if command == "/models":
        from app.config import Config
        cfg = Config.get()
        lines = ["Available models:"]
        try:
            info = agent.llm.backend_info() if agent else {}
            lines.append(f"  active: {info.get('provider', cfg.llm.provider)} / {info.get('model', cfg.llm.model)}")
        except Exception:
            lines.append(f"  active: {cfg.llm.provider} / {cfg.llm.model}")
        from app.providers import get_providers, KNOWN_MODELS
        custom = get_providers().list(masked=True)
        for p in custom:
            models = get_providers().models_for(p["name"])
            if models:
                lines.append(f"  [{p['name']}] {', '.join(models[:6])}")
        for prov, models in KNOWN_MODELS.items():
            lines.append(f"  [{prov}] {', '.join(models[:5])}")
        lines.append("\nSwitch with: /model <name>  or  /provider <name> <model>")
        return "\n".join(lines)

    # ------------------------------------------------------------------ providers
    if command == "/provider":
        from app.providers import get_providers, API_TYPES
        from app.config import Config
        reg = get_providers()
        if not arg:
            info = agent.llm.backend_info() if agent and hasattr(agent, "llm") else {}
            lines = ["Built-in providers:",
                     "  openai · anthropic · google · mistral · bedrock · universal",
                     "  openrouter · lmstudio · groq · together · perplexity · ollama · gguf · huggingface",
                     f"Active: {info.get('provider', '')} / {info.get('model', '')}",
                     "\nCustom providers:"]
            custom = reg.list(masked=True)
            if not custom:
                lines.append("  (none) — add one: /provider add <name> openai-compat <base_url> <model> [api_key]")
            for p in custom:
                lines.append(f"  {p['name']} ({p['api_type']}) model={p.get('model', '-')} "
                             f"key={p.get('api_key', '-')} rpm={p.get('rpm') or '-'} "
                             f"{'[enabled]' if p.get('enabled') else '[disabled]'}")
            return "\n".join(lines)
        sub = arg.split()
        if sub[0] == "add":
            # /provider add <name> <api_type> <base_url> <model> [api_key] [rpm]
            if len(sub) < 5:
                return ("Usage: /provider add <name> <api_type> <base_url> <model> [api_key] [rpm]\n"
                        f"api_type: {' | '.join(sorted(API_TYPES))}")
            try:
                # SHS Code FIX: the old parser treated a digit-only API key as
                # rpm and silently dropped real keys. Parse the tail properly:
                # first trailing token = api_key, second (if numeric or 'rpm=') = rpm.
                api_key = ""
                rpm = 0
                tail = sub[5:]
                if tail:
                    api_key = tail[0]
                if len(tail) > 1:
                    tok = tail[1].lower()
                    if tok.startswith("rpm="):
                        tok = tok[4:]
                    if tok.isdigit():
                        rpm = int(tok)
                e = reg.add(name=sub[1], api_type=sub[2], base_url=sub[3],
                            model=sub[4], api_key=api_key, rpm=rpm)
                return (f"Provider '{e['name']}' registered (persisted to ~/.shscode/providers.json).\n"
                        f"Switch to it: /provider {e['name']}")
            except ValueError as ex:
                return f"Error: {ex}"
        if sub[0] == "remove" and len(sub) > 1:
            return f"Removed {sub[1]}." if reg.remove(sub[1]) else f"No provider named {sub[1]}."
        if sub[0] == "set-key" and len(sub) > 2:
            e = reg.get(sub[1])
            if not e:
                return f"No provider named {sub[1]}."
            # SHS Code FIX: stored entries carry 'added_at' (and possibly other
            # bookkeeping keys) which ProviderRegistry.add() does not accept —
            # spreading them raised TypeError and the key was never updated.
            ctor_keys = {"name", "api_type", "base_url", "model", "api_key", "rpm"}
            reg.add(**{**{k: v for k, v in e.items() if k in ctor_keys},
                       "api_key": sub[2]})
            return f"API key updated for {sub[1]} (masked: {'*' * 8})."
        # /provider <name> [model] — switch
        name = sub[0]
        model = sub[1] if len(sub) > 1 else None
        entry = reg.get(name)
        if entry is None:
            built_in = {"openai", "anthropic", "google", "gemini", "mistral",
                        "bedrock", "universal", "openrouter", "lmstudio",
                        "groq", "together", "perplexity", "ollama", "gguf",
                        "huggingface", "hf", "mock"}
            if name not in built_in:
                return (f"Unknown provider '{name}'. Use /provider add ... for custom,\n"
                        f"or one of: {', '.join(sorted(built_in))}")
            if agent is None or not hasattr(agent, "llm"):
                return "No agent active."
            info = await agent.llm.switch(provider=name, model=model)
        else:
            if agent is None or not hasattr(agent, "llm"):
                return "No agent active."
            cfg = Config.get()
            reg.provider_overlay(name, cfg)
            info = await agent.llm.switch(provider=cfg.llm.provider,
                                          model=model or cfg.llm.model,
                                          base_url=cfg.llm.base_url,
                                          api_key=cfg.llm.api_key)
            if entry.get("rpm"):
                cfg.llm.rate_limit.rpm = int(entry["rpm"])
        Config.get().save_llm()
        return (f"Provider switched to {info['provider']} / {info['model']}\n"
                f"Context, memory and task progress fully preserved (spec §4/§17).")

    if command == "/providers":
        return await _handle_slash("/provider", agent, session_id, task_queue, runtime)

    # ------------------------------------------------------------------ memory
    if command == "/memory":
        if agent is None or not getattr(agent, "long_term_memory", None):
            return "Long-term memory unavailable."
        entries = await agent.long_term_memory.get_recent(k=15)
        if not entries:
            return "Memory is empty. /remember <fact> to store your first memory."
        lines = [f"Persistent memory ({await agent.long_term_memory.count()} entries, survives restarts & model switches):"]
        for en in entries:
            lines.append(f"  [{en['id'][:8]}] {_rel_ts(en.get('ts'))} — {(en.get('content') or '')[:90]}")
        lines.append("\n/remember <text> · /forget <text|id|all>")
        return "\n".join(lines)

    if command == "/remember":
        if not arg:
            return "Usage: /remember <information to persist>"
        if agent is None or not getattr(agent, "long_term_memory", None):
            return "Long-term memory unavailable."
        mid = await agent.long_term_memory.store(arg, meta={"source": "user:/remember"})
        return f"Remembered [{mid[:8]}]: {arg[:80]}\nThis memory survives restarts, model and provider switches."

    if command == "/forget":
        if agent is None or not getattr(agent, "long_term_memory", None):
            return "Long-term memory unavailable."
        target = arg.strip()
        if not target:
            return "Usage: /forget <text-or-id> | all"
        ltm = agent.long_term_memory
        if target.lower() == "all":
            async def _nuke():
                entries = await ltm.get_recent(k=100000)
                for en in entries:
                    await ltm.delete(en["id"])
            await _nuke()
            return "All persistent memories removed."
        deleted = 0
        entries = await ltm.search(target, k=10)
        if not entries:
            entries = await ltm.get_recent(k=50)
            entries = [e for e in entries if target.lower() in (e.get("content") or "").lower()]
        if len(target) == 8 or (len(target) > 8 and target[:8].isalnum()):
            entries += [e for e in await ltm.get_recent(k=200) if e["id"].startswith(target[:8])]
        for en in entries:
            try:
                await ltm.delete(en["id"])
                deleted += 1
            except Exception:
                pass
        return f"Forgot {deleted} memory entr{'y' if deleted == 1 else 'ies'}."

    # ------------------------------------------------------------------ skills
    if command == "/skills":
        try:
            from app.skills.skill_engine import get_skill_engine
            engine = get_skill_engine()
            skills = engine.list_skills()
            if not skills:
                return "No skills loaded."
            lines = [f"{len(skills)} skill(s) loaded — levels: builtin · user · project · installed:"]
            for s in skills:
                state = "OFF" if engine.is_disabled(s.name) else "on"
                lines.append(f"  [{s.level:<9}] {s.name} v{s.version} [{state}]: {s.description[:56]}")
            lines.append("\n/skill info|enable|disable|install|create|remove|reload <name>")
            return "\n".join(lines)
        except Exception as e:
            return f"Skills error: {e}"

    if command == "/skill":
        sub = arg.split(None, 1)
        if not sub:
            return ("Usage: /skill info|enable|disable|reload <name>\n"
                    "       /skill install <git-url|path> [name]\n"
                    "       /skill create <name> <description>\n"
                    "       /skill remove <name>")
        try:
            from app.skills.skill_engine import get_skill_engine
            engine = get_skill_engine()
            action = sub[0].lower()
            if action == "reload":
                engine.reload()
                return f"Skills reloaded: {len(engine.list_skills())} skill(s)."
            if action == "install":
                toks = (sub[1] if len(sub) > 1 else "").split()
                if not toks:
                    return "Usage: /skill install <git-url|path> [name]"
                try:
                    s = engine.install(toks[0], toks[1] if len(toks) > 1 else None)
                    return f"Installed skill '{s.name}' (v{s.version}) into ~/.shscode/skills/installed/"
                except Exception as e:
                    return f"Install failed: {e}"
            if action == "create":
                toks = (sub[1] if len(sub) > 1 else "").split(None, 1)
                if len(toks) < 2:
                    return "Usage: /skill create <name> <description>"
                name, desc = toks[0].strip(), toks[1].strip()
                s = engine.create(name, desc, content=f"# {name}\n\n{desc}\n\n(Author this skill's guidance here — it is injected when relevant.)")
                return f"Skill '{s.name}' created at {s.path} — edit the file to add real guidance."
            if action == "remove":
                name = (sub[1] or "").strip()
                if not name:
                    return "Usage: /skill remove <name>"
                return (f"Removed skill '{name}'." if engine.remove(name)
                        else f"Cannot remove '{name}' (not found or builtin).")
            if len(sub) < 2:
                return f"Usage: /skill {action} <name>"
            name = sub[1].strip()
            if action == "info":
                s = engine.get(name)
                if not s:
                    return f"No skill named {name}."
                return (f"{s.name} v{s.version} [{s.level}]\n{s.description}\n\n"
                        f"tags: {', '.join(s.tags)}\npath: {s.path}\n\n{s.content[:600]}")
            if action == "enable":
                return "Enabled " + name if engine.set_disabled(name, False) else f"No skill named {name}."
            if action == "disable":
                return f"Disabled {name} (persists in ~/.shscode/skills_state.json)" if engine.set_disabled(name, True) else f"No skill named {name}."
            return f"Unknown action: {action}"
        except Exception as e:
            return f"Skill error: {e}"

    # ------------------------------------------------------------------ tools
    if command == "/tools":
        if agent and hasattr(agent, "tools"):
            names = list(agent.tools._tools.keys())
            return f"Tools ({len(names)}): " + ", ".join(names)
        return "No agent active."

    # ------------------------------------------------------------------ mcp
    if command == "/mcp":
        from app.config import Config
        servers = Config.get().mcp_servers
        sub = arg.split(None, 1)
        if not sub or sub[0] == "list":
            if not servers:
                return ("No MCP servers configured.\nAdd: /mcp add <name> stdio <command> [args...]\n"
                        "     /mcp add <name> sse <url>")
            lines = [f"{len(servers)} MCP server(s):"]
            for s in servers:
                where = s.url or (s.command or "") + (" " + " ".join(s.args) if s.args else "")
                lines.append(f"  {s.name} [{s.transport}] {where}")
            lines.append("\n/mcp inspect <name> · /mcp remove <name>")
            return "\n".join(lines)
        action, sarg = sub[0].lower(), (sub[1] if len(sub) > 1 else "")
        if action == "add":
            toks = sarg.split()
            if len(toks) < 3:
                return "Usage: /mcp add <name> stdio <command> [args…]  |  /mcp add <name> sse <url>"
            name, transport = toks[0], toks[1].lower()
            if transport == "sse":
                # SHS Code FIX: appending None when the list is empty broke
                # /mcp permanently (persist crashed on None.name; every later
                # /mcp crashed on None.url). Use MCPServerDef directly.
                from app.config import MCPServerDef
                servers.append(MCPServerDef(name=name, transport="sse", url=toks[2]))
            else:
                from app.config import MCPServerDef
                servers.append(MCPServerDef(name=name, transport="stdio",
                                            command=toks[2], args=toks[3:]))
            await _save_mcp_servers(servers)
            return f"MCP server '{name}' added and persisted."
        if action == "remove":
            before = len(servers)
            servers[:] = [s for s in servers if s.name != sarg.strip()]
            await _save_mcp_servers(servers)
            return f"Removed '{sarg.strip()}'." if len(servers) < before else f"No server named {sarg}."
        if action == "inspect":
            target = [s for s in servers if s.name == sarg.strip()]
            if not target:
                return f"No MCP server named {sarg}."
            s = target[0]
            try:
                from app.mcp.client import MCPClient
                client = MCPClient(name=s.name, transport=s.transport,
                                   command=s.command, args=s.args or [], url=s.url)
                tools = await client.connect()
                tool_names = list(tools._tools.keys()) if tools else []
                if not tool_names:
                    return f"Connected to {s.name} but it exposes no tools."
                lines = [f"{s.name}: {len(tool_names)} tool(s)"]
                for tn in tool_names[:20]:
                    tl = tools.get(tn)
                    desc = (tl.description or "")[:70] if tl else ""
                    lines.append(f"  {tn}: {desc}")
                await client.disconnect()
                return "\n".join(lines)
            except Exception as e:
                return f"MCP inspect failed for {s.name}: {e}"
        return f"Unknown /mcp action: {action}. Use list|add|remove|inspect."

    # ------------------------------------------------------------------ connectors
    if command == "/connectors":
        from app.connectors import get_connectors, KNOWN_PLATFORMS
        reg = get_connectors()
        sub = arg.split(None, 1)
        if not sub or sub[0] == "list":
            cons = reg.list(masked=True)
            if not cons:
                return ("No connectors configured.\n"
                        "Add: /connectors add github <username> <token>\n"
                        "     /connectors add gitlab <username> <token>\n"
                        f"Known platforms: {', '.join(KNOWN_PLATFORMS[:12])}…")
            lines = [f"{len(cons)} connector(s):"]
            for c in cons:
                lines.append(f"  {c['platform']}: user={c.get('username') or '-'} "
                             f"token={c.get('token')} "
                             f"{'[enabled]' if c.get('enabled') else '[disabled]'}")
            return "\n".join(lines)
        action, sarg = (sub[0].lower(), sub[1] if len(sub) > 1 else "")
        toks = sarg.split()
        if action == "add":
            if len(toks) < 2:
                return "Usage: /connectors add <platform> <username> <token> [email]"
            platform = toks[0].lower()
            username = toks[1] if len(toks) > 1 else ""
            token = toks[2] if len(toks) > 2 else ""
            email = toks[3] if len(toks) > 3 else ""
            reg.add(platform=platform, username=username, token=token, email=email)
            return (f"Connector '{platform}' saved (token masked in all displays).\n"
                    f"Git provider tools will now authenticate with it automatically.")
        if action == "remove":
            return f"Removed {toks[0]}." if reg.remove(toks[0]) else f"No connector named {toks[0]}."
        if action == "enable":
            return f"Enabled {toks[0]}." if reg.set_enabled(toks[0], True) else f"No connector named {toks[0]}."
        if action == "disable":
            return f"Disabled {toks[0]}." if reg.set_enabled(toks[0], False) else f"No connector named {toks[0]}."
        return "Usage: /connectors add|remove|enable|disable <platform> …"

    # ------------------------------------------------------------------ channels
    if command == "/channels":
        try:
            from app.messaging.gateway import MessagingGateway
            gw = MessagingGateway()
            lines = ["Messaging channels (all route into the same persistent agent):"]
            for ad in gw._adapters:
                name = type(ad).__name__.replace("Adapter", "").lower()
                try:
                    cfg = "configured" if ad.is_configured() else "not configured"
                except Exception:
                    cfg = "unknown"
                lines.append(f"  {name:<12} {cfg}")
            return "\n".join(lines)
        except Exception as e:
            return f"Channels error: {e}"

    # ------------------------------------------------------------------ config
    if command in ("/config", "/settings"):
        from app.config import Config
        c = Config.get()
        llm = c.llm
        return (
            "Effective configuration (secrets masked):\n"
            f"  provider:    {llm.provider}\n"
            f"  model:       {llm.model}\n"
            f"  base_url:    {llm.base_url or '-'}\n"
            f"  api_key:     {_mask(llm.api_key)}\n"
            f"  max_tokens:  {llm.max_tokens}  temperature: {llm.temperature}\n"
            f"  timeout:     {llm.timeout if llm.timeout else 'adaptive (default)'}  retries: {llm.max_retries}\n"
            f"  rate_limit:  enabled={llm.rate_limit.enabled} rpm={llm.rate_limit.rpm or 'auto (NIM=40)'}\n"
            f"  max_steps:   {c.max_steps}  token_budget: {c.token_budget or 'unlimited'}\n"
            f"  workspace:   {c.workspace_dir}\n"
            f"  streaming:   {llm.streaming.enabled}\n"
            f"  mcp servers: {len(c.mcp_servers)}\n"
            f"  config path: {env.home_dir()}"
        )

    if command == "/context":
        if agent is None:
            return "No agent active."
        msgs = agent.memory.messages
        from collections import Counter
        roles = Counter(m.role.value if hasattr(m.role, "value") else str(m.role) for m in msgs)
        est = agent.memory.token_estimate()
        return (f"Context window usage:\n"
                f"  messages: {len(msgs)}  ({', '.join(f'{k}={v}' for k, v in roles.items())})\n"
                f"  token estimate: ~{est}\n"
                f"  max_messages: {getattr(agent.memory, 'max_messages', '?')}\n"
                f"  /compress to compact this session in the DB.")

    if command == "/checkpoint":
        j = _journal()
        if j is None or agent is None:
            return "Journal/agent unavailable."
        tid = getattr(agent, "_journal_task_id", None)
        if not tid:
            tid = await j.task_start(goal="(manual checkpoint)", cwd=os.getcwd())
            agent._journal_task_id = tid
        await j.checkpoint(tid, agent._step_count,
                           [m.to_dict() for m in agent.memory.messages])
        return f"Checkpoint saved ({len(agent.memory.messages)} messages, step {agent._step_count})."

    if command == "/history":
        j = _journal()
        if j is None:
            return "Journal unavailable."
        rows = await j.list_tasks(limit=5)
        if not rows:
            return "No journal history yet."
        lines = ["Recent journal events:"]
        for t in rows[:3]:
            evs = await j.events(t["task_id"], limit=6)
            lines.append(f"— {t['goal'][:50]} ({t['status']})")
            lines += [f"   {_rel_ts(e['ts'])} {e['kind']} {e.get('tool') or ''}" for e in evs]
        return "\n".join(lines)

    if command == "/files":
        j = _journal()
        if j is None:
            return "Journal unavailable."
        st = await j.current_status()
        t = st.get("active_task")
        if not t:
            rows = await j.list_tasks(limit=1)
            t = rows[0] if rows else None
        if not t:
            return "No tasks yet."
        t = await j.get_task(t["task_id"])
        files = (t or {}).get("files_changed") or []
        if not files:
            return f"No file changes recorded for task {t['task_id']}."
        lines = [f"Files changed by task {t['task_id']}:"]
        lines += [f"  {f.get('op', '?'): <9} {_rel_ts(f.get('ts'))} {f.get('path', '')}" for f in files[:30]]
        return "\n".join(lines)

    if command == "/search":
        if not arg:
            return "Usage: /search <query>"
        lines = []
        try:
            from app.db.session import SessionDB
            db = SessionDB()
            hits = await db.fts_search(arg.strip(), limit=8)
            db.close()
            if hits:
                lines.append("Sessions:")
                for h in hits:
                    lines.append(f"  [{h.get('session_id', '')[:10]}] {(h.get('snippet') or h.get('content', ''))[:80]}")
        except Exception:
            pass
        j = _journal()
        if j is not None:
            rows = await j.list_tasks(limit=50)
            q = arg.lower()
            matches = [t for t in rows if q in (t.get("goal") or "").lower()]
            if matches:
                lines.append("Journal tasks:")
                for t in matches[:8]:
                    lines.append(f"  [{t['task_id']}] {t['status']}: {t['goal'][:70]}")
        if not lines:
            return f"No results for '{arg}'."
        return "\n".join(lines)

    if command == "/git":
        # SHS Code Phase 2 (spec §31): full git intelligence
        try:
            from app.git_intel import GitIntelligence
            return GitIntelligence().render()
        except Exception as e:
            return f"git error: {e}"

    if command == "/doctor":
        try:
            from app.doctor import run_doctor, format_doctor
            base = format_doctor(run_doctor())
        except Exception as e:
            base = f"Doctor crashed: {e}"
        # SHS Code Phase 2 (spec §43 /doctor 2.0): extended checks
        extra: list[str] = []
        try:
            from app.intelligence import current_intelligence
            intel = current_intelligence()
            intel.ensure_indexed()
            fs = intel.cache.file_stats()
            extra.append(f"✓ project intelligence: {fs.get('files', 0)} files, "
                         f"{intel.cache.symbol_count()} symbols indexed (incremental cache on)")
        except Exception as e:
            extra.append(f"✗ project intelligence: {e}")
        try:
            from app.provider_health import get_health
            hs = list(get_health().stats().values())
            if hs:
                bad = [h for h in hs if h["status"] == "🔴"]
                extra.append("✓ provider health: " + ", ".join(
                    f"{h['provider']}/{h['model'][:20]} {h['status']}" for h in hs[:4]))
            else:
                extra.append("ℹ provider health: no calls recorded this session")
        except Exception as e:
            extra.append(f"✗ provider health: {e}")
        try:
            from app.modes import get_active_mode
            from app.agent_profiles import get_active_profile_name
            extra.append(f"✓ mode={get_active_mode()}  profile={get_active_profile_name() or '(default)'}")
        except Exception:
            pass
        try:
            from app.intelligence.environment import detect_environment
            env_info = detect_environment()
            extra.append(f"✓ environment: {env_info['tool_count']} dev tools detected "
                         f"(git={('git' in env_info['tools'])})")
        except Exception:
            pass
        try:
            from app.git_intel import GitIntelligence
            gi = GitIntelligence()
            if gi.is_repo():
                extra.append("✓ git: repository detected — rollback snapshots + diff intel active")
            else:
                extra.append("ℹ git: not a repository (rollback/intel git features idle)")
        except Exception:
            pass
        return base + "\n\nPhase 2 subsystems:\n" + "\n".join(extra)

    if command == "/log":
        n = 20
        if arg.strip().isdigit():
            n = int(arg.strip())
        try:
            # SHS Code FIX: recent_lines is a module-level function, not a
            # method on the logger object — the old call always raised
            # AttributeError and /log never worked.
            from app.logger import recent_lines
            lines = recent_lines(n)
            if not lines:
                return "(log capture empty — check workspace/logs/)"
            return "\n".join(lines[-n:])
        except Exception as e:
            return f"log error: {e}"

    if command == "/debug":
        on = arg.strip().lower() not in ("off", "0", "false")
        try:
            import logging
            from app.logger import logger
            root = logging.getLogger()
            root.setLevel(logging.DEBUG if on else logging.INFO)
            return f"Debug logging {'ON' if on else 'OFF'}."
        except Exception:
            return f"Debug logging set to {'ON' if on else 'OFF'} (best effort)."

    # ------------------------------------------------------------------ Phase 2
    # /plan (spec §41): persisted dependency-aware plan + status
    if command == "/plan":
        j = _journal()
        if j is None:
            return "Journal unavailable."
        tid = arg.strip() or (agent._journal_task_id if agent else None)
        if not tid:
            t = (await j.current_status()).get("active_task")
            tid = t["task_id"] if t else None
        if not tid:
            rows = await j.list_tasks(limit=1)
            tid = rows[0]["task_id"] if rows else None
        if not tid:
            return "No task/plan found yet — start a task first."
        from app.task_dag import TaskGraph
        g = await TaskGraph(j, tid).load()
        if not g.nodes():
            return f"No plan nodes for task {tid}. (Plans are generated at task start — spec §7.)"
        t = await j.get_task(tid) or {}
        header = (f"Task {tid} — {t.get('goal', '')[:70]}\n"
                  f"Status: {t.get('status')} | phase: {t.get('phase') or '-'}\n")
        return header + g.render()

    # /verify (spec §15): run project-aware verification NOW
    if command == "/verify":
        level = arg.strip().lower() or "standard"
        if level not in ("fast", "standard", "thorough"):
            return "Usage: /verify [fast|standard|thorough]"
        try:
            import asyncio as _aio
            from app.verification import VerificationEngine, format_verification
            ve = VerificationEngine()
            report = await ve.verify(level=level)
            out = format_verification(report)
            # journal the outcome against the active task
            j = _journal()
            tid = (agent._journal_task_id if agent else None)
            if j and tid:
                await j.record_verification(tid, {
                    "kind": "manual /verify", "ok": report.get("ok"),
                    "summary": report.get("summary", "")[:300],
                    "level": level})
                for r in report.get("results", []):
                    await j.record_test_result(tid, r.get("label", "verify"),
                                                bool(r.get("ok")),
                                                (r.get("output") or "")[:200])
            return out
        except Exception as e:
            return f"verify failed: {e}"

    # /project (spec §2/§28): project intelligence
    if command == "/project":
        action = arg.strip().lower() or "summary"
        try:
            from app.intelligence import current_intelligence
            intel = current_intelligence()
            if action in ("summary", "profile"):
                intel.ensure_indexed()
                p = intel.profile()
                out = intel.summary()
                deps = p.get("dependency_files") or []
                if deps:
                    out += f"\nDependency files: {', '.join(deps[:8])}"
                return out
            if action == "architecture":
                return intel.architecture_map()
            if action == "entry":
                p = intel.profile()
                return ("ENTRY POINTS: " + ", ".join(p.get("entry_points") or []))
            if action == "git":
                from app.git_intel import GitIntelligence
                return GitIntelligence().render()
            if action == "refresh":
                from app.activity import emit
                emit("indexing", project=intel.root.name)
                stats = intel.ensure_indexed(force=True)
                return (f"Index refreshed: {stats.get('files', 0)} files, "
                        f"{stats.get('symbols', 0)} symbols, changed "
                        f"{stats.get('changed', 0)}, {stats.get('ms', 0)}ms")
            return "Usage: /project [summary|architecture|entry|git|refresh]"
        except Exception as e:
            return f"project intelligence error: {e}"

    # /env (spec §29): development environment
    if command == "/env":
        try:
            from app.intelligence.environment import environment_summary, command_available
            return environment_summary()
        except Exception as e:
            return f"environment detection error: {e}"

    # /usage (spec §42): provider usage + cost intelligence
    if command == "/usage":
        try:
            from app.provider_health import get_health
            out = get_health().render()
            try:
                budget = agent._effective_budget if agent else None
                if budget:
                    u = budget.usage()
                    out += (f"\nSession token usage: input={u.input_tokens} "
                            f"output={u.output_tokens} total={u.total()} "
                            f"est ${u.cost_estimate_usd()}")
            except Exception:
                pass
            return out
        except Exception as e:
            return f"usage error: {e}"

    # /mode (spec §36): agent modes
    if command == "/mode":
        try:
            from app.modes import render_modes, set_active_mode, get_mode_config, get_active_mode
            if not arg.strip():
                return render_modes()
            name = arg.strip().lower()
            if not set_active_mode(name):
                return f"Unknown mode '{name}'. " + render_modes()
            cfg = get_mode_config(name)
            return (f"Mode set to {name} (persisted — applies to future runs).\n"
                    f"{cfg['description']}\n"
                    f"plan={cfg['plan']} verify={cfg['verification_level']} "
                    f"step-budget x{cfg['max_steps_scale']}")
        except Exception as e:
            return f"mode error: {e}"

    # /profile (spec §37): custom agent profiles
    if command == "/profile":
        try:
            from app.agent_profiles import (render_profiles, set_active_profile,
                                            create_profile, remove_profile,
                                            get_profile)
            sub = arg.split()
            if not sub or sub[0] == "list":
                return render_profiles()
            action = sub[0].lower()
            if action == "use" and len(sub) > 1:
                if sub[1].lower() == "off":
                    set_active_profile("")
                    return "Profile deactivated — default agent behavior."
                p = get_profile(sub[1])
                if not p:
                    return f"No profile named {sub[1]}. /profile list"
                set_active_profile(sub[1])
                return (f"Profile '{sub[1]}' active (persisted — applies to future runs).\n"
                        f"{p.get('description', '')}\n"
                        f"skills: {', '.join(p.get('skills') or [])} | "
                        f"verification: {p.get('verification_strategy')}")
            if action == "off":
                set_active_profile("")
                return "Profile deactivated — default agent behavior."
            if action == "create" and len(sub) >= 2:
                name = sub[1]
                desc = arg.split(None, 2)[2] if len(sub) > 2 else ""
                try:
                    create_profile(name, description=desc)
                    return (f"Profile '{name}' created. Configure it:\n"
                            f"  edit ~/.shscode/profiles.json or ask me to "
                            f"update its instructions/skills/verification.")
                except ValueError as e:
                    return f"Error: {e}"
            if action == "remove" and len(sub) > 1:
                return f"Removed profile {sub[1]}." if remove_profile(sub[1]) \
                    else f"Cannot remove {sub[1]} (missing or builtin)."
            if action == "show" and len(sub) > 1:
                p = get_profile(sub[1])
                if not p:
                    return f"No profile named {sub[1]}."
                import json as _json
                return _json.dumps(p, ensure_ascii=False, indent=1)[:2000]
            return ("Usage: /profile list|use <name>|off|show <name>|create <name> [desc]|remove <name>")
        except Exception as e:
            return f"profile error: {e}"

    # /rollback (spec §33): smart rollback of agent-changed files
    if command == "/rollback":
        try:
            from app.git_intel import SmartRollback
            j = _journal()
            toks = arg.split()
            tid = toks[0] if toks else (agent._journal_task_id if agent else None)
            if not tid:
                t = (await j.current_status()).get("active_task") if j else None
                tid = t["task_id"] if t else None
            if not tid:
                return "No task id given and none active. Usage: /rollback [task_id] [snapshot_id]"
            rb = SmartRollback(tid)
            snaps = rb.list_snapshots()
            if not snaps:
                return f"No rollback snapshots for task {tid}."
            snap_id = toks[1] if len(toks) > 1 else None
            if snap_id:
                res = rb.restore(snap_id)
                if res.get("ok"):
                    return (f"Restored {len(res['restored'])} file(s) from {res['snapshot']} "
                            f"(reason: {res.get('reason', '-')}).\n"
                            f"Re-run verification after rollback: /verify fast")
                return f"Restore failed: {res}"
            lines = [f"Rollback snapshots for task {tid}:"]
            for s in snaps[-8:]:
                lines.append(f"  {s['id']} — {len(s.get('files', []))} file(s), "
                             f"{_rel_ts(s.get('at'))} — {s.get('reason', '')[:50]}")
            lines.append("\n/rollback <task_id> <snapshot_id> to restore. "
                         "Only agent-snapshotted files are touched.")
            return "\n".join(lines)
        except Exception as e:
            return f"rollback error: {e}"

    # /undo — one-step undo of the LAST agent edit batch (SmartRollback of
    # the most recent snapshot of the current/last task). Stabilization fix:
    # the command was advertised but never implemented.
    if command == "/undo":
        try:
            from app.git_intel import SmartRollback
            j = _journal()
            tid = arg.strip() or (agent._journal_task_id if agent else None)
            if not tid and j:
                t = (await j.current_status()).get("active_task")
                tid = t["task_id"] if t else None
            if not tid:
                return "Nothing to undo: no active task and no task id given. Usage: /undo [task_id]"
            rb = SmartRollback(tid)
            snaps = rb.list_snapshots()
            if not snaps:
                return f"No snapshots recorded for task {tid} — nothing to undo."
            latest = snaps[-1]
            res = rb.restore(latest["id"])
            if res.get("ok"):
                return (f"Undid last edit batch: restored {len(res['restored'])} file(s) "
                        f"from snapshot {res['snapshot']}.\n"
                        f"Redo manually if needed; verification: /verify fast")
            return f"Undo failed: {res}"
        except Exception as e:
            return f"undo error: {e}"

    # /retry — re-queue a failed/cancelled/interrupted task (task queue or
    # journal). Stabilization fix: the command was advertised (the crash-loop
    # parking message even tells users to run it) but never implemented.
    if command == "/retry":
        try:
            tq_arg = arg.strip()
            tq = runtime.get("task_queue") if runtime else None
            if tq_arg and tq:
                ok = await tq.retry_task(tq_arg)
                if ok:
                    return (f"Task {tq_arg} re-queued — background workers will pick it up.\n"
                            "Watch progress: /tasks")
                return (f"Could not re-queue {tq_arg} (not found, or not in "
                        "failed/cancelled state).")
            # Journal path: re-open the most recent failed/interrupted task
            j = _journal()
            if j is None:
                return "Journal unavailable. Usage: /retry [task_id] (background queue) or /retry (journal task)"
            tid = tq_arg
            if not tid:
                rows = (await j.list_tasks("failed") or []) + \
                       (await j.list_tasks("interrupted") or [])
                if not rows:
                    return "No failed or interrupted tasks to retry."
                rows.sort(key=lambda t: t.get("updated_at") or 0, reverse=True)
                tid = rows[0]["task_id"]
            await j.task_update(tid, status="interrupted",
                                blocked_reason=None)
            return (f"Task {tid} re-opened as interrupted — it will resume from its "
                    "checkpoint. Use /resume {tid} to continue it in this session, "
                    "or /continue to re-run the last prompt.")
        except Exception as e:
            return f"retry error: {e}"

    # /browser — browser tool status + quick actions. Stabilization fix:
    # the command was advertised but never implemented.
    if command == "/browser":
        action = arg.strip().lower()
        try:
            from app.config import Config
            bc = Config.get().browser
            headless = "headless" if bc.headless else "visible"
            base = (f"Browser tool: crawl enabled (playwright/crawl4ai optional extras), "
                    f"mode={headless}, max_content={bc.max_content_length} chars")
            if not action:
                try:
                    import playwright  # noqa: F401
                    deps = "playwright: installed"
                except ImportError:
                    deps = "playwright: NOT installed (pip install shscode[browser])"
                try:
                    import crawl4ai  # noqa: F401
                    deps += " | crawl4ai: installed"
                except ImportError:
                    deps += " | crawl4ai: NOT installed (aiohttp fallback active)"
                return base + f"\n{deps}\nUsage: /browser open <url> (crawls the page and returns readable content)"
            if action in ("open", "search") and len(arg.split()) > 1:
                target = arg.split(None, 1)[1].strip()
                from app.tool.crawl4ai import Crawl4AITool
                tool = Crawl4AITool()
                res = await tool.execute(url=target)
                if res.error:
                    return f"Browser error: {res.error}"
                return (res.output or "")[:3000]
            return "Usage: /browser open <url>"
        except Exception as e:
            return f"browser error: {e}"

    # ------------------------------------------------------------------ legacy
    if command == "/compress":
        # SHS Code Phase 2 (spec §23): structured compaction — extract
        # operational state, never a lossy plain summary.
        if agent is None:
            return "No agent active."
        try:
            from app.compaction import compact_messages, render_report
            plan_text = ""
            try:
                if getattr(agent, "_plan_graph", None) and agent._plan_graph.nodes():
                    plan_text = agent._plan_graph.to_prompt()
            except Exception:
                pass
            msgs = [m.to_dict() for m in agent.memory.messages]
            new_msgs, report = compact_messages(msgs, keep_last=6, plan_text=plan_text)
            if not report.get("compacted"):
                return render_report(report)
            from app.schema import Message
            agent.memory.messages = [Message.from_dict(m) for m in new_msgs]
            # keep DB compression too
            if session_id:
                try:
                    from app.db.session import SessionDB
                    db = SessionDB()
                    summary = agent._task_history.context_summary() if agent._task_history else "structured compaction"
                    await db.compress_session(session_id, summary)
                    db.close()
                except Exception:
                    pass
            # checkpoint the compacted state immediately
            j = _journal()
            tid = getattr(agent, "_journal_task_id", None)
            if j and tid:
                await j.checkpoint(tid, agent._step_count,
                                   [m.to_dict() for m in agent.memory.messages])
            return render_report(report)
        except Exception as e:
            return f"compress failed: {e}"

    if command == "/new":
        return "NEW_SESSION"

    if command == "/branch":
        if session_id:
            from app.db.session import SessionDB
            db = SessionDB()
            try:
                new_sid = await db.branch_session(session_id, arg or None)
                return f"Branched session: {new_sid}"
            except Exception as e:
                return f"Branch failed: {e}"
            finally:
                db.close()
        return "No active session to branch."

    if command == "/sessions":
        return await _handle_sessions(arg, agent, session_id)

    if command == "/tasks_bg":
        return await _handle_slash("/tasks", agent, session_id, task_queue, runtime)

    if command == "/bg":
        if not arg:
            return "Usage: /bg <task description>"
        if task_queue:
            from app.task_queue import TaskPriority
            task = await task_queue.submit(arg, priority=TaskPriority.NORMAL)
            return f"Task submitted to background queue: {task.id}\nUse /tasks to monitor progress."
        return "Task queue not initialized."

    return f"Unknown command: {command}. Type /help for help."


async def _save_mcp_servers(servers) -> None:
    """Persist mcp_servers list to the active config file."""
    try:
        import yaml
        from app.config import Config
        target = Config.get().active_config_path()
        data = {}
        if target.exists():
            try:
                data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
        data["mcp_servers"] = [
            {k: v for k, v in {
                "name": s.name, "transport": s.transport, "command": s.command,
                "args": s.args, "url": s.url}.items() if v}
            for s in servers]
        tmp = target.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        os.replace(tmp, target)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# /sessions subcommand handler (preserved from SHS Code, spec §46)
# ──────────────────────────────────────────────────────────────────────────────

async def _handle_sessions(arg: str, agent=None, session_id: str = "") -> str:
    """Handle /sessions subcommands: list, history, send, spawn."""
    parts = arg.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else ""
    subarg = parts[1] if len(parts) > 1 else ""

    if not subcmd or subcmd == "list":
        from app.db.session import SessionDB
        db = SessionDB()
        sessions = await db.get_sessions(limit=20)
        db.close()
        if not sessions:
            return "No sessions found."
        lines = ["Sessions:", f"{'ID':<14} {'STATE':<10} {'AGENT':<10} {'GOAL'}", "-" * 70]
        for s in sessions:
            goal = (s.get("goal") or "")[:40]
            lines.append(f"  {s['id']:<14} {s.get('state', '?'):<10} {s.get('agent_name', 'shscode'):<10} {goal}")
        return "\n".join(lines)

    if subcmd == "history":
        if not subarg:
            return "Usage: /sessions history <session_id>"
        from app.db.session import SessionDB
        db = SessionDB()
        messages = await db.get_session_messages(subarg.strip())
        tool_calls = await db.get_session_tool_calls(subarg.strip())
        db.close()
        if not messages:
            return f"No messages found for session {subarg.strip()}"
        lines = [f"=== Session {subarg.strip()} ==="]
        for msg in messages[-30:]:
            role = msg.get("role", "?").upper()
            content = (msg.get("content") or "")[:200]
            if role != "SYSTEM":
                lines.append(f"  [{role}] {content}")
        if tool_calls:
            lines.append(f"\n  ({len(tool_calls)} tool call(s))")
        return "\n".join(lines)

    if subcmd == "send":
        import shlex
        tokens = list(shlex.split(subarg)) if subarg else []
        if not tokens:
            return "Usage: /sessions send <session_id> --message \"text\""
        sid = tokens[0]
        msg_text = ""
        i = 1
        while i < len(tokens):
            if tokens[i] in ("--message", "-m") and i + 1 < len(tokens):
                msg_text = tokens[i + 1]
                break
            i += 1
        if not msg_text:
            return "Usage: /sessions send <session_id> --message \"text\""
        from app.db.session import SessionDB
        db = SessionDB()
        await db.log_message(sid, "user", msg_text)
        db.close()
        return f"Message injected into session {sid}."

    if subcmd == "spawn":
        import shlex
        tokens = list(shlex.split(subarg)) if subarg else []
        prompt_text = ""
        i = 0
        while i < len(tokens):
            if tokens[i] in ("--prompt", "-p") and i + 1 < len(tokens):
                prompt_text = tokens[i + 1]
                break
            i += 1
        if not prompt_text:
            return "Usage: /sessions spawn --prompt \"task description\""
        return f"SPAWN_TASK:{prompt_text}"

    # ── Phase 2 (spec §27): switch | rename | archive | delete ──
    if subcmd == "switch":
        if not subarg:
            return "Usage: /sessions switch <session_id>"
        from app.db.session import SessionDB
        db = SessionDB()
        try:
            sessions = await db.get_sessions(limit=100)
            target = next((s for s in sessions if s["id"] == subarg.strip()), None)
            if not target:
                return f"No session {subarg.strip()}."
            # preserve current session state before switching
            if session_id:
                await db.close_session(session_id, state="paused", step_count=0)
            await db.log_message(subarg.strip(), "system",
                                  "Session switched back into (context in journal/agent memory).")
            db.close()
            return (f"Switched to session {subarg.strip()}.\n"
                    f"Goal: {(target.get('goal') or '')[:60]}\n"
                    f"Use /resume to restore that session's task context, or /branch to fork it.")
        except Exception as e:
            db.close()
            return f"Switch failed: {e}"

    if subcmd == "rename":
        toks = subarg.split(None, 1)
        if len(toks) < 2:
            return "Usage: /sessions rename <session_id> <new goal/title>"
        from app.db.session import SessionDB
        db = SessionDB()
        try:
            await db.rename_session(toks[0].strip(), toks[1].strip())
            db.close()
            return f"Session {toks[0].strip()} renamed to: {toks[1].strip()[:60]}"
        except Exception as e:
            db.close()
            return f"Rename failed: {e}"

    if subcmd == "archive":
        if not subarg:
            return "Usage: /sessions archive <session_id>"
        from app.db.session import SessionDB
        db = SessionDB()
        try:
            await db.archive_session(subarg.strip())
            db.close()
            return (f"Session {subarg.strip()} archived (hidden from the default list; "
                    f"data preserved).")
        except Exception as e:
            db.close()
            return f"Archive failed: {e}"

    if subcmd == "delete":
        if not subarg:
            return "Usage: /sessions delete <session_id>"
        from app.db.session import SessionDB
        db = SessionDB()
        try:
            await db.delete_session(subarg.strip())
            db.close()
            return f"Session {subarg.strip()} deleted (journal tasks remain in the task journal)."
        except Exception as e:
            db.close()
            return f"Delete failed: {e}"

    return (f"Unknown sessions subcommand: {subcmd}. Use: list, history, send, "
            "spawn, switch, rename, archive, delete")


# ──────────────────────────────────────────────────────────────────────────────
# prompt_toolkit input layer
# ──────────────────────────────────────────────────────────────────────────────

def _get_completer():
    try:
        import re as _re
        from prompt_toolkit.completion import WordCompleter
        # FIX (spec §30 — stable input): newer prompt_toolkit requires a
        # compiled regex for the WordCompleter pattern; passing a raw string
        # crashes the completer coroutine on every keystroke.
        return WordCompleter(SLASH_COMMANDS, pattern=_re.compile(r"^/\w*"))
    except ImportError:
        return None


def _get_session():
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from pathlib import Path
        history_file = Path(env.home_dir()) / ".cli_history"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        return PromptSession(history=FileHistory(str(history_file)))
    except ImportError:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Background task executor (preserved; checkpoint restore, spec §12)
# ──────────────────────────────────────────────────────────────────────────────

async def _execute_background_task(task_entry) -> str:
    """Execute a task from the background queue."""
    from app.agent.shscode import SHSCode
    agent = SHSCode()
    try:
        # If task has a checkpoint, restore memory state
        if task_entry.checkpoint and task_entry.checkpoint.memory_snapshot:
            from app.schema import Message
            messages = [Message.from_dict(m) for m in task_entry.checkpoint.memory_snapshot]
            agent.memory.messages = messages
            from app.logger import logger as _logger
            _logger.info(f"[BG Task {task_entry.id}] Restored from checkpoint at step {task_entry.checkpoint.step_count}")

        result = await agent.run(task_entry.prompt)
        return result or "Task completed (no output)"
    except Exception as e:
        return f"Task failed: {e}"
    finally:
        await agent.cleanup()


# ──────────────────────────────────────────────────────────────────────────────
# Main interactive loop — persistent autonomous coding shell
# ──────────────────────────────────────────────────────────────────────────────

async def _interactive_loop(skin_name: str = "default") -> None:
    from app.agent.shscode import SHSCode
    from app.config import Config
    from app.task_queue import TaskQueue
    from app.logger import logger
    from app.activity import ActivityBus

    skin = _get_skin(skin_name)
    cfg = Config.get()
    agent = SHSCode()
    session_id = ""
    pt_session = _get_session()
    completer = _get_completer()

    # runtime state shared with slash commands (pause/stop/continue)
    runtime: dict = {"current_run_task": None, "last_prompt": ""}

    # Initialize task queue for background execution
    task_queue = TaskQueue(max_workers=1)
    task_queue.set_executor(_execute_background_task)

    # ── SHS Code startup recovery (spec §9, §42) ─────────────────────────
    resumed_count = await task_queue.resume_interrupted()
    if resumed_count > 0:
        _print_message("system", f"Resumed {resumed_count} background task(s) from previous session.", skin)

    j = _journal()
    previous_task_note = ""
    if j is not None:
        try:
            interrupted = await j.mark_interrupted_running_tasks()
            if interrupted:
                t = await j.last_interrupted()
                if t:
                    previous_task_note = (
                        f"Previous task detected.\n"
                        f"  Goal: {t.get('goal', '')[:70]}\n"
                        f"  Status: interrupted | steps done: {t.get('step_count')}\n"
                        f"  Last completed: {(t.get('last_success') or '-')[:60]}\n"
                        f"  Last failed:    {(t.get('last_error') or '-')[:60]}\n"
                        f"Run /resume to continue from the checkpoint."
                    )
        except Exception:
            pass

    await task_queue.start_workers()

    # ── Banner ───────────────────────────────────────────────────────────
    try:
        info = agent.llm.backend_info()
        provider, model_name = info.get("provider", ""), info.get("model", "")
    except Exception:
        provider, model_name = cfg.llm.provider, cfg.llm.model
    _print_banner(skin, model_name, provider)
    if previous_task_note:
        _print_message("system", previous_task_note, skin)

    # ── Live activity display (spec §32) ─────────────────────────────────
    activity_printer = _make_activity_printer(skin, enabled=True)
    ActivityBus.subscribe(activity_printer)

    # ── Graceful shutdown wiring ─────────────────────────────────────────
    shutdown_event = asyncio.Event()

    def _signal_handler(sig, frame):
        # Ctrl+C during a run -> cancel the run (state is checkpointed).
        # Ctrl+C at the prompt -> the executor input raises KeyboardInterrupt.
        task = runtime.get("current_run_task")
        if task and not task.done():
            task.cancel()
        else:
            shutdown_event.set()

    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler, sig, None)
            except (NotImplementedError, OSError):
                pass  # Windows
    except RuntimeError:
        pass

    while not shutdown_event.is_set():
        try:
            if pt_session and completer:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: pt_session.prompt("SHS Code> ", completer=completer, multiline=False)
                )
            else:
                user_input = await asyncio.get_event_loop().run_in_executor(None, input, "SHS Code> ")
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break
        except asyncio.CancelledError:
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Plain 'exit' / 'quit' works like /exit (spec §1)
        if user_input.lower() in ("exit", "quit", "q!"):
            break

        # Handle slash commands
        if user_input.startswith("/"):
            try:
                result = await _handle_slash(
                    user_input, agent=agent, session_id=session_id,
                    task_queue=task_queue, runtime=runtime,
                )
            except Exception as e:
                result = f"Command error: {e}"
            if result == "EXIT":
                break
            if result == "NEW_SESSION":
                await agent.cleanup()
                ActivityBus.unsubscribe_all()
                agent = SHSCode()
                ActivityBus.subscribe(_make_activity_printer(skin, enabled=True))
                session_id = ""
                _print_message("system", "New session started. (Persistent memory and journal remain on disk.)", skin)
                continue
            if isinstance(result, str) and result.startswith("SPAWN_TASK:"):
                # FIX (audit bug #2): SPAWN_TASK sentinel was never executed.
                user_input = result[len("SPAWN_TASK:"):]
            elif isinstance(result, str) and result.startswith("SPAWN_PROMPT:"):
                user_input = result[len("SPAWN_PROMPT:"):]
            elif result:
                _print_message("system", result, skin)
                continue
            else:
                continue

        # Regular prompt — run agent as a MONITORED background task (spec §31).
        # SHS Code FIX (/pause & /stop were dead): the REPL used to block on
        # `await run_task`, so no input was ever read while a run was in
        # flight — /pause and /stop could only ever print "No run in
        # progress.". Prompts now run concurrently with the input loop and
        # slash commands keep working DURING execution.
        _print_message("user", user_input, skin)
        runtime["last_prompt"] = user_input

        active = runtime.get("current_run_task")
        if active is not None and not active.done():
            _print_message("system",
                           "A run is already active. Use /pause, /stop, or /status — "
                           "or wait for it to finish before sending a new prompt.", skin)
            continue

        runtime["current_run_task"] = asyncio.create_task(
            _run_prompt(agent, user_input, skin, runtime))

    # Wait for any active run to settle before shutdown (bounded).
    active = runtime.get("current_run_task")
    if active is not None and not active.done():
        _print_message("system", "Waiting for the active run to settle (Ctrl+C to force)...", skin)
        try:
            await asyncio.wait_for(asyncio.shield(active), timeout=30)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            active.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(active), timeout=5)
            except Exception:
                pass

    # Graceful shutdown
    ActivityBus.unsubscribe_all()
    _print_message("system", "Shutting down... state saved. Background tasks can be resumed next launch.", skin)
    await task_queue.stop_workers()
    await agent.cleanup()
    print("Goodbye. SHS Code state is saved — run 'SHSCode' again to resume.")


async def _run_prompt(agent, prompt: str, skin: dict, runtime: dict) -> None:
    """Run one user prompt and print the result (concurrent with input loop)."""
    try:
        result = await agent.run(prompt)
        _print_message("assistant", result or "(no output)", skin)
        try:
            info = agent.llm.backend_info()
            model_name = info.get("model", "")
        except Exception:
            model_name = ""
        _print_header(skin, model_name, agent._session_id or "", agent._step_count)
    except asyncio.CancelledError:
        _print_message("system",
                       "Run interrupted — state checkpointed. Use /resume or /continue.", skin)
    except Exception as e:
        _print_message("error", f"Error: {e}", skin)
    finally:
        # Reset agent state for next prompt (session context retained)
        from app.schema import AgentState
        agent.state = AgentState.IDLE
        agent._step_count = 0
        runtime["current_run_task"] = None


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="SHS Code — Persistent Autonomous Coding Agent (SHS Lab)",
        prog="SHSCode",
    )
    parser.add_argument("prompt", nargs="*", help="Task prompt (omit for interactive shell)")
    parser.add_argument("--skin", default="default", choices=list(SKINS.keys()), help="UI skin")
    parser.add_argument("--model", help="Override LLM model")
    parser.add_argument("--profile", help="Config profile name")
    parser.add_argument("--session", metavar="ID", help="Continue a specific session (conversation history is restored)")
    parser.add_argument("--continue", dest="continue_last", action="store_true",
                        help="Continue the most recent session in this workspace")
    parser.add_argument("--no-color", action="store_true", help="Disable colors (forces plain text)")
    parser.add_argument("--version", action="version", version=f"SHS Code v{VERSION}")
    args = parser.parse_args()

    if args.profile:
        os.environ["SHSCODE_PROFILE"] = args.profile

    if args.model:
        os.environ["LLM_MODEL_OVERRIDE"] = args.model

    if args.no_color:
        os.environ["NO_COLOR"] = "1"
        os.environ["TERM"] = "dumb"

    if args.prompt:
        # Single-shot mode: SHSCode "do something"
        prompt_text = " ".join(args.prompt)

        async def _run_once():
            from app.agent.shscode import SHSCode
            from app.task_queue import TaskQueue
            skin = _get_skin(args.skin)

            # v3.0 conversation continuity: resolve the session to continue.
            # --session ID wins; --continue picks the most recent session in
            # this workspace. Fresh runs get a brand-new session as before.
            session_id = None
            try:
                if args.session:
                    from app.db.session import SessionDB
                    row = await SessionDB().get_session(args.session)
                    if row is None:
                        _print_message("system",
                            f"Session {args.session} not found — starting a new session.",
                            skin)
                    else:
                        session_id = args.session
                elif args.continue_last:
                    from app.db.session import SessionDB
                    row = await SessionDB().latest_session()
                    if row is None:
                        _print_message("system",
                            "No previous session found — starting a new session.", skin)
                    else:
                        session_id = row["id"]
                        _print_message("system",
                            f"Continuing session {session_id} "
                            f"(goal: {row.get('goal', '')[:60]})", skin)
            except Exception as e:
                _print_message("system", f"Session lookup failed: {e}", skin)

            agent = SHSCode(session_id=session_id)

            task_queue = TaskQueue(max_workers=1)
            resumed = await task_queue.resume_interrupted()
            if resumed:
                _print_message("system", f"Resumed {resumed} background task(s).", skin)

            try:
                with Spinner(verb="thinking", skin=skin):
                    result = await agent.run(prompt_text)
                _print_message("assistant", result or "(no output)", skin)
                # v3.0: surface the session id so the next one-shot can
                # continue this conversation (SHSCode --session <id> ...).
                sid = getattr(agent, "_session_id", None)
                if sid:
                    _print_message("system", f"session: {sid}", skin)
            finally:
                # SHS Code FIX (one-shot leak regression): complete async
                # resource lifecycle — agent (LLM aiohttp session, tools,
                # subprocesses, DB) AND the task-queue connections. One-shot
                # execution must exit without unclosed-session / closed-loop
                # warnings or dangling background tasks.
                await agent.cleanup()
                await task_queue.stop_workers()

        asyncio.run(_run_once())
    else:
        # Interactive shell mode: SHSCode (persistent autonomous environment)
        try:
            asyncio.run(_interactive_loop(skin_name=args.skin))
        except KeyboardInterrupt:
            print("\nGoodbye. Run 'SHSCode' again — your state is saved.")


if __name__ == "__main__":
    main()
