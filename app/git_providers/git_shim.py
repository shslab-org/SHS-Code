"""Identity-enforcing git shim (v4.3.0 — REAL GitHub attribution).

WHY THIS EXISTS
===============
The mission rule: **work performed by SHS Code must be attributed to the
SHS-Agent identity (https://github.com/SHS-Agent) — and nothing
inside SHS Code may bypass that** — not a prompt, not a task instruction,
not a CLI flag, not an env var, not a git flag.

Env-var inheritance alone is NOT enough. Git's precedence is:

    explicit ``--author`` flag  >  ``GIT_AUTHOR_*`` env  >  ``-c user.*`` config

so an agent (or a user instruction like "commit this as me") could bypass
env-based enforcement with any of:

    git commit --author="Human <human@example.com>"
    git -c user.email=human@example.com commit ...
    env -u GIT_AUTHOR_EMAIL git commit ...
    git commit --reset-author

The shim closes ALL of those mechanically. It is installed (by
``install_git_shim()``) as ``~/.shscode/shims/git`` and that directory is
prepended to the PATH of the SHS-Code process AND every child it spawns
(agent bash sessions, GUI terminal panel, python_execute, cron jobs).
Any ``git`` invocation from inside SHS Code therefore runs through the
shim, which:

  * ``commit``     — strips every ``--author=…`` / ``--author …`` /
                     ``--reset-author`` the caller passed, appends the
                     mandatory ``--author=SHS-Agent <…>``, and execs
                     the REAL git with the four identity env vars forced
                     (the shim constructs the child env itself, so neither
                     ``env -u`` games nor inherited values can interfere).
  * merge-ish      — ``merge`` / ``revert`` / ``cherry-pick`` / ``pull`` /
                     ``rebase`` / ``am`` / ``stash`` create commits whose
                     COMMITTER (and for merges the author) come from the
                     env — the shim forces those env vars, so merge/stash
                     commits SHS Code creates are agent-attributed too.
  * everything else— passed through UNTOUCHED via ``os.execv`` (read-only
                     commands, push, branch, log, status, clone …).

The user's OWN shells outside SHS Code are never affected: the shim only
exists in PATH of processes spawned by SHS Code.

The shim script is fully self-contained (no ``app.*`` imports) so it works
in any child interpreter context. Its source lives in ``SHIM_SOURCE``.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from app import env as _env
from app.logger import logger

# The standalone shim script. Written to ~/.shscode/shims/git (0755).
# Keep it POSIX-portable and dependency-free — it runs as a plain script
# under any Python 3 the shebang resolves to.
SHIM_SOURCE = r'''#!/usr/bin/env python3
"""SHS Code git shim — mandatory SHS-Agent attribution.

