# SHS Code GUI — The Complete Guide (For Everyone)

> This guide explains the SHS Code web GUI in **plain language**. You do not need
> to be a programmer to follow it. If you can use a web browser, you can use this GUI.
>
> Applies to **SHS Code v4.1.0+**.

---

## Table of contents

1. [What is SHS Code?](#1-what-is-shs-code)
2. [What is the GUI?](#2-what-is-the-gui)
3. [Starting the GUI](#3-starting-the-gui)
4. [The screen layout](#4-the-screen-layout)
5. [Hiding and showing the navigation (slide menu)](#5-hiding-and-showing-the-navigation-slide-menu)
6. [Your first task — step by step](#6-your-first-task--step-by-step)
7. [The 14 panels explained, one by one](#7-the-14-panels-explained-one-by-one)
8. [Understanding what the agent shows you](#8-understanding-what-the-agent-shows-you)
9. [Task statuses and what they mean](#9-task-statuses-and-what-they-mean)
10. [Working with Git and GitHub safely](#10-working-with-git-and-github-safely)
11. [Keyboard shortcuts](#11-keyboard-shortcuts)
12. [Where your data lives](#12-where-your-data-lives)
13. [Troubleshooting](#13-troubleshooting)
14. [FAQ](#14-faq)
15. [CLI ↔ GUI cheat sheet](#15-cli--gui-cheat-sheet)

---

## 1. What is SHS Code?

SHS Code is an **AI coding agent**. You describe what you want in ordinary
language — for example:

> "Make a small website for my bakery with a menu page and a contact form."

…and the agent:

1. **Plans** the work (breaks your request into ordered steps),
2. **Writes** the code (creates and edits real files on the server),
3. **Checks** its own work (runs builds, tests and linters),
4. **Reports back** with the final answer — and shows you every step it took along the way.

The important promise of SHS Code: **it never pretends something succeeded when
it didn't.** If a step fails, you see the failure. A task is only marked
"completed" when it actually ran and passed its checks.

## 2. What is the GUI?

SHS Code can be used in two ways:

- the **CLI** (command line — you type commands in a terminal), and
- the **GUI** (graphical interface — you click things in your web browser).

Both are windows into the **same running system**: same sessions, same tasks,
same memory, same files. Start a task in the GUI and you can inspect it from the
CLI, or the other way around. The GUI does not "guess" what the agent is doing —
the runtime sends it structured events, so **what you see is what actually
happened**.

## 3. Starting the GUI

**Step 1 — start the server.** In a terminal:

```bash
shscode-server
```

The server starts (by default on port **8765**) and prints its address.

**Step 2 — open the GUI.** In any modern browser:

```
http://localhost:8765/gui
```

> **If the server was started with an API key** (setting `SHSCODE_API_KEY`),
> you must pass it in the address:
> `http://localhost:8765/gui?api_key=YOUR_KEY`
> Otherwise the panels will say "unauthorized".

**Step 3 — check the connection.** Look at the bottom-left of the sidebar:
a **green dot** means the live connection (WebSocket) is up. Red means
disconnected — the GUI keeps retrying automatically every 3 seconds.

That's it — the GUI is running.

## 4. The screen layout

The GUI has three areas:

```
┌──────────┬─────────────────────────────────────────────┐
│          │  ☰  Dashboard            model · project ↻  │  ← top bar
│  SIDE    ├─────────────────────────────────────────────┤
│  BAR     │                                             │
│          │               MAIN CONTENT                  │
│  (menu:  │         (changes per selected panel)        │
│  14      │                                             │
│  panels) │                                             │
│          │                                             │
│ ● online │                                             │
└──────────┴─────────────────────────────────────────────┘
```

- **Left — the navigation sidebar**: the menu with all 14 panels, and the
  connection status dot at the bottom.
- **Top — the top bar**: the ☰ menu button (hide/show the sidebar), the current
  panel name, the active model, and a **↻ Refresh** button for the panel.
- **Center — the content**: the selected panel's screen.

## 5. Hiding and showing the navigation (slide menu)

You asked for it — the left menu can be **slid out of the way** to give the
whole screen to your content. Three ways to toggle it:

| How | What to do |
|---|---|
| **Menu button** | Click the **☰** button at the far left of the top bar |
| **Edge tab** | When the menu is hidden, a vertical **☰ MENU** tab appears at the left edge of the screen — click it to slide the menu back in |
| **Keyboard** | <kbd>Ctrl</kbd>+<kbd>B</kbd> (Windows/Linux) or <kbd>Cmd</kbd>+<kbd>B</kbd> (Mac) |

Details worth knowing:

- The slide is **animated** — the menu glides in and out smoothly.
- Your choice is **remembered**. Hide the menu today, close the browser, open
  the GUI tomorrow — it stays hidden until you bring it back.
- **On phones and small screens**, the menu works like a modern app drawer:
  it slides over the content with a dark backdrop. Tap the backdrop or press
  <kbd>Esc</kbd> to close it. Picking a panel closes it automatically.

Why hide the menu? More room for code, diffs, logs and chat — especially on
laptops. One keypress brings it right back.

## 6. Your first task — step by step

**Step 1 — open the Agent panel.** Click **Agent** in the left menu
(or press <kbd>Ctrl</kbd>+<kbd>B</kbd> if the menu is hidden, then click Agent).

**Step 2 — make sure a model is configured.** Open **Settings** once:
provider, model and API key must be filled (keys are stored securely and are
**never displayed back**). If you set them up during installation, you're done.

**Step 3 — type your request.** In the Agent panel, type what you want in
normal language:

```
Create a Python script called rename.py that renames all files
in a folder to lowercase, with a --dry-run option.
```

Press <kbd>Enter</kbd> to send (use <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new
line while typing).

**Step 4 — watch it work.** The right side of the Agent panel ("Activity")
fills with the agent's live internal events: which files it reads, which tools
it uses, each step it takes. The agent's answer **streams in live** in the chat.

**Step 5 — read the honest result.** When the run finishes you get:

- the **final answer** in the chat bubble (only real, verified results),
- a system line like `— run finished · 12 steps · final_answer —`,
- the **Run Progress** card shows the finish reason.

**Step 6 — check the result yourself** (optional but recommended):
- **Workspace** panel → find and open the file(s) it created.
- **QA** panel → **Run verification** to run the same checks the agent used.
- **Terminal** panel → run the script yourself, e.g. `python rename.py --dry-run`.

**Step 7 — save your work.** If you like the result, use the **Git** panel to
commit (and push). Commits are properly credited to you and to
**SHS-Code-Agent** (the agent's GitHub identity).

## 7. The 14 panels explained, one by one

### ◧ Dashboard
The overview home screen. Shows at a glance: which AI model is active, the
GitHub identity, local git state (branch, dirty files, last commit), the most
recent tasks with their real statuses, and recent sessions. Start here to
confirm everything is connected.

### ✦ Agent
The main workspace — your conversation with the agent. Left: the chat (your
messages and the agent's **final answers**, streaming live). Right: the
**activity feed** — the agent's internal work log (every tool call, file
change, step), which is deliberately kept **separate from your conversation**.
The **Run Progress** card tracks status / step / finish reason / tool calls.
Buttons: **New** (fresh session), **■ Cancel run** (stop — nothing is lost).

### ⬢ Tasks
Every job the agent has run, with its **true lifecycle status**. Click any task
to see: its **plan as a visual DAG** — boxes arranged in waves, arrows showing
which steps depend on which, colors showing state — plus the task's recent
journal events. This is where you verify "did it really finish everything?"

### ⧉ Team103
For **very large goals** (e.g. "migrate this whole project to Python 3.12").
Your goal is decomposed by a PM step, ordered into dependency waves by an
Architect step, executed by many lightweight engineer workers with dynamic
concurrency, and checked by a QA gate. The panel shows the honest result:
QA pass/fail, how many tasks, peak workers, conflicts, unresolved items.

### ▤ Workspace
A file browser for the server's working folder. Click folders to expand,
click a file to view its contents (large files are truncated for safety).
You cannot escape the workspace folder — path traversal is blocked.

### ▸_ Terminal
A real command line in the browser, running in the server's working directory.
Type a command, press <kbd>Enter</kbd>, see output + exit code. Handy for
quick checks (`ls`, `python --version`, running the agent's output…).

### ⑂ Git
Local version control: current branch and changes, create branches, commit
(with the agent credited via a `Co-Authored-By` trailer), push, pull, stash,
pop stash, and view **diffs** (unstaged or staged) plus recent commits.

### ◉ GitHub
The agent's GitHub identity card (SHS-Code-Agent, auth mode, account, profile
link) plus remote operations: **create pull requests** (with title, body,
head/base branch, draft flag) and **list PRs / issues** for any repo you can
access. This uses the shared GitHubProvider — the same one the CLI uses.

### ✓ QA
Runs the **VerificationEngine** — the exact same checks the agent runs on
itself: project-aware build, tests, lint, typecheck. Green PASS rows mean the
check genuinely passed; red FAIL rows show the output so you can see why.

### ◷ Sessions
Your conversation history. Every session (CLI or GUI) is listed with its state
and step count. Click one to browse its messages — **final answers vs interim
narration are labeled and separated** — then **Continue in Agent panel** to
pick up exactly where you left off.

### ≣ Logs
The system's technical log (auto-refreshing every 3 seconds while open).
Diagnostics live here — by design **separate from your chat** — with levels
color-coded (INFO blue, WARNING yellow, ERROR red).

### ◈ Memory
What the agent remembers: **MEMORY.md** (project knowledge), **USER.md**
(your preferences), and **long-term memory** entries with timestamps.
This is how the agent gets better acquainted with your project over time.

### ⚙ Settings
The effective configuration (values, with secrets masked) and the
**model switcher**: change provider / model / base URL / API key. Changes are
persisted securely (0600 permissions) and apply to **new** agents —
in-flight runs are never disrupted.

### ? Help / Guide
A condensed version of this guide, always available inside the GUI itself —
including the quick-start, the panel list, status meanings, shortcuts and
troubleshooting.

## 8. Understanding what the agent shows you

**Chat vs activity — the two-channel design.** Your conversation contains only
two kinds of bubbles: what **you** said, and the agent's **final answers**.
Everything the agent does in between (tool calls, file edits, retries, internal
reasoning events) appears in the **activity feed**, never in the chat. This is
the "internal events vs user messages" separation — you get a clean
conversation and a full audit trail side by side.

**Streaming.** Answers appear **live, token by token**, as the model writes
them. When the run completes, the final message is shown exactly once — the
GUI checks and never duplicates what was already streamed.

**Finish reasons — the honesty signal.** Every run ends with a reason:

| Reason | Meaning |
|---|---|
| `final_answer` | The agent verified its work and answered properly |
| `max_steps` | It ran out of allowed steps — work is saved, you can continue |
| `interrupted` | You (or a restart) stopped it — state is preserved |
| `error` | Something failed — the error is shown, never hidden |

If the agent could not finish, **it says so**. "Completed" always means
"actually completed".

## 9. Task statuses and what they mean

Tasks (and each step of a plan) move through a strict lifecycle. The GUI
colors them consistently:

| Status | Color | Plain meaning |
|---|---|---|
| `pending` | gray | Waiting — some step it depends on isn't done yet |
| `ready` | cyan | Dependencies satisfied; queued to start |
| `running` | blue | Being worked on right now |
| `partial` | yellow | Stopped midway (interrupted / timeout); recoverable |
| `retryable` | yellow | Failed once — will be retried automatically |
| `failed` | red | Failed (after retries) |
| `blocked` | red | Can't proceed because a dependency failed |
| `completed` | green | Ran AND passed its checks |

Two guarantees the system enforces (and tests pin):

1. **A failed task can never become completed.** No fake success.
2. **A task only unlocks when all its dependencies are completed.** No
   skipped prerequisites.

## 10. Working with Git and GitHub safely

**Local git (Git panel):** everything you'd expect — branch, commit, push,
pull, stash, diff, log. One special behavior: commits made through SHS Code
carry the trailer

```
Co-Authored-By: SHS-Code-Agent <SHS-Code-Agent@users.noreply.github.com>
```

so history stays honest about what the agent did, while **you remain the
author**.

**Remote GitHub (GitHub panel):** create PRs and list PRs/issues through the
same GitHubProvider abstraction the CLI and the agent runtime use — one
credential path, one place to audit. The **Dashboard** and **GitHub** panels
show which identity is active (personal account vs the SHS-Code-Agent
installation identity).

**Safety rails built in:**

- Your API keys and tokens are stored with 0600 permissions and **masked** in
  every GUI view — the Settings panel shows that a key exists, never the key.
- The Workspace browser is confined to the server's working directory.
- The QA panel shows raw check output, so "pass" is verifiable, not asserted.

## 11. Keyboard shortcuts

| Keys | Action |
|---|---|
| <kbd>Ctrl</kbd>+<kbd>B</kbd> / <kbd>Cmd</kbd>+<kbd>B</kbd> | Hide or show the left navigation |
| <kbd>Enter</kbd> | Send the message (Agent panel input) |
| <kbd>Shift</kbd>+<kbd>Enter</kbd> | New line inside the message input |
| <kbd>Esc</kbd> | Close the navigation drawer (small screens) |
| <kbd>↻ Refresh</kbd> | Button in the top bar — reloads the current panel's data |

## 12. Where your data lives

| Data | Where | Visible in |
|---|---|---|
| Conversations | server-side session database | Sessions panel (and CLI) |
| Task journal (statuses, DAG, events) | server-side journal | Tasks panel |
| Project & user memory | MEMORY.md / USER.md / memory store | Memory panel |
| System diagnostics | rotating log files | Logs panel |
| API keys / tokens | encrypted/secrets store, 0600 | Settings (masked) |

Nothing is stored in the browser except your **navigation preference**
(hidden or shown) — sessions and data always live with the server, so you can
open the GUI from any browser and continue seamlessly.

## 13. Troubleshooting

**"WebSocket disconnected" (red dot, bottom-left).**
The live connection dropped. The GUI retries automatically every 3 seconds.
If it stays red: check the server terminal is still running, then reload the
page (F5).

**Panels say "unauthorized — set ?api_key=".**
The server was started with `SHSCODE_API_KEY`. Append it to the URL:
`http://localhost:8765/gui?api_key=YOUR_KEY`.

**Nothing happens when I send a message.**
Check **Settings** — provider, model and API key must be configured. Also check
the green connection dot; a message needs the live connection.

**The agent's answer stopped mid-way.**
Look at the finish reason. `max_steps` or `interrupted` means the session is
preserved — open **Sessions**, find it, and **Continue in Agent panel** to
resume with full context.

**A task shows `failed` / `blocked`.**
That's honest reporting — details are in the task's event tail (Tasks panel →
click the task). Fix the underlying problem (often a failing check or a
missing dependency), then re-run or continue the session.

**The menu disappeared and I can't find it.**
Click the **☰ MENU** tab at the left edge of the screen, or press
<kbd>Ctrl</kbd>+<kbd>B</kbd>. (If you're on a phone: tap **☰** in the top bar.)

**I changed the model in Settings but the running agent didn't switch.**
By design — in-flight runs keep their backend so context is never destroyed.
New runs use the new model.

**Where do I report a bug?**
Open an issue on the GitHub panel (or the repo's issues page) with the session
ID from the Sessions panel and the relevant Logs panel output.

## 14. FAQ

**Q: Do I need to know programming to use this?**
No. Describe what you want in plain language. Programming knowledge helps you
*evaluate* the result — and the Workspace/QA/Terminal panels let you do that
without leaving the browser.

**Q: Is the GUI a separate product from the CLI?**
No — one system, two views. Same runtime, same database, same sessions.

**Q: Can the agent break my files?**
It works inside the server's workspace, commits are explicit (nothing enters
git history until you commit), and every change is visible in the activity
feed and diffs. Use the Git panel's branches for risky experiments.

**Q: Does it hide failures from me?**
The opposite — failures are first-class: red statuses, honest finish reasons,
full event tails, raw QA output.

**Q: Can I use it on my phone?**
Yes. On small screens the navigation becomes a slide-over drawer and panels
stack vertically. The ☰ button (or <kbd>Ctrl</kbd>+<kbd>B</kbd> on desktop)
toggles it.

**Q: How do I stop a run that's going wrong?**
**■ Cancel run** in the Agent panel. Everything done so far is kept; you can
continue the session later or start a new one.

## 15. CLI ↔ GUI cheat sheet

| I want to… | CLI | GUI |
|---|---|---|
| Run a task | `shscode "do X"` | Agent panel → type → <kbd>Enter</kbd> |
| See task status | task journal output | Tasks panel (DAG view) |
| Browse files | `ls` / editor | Workspace panel |
| Run a command | shell | Terminal panel |
| Commit / push | `shscode /git …` | Git panel buttons |
| Create a PR | `shscode /github …` | GitHub panel form |
| Verify the project | verification on run | QA panel → Run verification |
| Review a past chat | session commands | Sessions panel → Continue |
| Check system health | log output | Logs panel (live) |
| Switch model | config / env | Settings panel |
| Get help | `--help` / docs | Help / Guide panel |

---

*This guide ships with SHS Code (`docs/GUI_GUIDE.md`) and is mirrored in the
documentation repository: <https://github.com/shslab-org/shs-code-docs>.*
