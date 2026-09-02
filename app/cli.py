from __future__ import annotations

"""
SHS Code CLI — Persistent Autonomous Coding Shell
=================================================
Type: SHSCode   (legacy alias: manusclaw)

SHS Code is part of the SHS Lab ecosystem (Sazzad Hussain Shobuj).
Lineage: evolved from ManusClaw — its predecessor and original foundation.

The interactive shell is a persistent agent environment:
  - Memory, task journal and checkpoints survive restarts (spec §3/§6/§7)
  - /model and /provider switch the reasoning backend LIVE — context,
    memory, files and task progress are never destroyed (spec §4/§17)
  - NVIDIA NIM (and any provider) paced by a true rolling-window limiter
    (spec §18) — rate-limit waits preserve all state (spec §19)
  - Interrupted tasks are detected and resumable on next launch (spec §9)

Slash commands (spec §10) — all backed by real functionality:
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

# ──────────────────────────────────────────────────────────────────────────────
# Version / branding
# ──────────────────────────────────────────────────────────────────────────────

VERSION = "1.0.0"           # SHS Code
PREDECESSOR = "ManusClaw v5.1.1"

SHS_BANNER = r"""
███████╗██╗  ██╗███████╗  ██████╗ ██████╗ ██████╗ ██████╗
██╔════╝██║  ██║██╔════╝ ██╔════╝██╔═══██╗██╔══██╗██╔══██╗
███████╗███████║███████╗ ██║     ██║   ██║██████╔╝██████╔╝
╚════██║██╔══██║╚════██║ ██║     ██║   ██║██╔══██╗██╔═══╝
███████║██║  ██║███████╗ ╚██████╗╚██████╔╝██║  ██║██║
╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝
"""

# ──────────────────────────────────────────────────────────────────────────────
# Skins (preserved from ManusClaw)
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
]


def _get_skin(name: str = "default") -> dict:
    """Load skin: check ~/.manusclaw/skins/<name>.yaml first, then built-ins."""
    from pathlib import Path
    import os
    skin_file = Path(os.getenv("MANUSCLAW_HOME", Path.home() / ".manusclaw")) / "skins" / f"{name}.yaml"
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
            "    /provider <n> [m]  — switch provider [model]\n"
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
            "    /sessions …        — list|history|send|spawn\n"
            "    /compress          — compress current session context\n"
            "    /branch            — branch current session\n"
            "    /exit              — quit (or just type: exit)"
        )

    if command in ("/exit", "/quit"):
        return "EXIT"

    if command == "/version":
        return (f"SHS Code v{VERSION} (SHS Lab — Sazzad Hussain Shobuj)\n"
                f"Predecessor: {PREDECESSOR}\n"
                f"Python {sys.version.split()[0]}")

    if command == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        return None

    # ------------------------------------------------------------------ status
    if command == "/status":
        lines = ["SHS Code Status", "=" * 58]
        try:
            import subprocess
            r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                               capture_output=True, text=True, timeout=8)
            branch = r.stdout.strip() if r.returncode == 0 else "(not a git repo)"
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
                lines.append(f"Last ok:   {(t.get('last_success') or '-')[:70]}")
                lines.append(f"Last err:  {(t.get('last_error') or '-')[:70]}")
                lines.append(f"Checkpoint: {_rel_ts(st.get('last_checkpoint_ts'))}")
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
            rows = await j.list_tasks("interrupted") + await j.list_tasks("paused")
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
            return "No interrupted/paused task to resume. /tasks to list."
        t = await j.get_task(tid)
        cp = await j.load_checkpoint(tid)
        if not t:
            return f"Task {tid} not found."
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
            f"Progress: {pct}% ({comp}/{total} items)\n"
            f"Last successful action: {t.get('last_success') or '-'}\n"
            f"Last failed action: {t.get('last_error') or '-'}\n"
            f"Next action: inspect the filesystem before repeating any operation;\n"
            f"completed work must not be redone."
        )
        agent.memory.add(Message.system(summary))
        await j.task_update(tid, status="in_progress")
        agent._journal_task_id = tid
        from app.schema import AgentState
        agent.state = AgentState.IDLE
        agent._step_count = 0
        return (f"Resumed task {tid}.\nGoal: {t.get('goal', '')[:60]}\n"
                f"Progress: {pct}% | restored {restored} context messages.\n"
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
                rpm = int(sub[5]) if len(sub) > 5 and sub[5].isdigit() else 0
                e = reg.add(name=sub[1], api_type=sub[2], base_url=sub[3],
                            model=sub[4], api_key=sub[5] if len(sub) > 5 and not sub[5].isdigit() else "",
                            rpm=rpm)
                return (f"Provider '{e['name']}' registered (persisted to ~/.manusclaw/providers.json).\n"
                        f"Switch to it: /provider {e['name']}")
            except ValueError as ex:
                return f"Error: {ex}"
        if sub[0] == "remove" and len(sub) > 1:
            return f"Removed {sub[1]}." if reg.remove(sub[1]) else f"No provider named {sub[1]}."
        if sub[0] == "set-key" and len(sub) > 2:
            e = reg.get(sub[1])
            if not e:
                return f"No provider named {sub[1]}."
            reg.add(**{**e, "api_key": sub[2]})
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
            skills = get_skill_engine().list_skills()
            if not skills:
                return "No skills loaded."
            lines = [f"{len(skills)} skill(s) loaded (builtin + ~/.manusclaw/skills):"]
            for s in skills:
                state = "OFF" if get_skill_engine().is_disabled(s.name) else "on"
                lines.append(f"  {s.name} v{s.version} [{state}]: {s.description[:60]}")
            lines.append("\n/skill info <name> · /skill enable|disable <name> · /skill reload")
            return "\n".join(lines)
        except Exception as e:
            return f"Skills error: {e}"

    if command == "/skill":
        sub = arg.split(None, 1)
        if not sub:
            return "Usage: /skill info|enable|disable|reload <name>"
        try:
            from app.skills.skill_engine import get_skill_engine
            engine = get_skill_engine()
            action = sub[0].lower()
            if action == "reload":
                engine.reload()
                return f"Skills reloaded: {len(engine.list_skills())} skill(s)."
            if len(sub) < 2:
                return f"Usage: /skill {action} <name>"
            name = sub[1].strip()
            if action == "info":
                s = engine.get(name)
                if not s:
                    return f"No skill named {name}."
                return f"{s.name} v{s.version}\n{s.description}\n\ntags: {', '.join(s.tags)}\n\n{s.content[:600]}"
            if action == "enable":
                return "Enabled " + name if engine.set_disabled(name, False) else f"No skill named {name}."
            if action == "disable":
                return f"Disabled {name} (persists in ~/.manusclaw/skills_state.json)" if engine.set_disabled(name, True) else f"No skill named {name}."
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
                servers.append(type(servers[0])(name=name, transport="sse", url=toks[2])
                               if servers else None)
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
            f"  timeout:     {llm.timeout}s  retries: {llm.max_retries}\n"
            f"  rate_limit:  enabled={llm.rate_limit.enabled} rpm={llm.rate_limit.rpm or 'auto (NIM=40)'}\n"
            f"  max_steps:   {c.max_steps}  token_budget: {c.token_budget or 'unlimited'}\n"
            f"  workspace:   {c.workspace_dir}\n"
            f"  streaming:   {llm.streaming.enabled}\n"
            f"  mcp servers: {len(c.mcp_servers)}\n"
            f"  config path: {os.getenv('MANUSCLAW_HOME', str(Path.home() / '.manusclaw'))}"
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
        import subprocess
        try:
            def _git(*a):
                return subprocess.run(["git", *a], capture_output=True, text=True, timeout=10)
            branch = _git("rev-parse", "--abbrev-ref", "HEAD")
            if branch.returncode != 0:
                return "Not inside a git repository."
            st = _git("status", "--short")
            log = _git("log", "--oneline", "-5")
            lines = [f"Branch: {branch.stdout.strip()}",
                     "Changes:" + ("" if st.stdout.strip() else " (clean)")]
            lines += [f"  {l}" for l in st.stdout.strip().splitlines()[:15]]
            lines.append("Recent commits:")
            lines += [f"  {l}" for l in log.stdout.strip().splitlines()[:5]]
            return "\n".join(lines)
        except Exception as e:
            return f"git error: {e}"

    if command == "/doctor":
        try:
            from app.doctor import run_doctor, format_doctor
            return format_doctor(run_doctor())
        except Exception as e:
            return f"Doctor crashed: {e}"

    if command == "/log":
        n = 20
        if arg.strip().isdigit():
            n = int(arg.strip())
        try:
            from app.logger import logger
            lines = logger.recent_lines(n)
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

    # ------------------------------------------------------------------ legacy
    if command == "/compress":
        if session_id and agent:
            from app.db.session import SessionDB
            db = SessionDB()
            summary = agent._task_history.context_summary() if agent._task_history else "No task history."
            await db.compress_session(session_id, summary)
            db.close()
            return f"Session {session_id[:8]} compressed in DB."
        return "No active session."

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
# /sessions subcommand handler (preserved from ManusClaw, spec §46)
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
            lines.append(f"  {s['id']:<14} {s.get('state', '?'):<10} {s.get('agent_name', 'manus'):<10} {goal}")
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

    return f"Unknown sessions subcommand: {subcmd}. Use: list, history, send, spawn"


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
        history_file = Path(os.getenv("MANUSCLAW_HOME", Path.home() / ".manusclaw")) / ".cli_history"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        return PromptSession(history=FileHistory(str(history_file)))
    except ImportError:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Background task executor (preserved; checkpoint restore, spec §12)
# ──────────────────────────────────────────────────────────────────────────────

async def _execute_background_task(task_entry) -> str:
    """Execute a task from the background queue."""
    from app.agent.manus import Manus
    agent = Manus()
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
    from app.agent.manus import Manus
    from app.config import Config
    from app.task_queue import TaskQueue
    from app.logger import logger
    from app.activity import ActivityBus

    skin = _get_skin(skin_name)
    cfg = Config.get()
    agent = Manus()
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
                agent = Manus()
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

        # Regular prompt — run agent in a cancellable task (spec §31)
        _print_message("user", user_input, skin)
        runtime["last_prompt"] = user_input

        try:
            run_task = asyncio.create_task(agent.run(user_input))
            runtime["current_run_task"] = run_task
            result = await run_task
            session_id = agent._session_id or ""
            _print_message("assistant", result or "(no output)", skin)
            try:
                info = agent.llm.backend_info()
                model_name = info.get("model", "")
            except Exception:
                model_name = ""
            _print_header(skin, model_name, session_id, agent._step_count)
        except asyncio.CancelledError:
            _print_message("system",
                           "Run interrupted — state checkpointed. Use /resume or /continue.", skin)
        except Exception as e:
            _print_message("error", f"Error: {e}", skin)

        # Reset agent state for next prompt (session context retained)
        from app.schema import AgentState
        agent.state = AgentState.IDLE
        agent._step_count = 0
        runtime["current_run_task"] = None

    # Graceful shutdown
    ActivityBus.unsubscribe_all()
    _print_message("system", "Shutting down... state saved. Background tasks can be resumed next launch.", skin)
    await task_queue.stop_workers()
    await agent.cleanup()
    print("Goodbye. SHS Code state is saved — run 'SHSCode' again to resume.")


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
    parser.add_argument("--no-color", action="store_true", help="Disable colors (forces plain text)")
    parser.add_argument("--version", action="version", version=f"SHS Code v{VERSION}")
    args = parser.parse_args()

    if args.profile:
        os.environ["MANUSCLAW_PROFILE"] = args.profile

    if args.model:
        os.environ["LLM_MODEL_OVERRIDE"] = args.model

    if args.no_color:
        os.environ["NO_COLOR"] = "1"
        os.environ["TERM"] = "dumb"

    if args.prompt:
        # Single-shot mode: SHSCode "do something"
        prompt_text = " ".join(args.prompt)

        async def _run_once():
            from app.agent.manus import Manus
            from app.task_queue import TaskQueue
            skin = _get_skin(args.skin)
            agent = Manus()

            task_queue = TaskQueue(max_workers=1)
            resumed = await task_queue.resume_interrupted()
            if resumed:
                _print_message("system", f"Resumed {resumed} background task(s).", skin)

            with Spinner(verb="thinking", skin=skin):
                result = await agent.run(prompt_text)
            _print_message("assistant", result or "(no output)", skin)
            await agent.cleanup()

        asyncio.run(_run_once())
    else:
        # Interactive shell mode: SHSCode (persistent autonomous environment)
        try:
            asyncio.run(_interactive_loop(skin_name=args.skin))
        except KeyboardInterrupt:
            print("\nGoodbye. Run 'SHSCode' again — your state is saved.")


if __name__ == "__main__":
    main()