Passthrough for everything except commit-creating commands, whose
author/committer are mechanically forced to the SHS-Agent identity.
Installed ONLY on the PATH of processes spawned by SHS Code; the user's
own shells outside SHS Code are untouched.
"""
import os
import sys

AGENT_NAME = "SHS-Agent"
AGENT_EMAIL = "337454460+SHS-Agent@users.noreply.github.com"

# git global options that consume the NEXT argument as their value
_VALUE_OPTS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--super-prefix", "--exec-path",
}

# subcommands that (can) create commits -> committer env forced
_COMMITTER_SUBS = {
    "commit", "merge", "revert", "cherry-pick", "pull", "rebase",
    "am", "stash", "cherry-pick", "revert",
}


def _find_real_git():
    override = os.environ.get("SHSCODE_REAL_GIT")
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        return override
    try:
        own_dir = os.path.dirname(os.path.realpath(__file__))
    except Exception:
        own_dir = ""
    search = os.environ.get("PATH", "")
    for d in search.split(os.pathsep):
        if not d:
            continue
        try:
            if own_dir and os.path.realpath(d) == own_dir:
                continue  # never resolve to ourselves
        except Exception:
            pass
        cand = os.path.join(d, "git")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    for cand in ("/usr/bin/git", "/usr/local/bin/git",
                 "/opt/homebrew/bin/git", "/bin/git"):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    sys.stderr.write("shs-git: real git binary not found\n")
    sys.exit(127)


def _split_subcommand(argv):
    """Return (subcommand, index_of_subcommand) using git's global-option
    grammar. (None, len(argv)) when no subcommand token is present."""
    i, n = 0, len(argv)
    while i < n:
        a = argv[i]
        if a == "--":
            return None, i
        if a.startswith("-"):
            if "=" not in a and a in _VALUE_OPTS:
                i += 2
            else:
                i += 1
            continue
        return a, i
    return None, n


def _strip_author_flags(sub_args):
    """Remove --author=<x>, '--author <x>' and --reset-author from commit
    arguments. Returns the cleaned argument list."""
    out = []
    i, n = 0, len(sub_args)
    while i < n:
        a = sub_args[i]
        if a == "--author":
            i += 2  # drop flag + separate value
            continue
        if a.startswith("--author="):
            i += 1
            continue
        if a == "--reset-author":
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def main():
    argv = sys.argv[1:]
    real_git = _find_real_git()
    sub, idx = _split_subcommand(argv)

    child_env = dict(os.environ)
    if sub in _COMMITTER_SUBS:
        child_env["GIT_AUTHOR_NAME"] = AGENT_NAME
        child_env["GIT_AUTHOR_EMAIL"] = AGENT_EMAIL
        child_env["GIT_COMMITTER_NAME"] = AGENT_NAME
        child_env["GIT_COMMITTER_EMAIL"] = AGENT_EMAIL

    if sub == "commit":
        sub_args = _strip_author_flags(argv[idx + 1:])
        # mandatory author goes LAST so nothing after it can override
        sub_args.append("--author=%s <%s>" % (AGENT_NAME, AGENT_EMAIL))
        new_argv = argv[: idx + 1] + sub_args
    else:
        new_argv = argv

    try:
        os.execve(real_git, [real_git] + new_argv, child_env)
    except OSError as e:  # exec failed — fall back to spawn semantics
        sys.stderr.write("shs-git: exec failed: %s\n" % e)
        sys.exit(126)


if __name__ == "__main__":
    main()
'''


def shim_install_dir() -> Path:
    """Where the shim is installed (per-user, outside any repo)."""
    return _env.home_dir() / "shims"


def shim_path() -> Path:
    name = "git.exe" if os.name == "nt" else "git"
    return shim_install_dir() / name


def install_git_shim(force: bool = False) -> bool:
    """Write the identity-enforcing git shim and put it FIRST on PATH.

    Idempotent: rewrites the shim when the embedded source changes (or
    ``force``). Prepending PATH affects THIS process and every child it
    spawns — the agent bash tool, the GUI terminal panel, python_execute,
    cron — which is exactly the enforcement scope of the mission rule.
    The user's own shells outside SHS Code are never modified.

    Returns True when the shim is active on PATH.
    """
    try:
        target = shim_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        current = None
        if target.exists():
            try:
                current = target.read_text(encoding="utf-8")
            except Exception:
                current = None
        if force or current != SHIM_SOURCE:
            tmp = target.with_suffix(".tmp")
            tmp.write_text(SHIM_SOURCE, encoding="utf-8")
            os.chmod(tmp, 0o755)
            os.replace(tmp, target)
        # prepend to PATH (deduplicated) — children inherit automatically
        shim_dir = str(target.parent)
        path = os.environ.get("PATH", "")
        parts = [p for p in path.split(os.pathsep) if p]
        if shim_dir in parts:
            parts.remove(shim_dir)
        os.environ["PATH"] = os.pathsep.join([shim_dir] + parts)
        # export the real-git override AFTER PATH surgery so the shim can
        # always find a genuine binary even if PATH were mangled later
        real = os.environ.get("SHSCODE_REAL_GIT", "")
        if not real:
            import shutil
            found = shutil.which("git")
            # shutil.which now may resolve to the shim itself — reject it
            if found:
                try:
                    if os.path.dirname(os.path.realpath(found)) == str(target.parent):
                        found = None
                except Exception:
                    pass
            if not found:
                for cand in ("/usr/bin/git", "/usr/local/bin/git",
                             "/opt/homebrew/bin/git", "/bin/git"):
                    if os.path.isfile(cand):
                        found = cand
                        break
            if found:
                os.environ["SHSCODE_REAL_GIT"] = found
        return True
    except Exception as e:
        logger.warning(f"[GitShim] install failed (env-var attribution still "
                       f"active): {e}")
        return False


def shim_active_on_path() -> bool:
    """True when the shim directory is first on PATH (enforcement active)."""
    path = os.environ.get("PATH", "")
    parts = [p for p in path.split(os.pathsep) if p]
    return bool(parts) and parts[0] == str(shim_install_dir())
