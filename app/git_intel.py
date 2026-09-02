from __future__ import annotations

"""
SHS Code — Git Intelligence 2.0 (spec §31) + Smart Rollback (spec §33)
========================================================================
GitIntelligence: branch, status, diff stats, staged, commits, remote,
recent history, merge state, conflicts — captured from the REAL repo.
"Never claim a commit exists unless it actually exists" — every claim
here is the output of an actual git subprocess.

SmartRollback: file-level safety net BEFORE significant changes.
Snapshots copy agent-touched files into ~/.manusclaw/rollback/<task_id>/
(with a manifest + git HEAD). Restore only touches the files the agent
changed — unrelated user work is never destroyed (spec §33 rule 5).
Falls back to no-op when git is absent or the dir isn't a repo.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logger import logger

HOME = Path(os.getenv("MANUSCLAW_HOME", str(Path.home() / ".manusclaw")))
ROLLBACK_DIR = HOME / "rollback"


def _git(root: Path, *args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True, timeout=timeout)


def _git_ok(root: Path, *args: str, timeout: int = 15) -> Optional[str]:
    try:
        r = _git(root, *args, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


class GitIntelligence:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root or Path.cwd()).resolve()

    def is_repo(self) -> bool:
        return _git_ok(self.root, "rev-parse", "--git-dir") is not None

    def state(self) -> Dict[str, Any]:
        """Full snapshot (spec §31): branch, status, diff, staged, commits,
        remote, history, merge state, conflicts."""
        if not self.is_repo():
            return {"is_repo": False, "root": str(self.root)}
        branch = _git_ok(self.root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
        head = _git_ok(self.root, "rev-parse", "HEAD") or ""
        status = _git_ok(self.root, "status", "--porcelain=v1") or ""
        entries = [l for l in status.split("\n") if l.strip()]
        staged = [l[3:] for l in entries if l[:2].strip() and l[0] != " " and l[:2] != "??"]
        untracked = [l[3:] for l in entries if l.startswith("??")]
        modified = [l[3:] for l in entries if l[1] == "M" or l[:2] == " M"]
        diff_stat = _git_ok(self.root, "diff", "--stat", "HEAD") or ""
        conflicts = self._conflicts()
        merge_head = (self.root / ".git" / "MERGE_HEAD").exists()
        rebase_dir = any((self.root / ".git" / d).exists()
                         for d in ("rebase-merge", "rebase-apply"))
        remote = _git_ok(self.root, "remote", "get-url", "origin") or ""
        history = self._history(10)
        ahead_behind = self._ahead_behind()
        return {
            "is_repo": True, "root": str(self.root),
            "branch": branch, "head": head[:12],
            "dirty": bool(entries), "dirty_files": len(entries),
            "staged": staged[:20], "untracked": untracked[:20],
            "modified": modified[:20],
            "diff_stat": diff_stat[:1200],
            "diff_files": self._diff_files(),
            "merge_in_progress": merge_head or rebase_dir,
            "conflicts": conflicts,
            "remote": remote,
            "history": history,
            "ahead": ahead_behind.get("ahead", 0),
            "behind": ahead_behind.get("behind", 0),
        }

    def _conflicts(self) -> List[str]:
        status = _git_ok(self.root, "status", "--porcelain=v1") or ""
        return [l[3:] for l in status.split("\n") if l[:2] in ("UU", "AA", "DD", "AU", "UA", "DU", "UD")]

    def _diff_files(self) -> List[str]:
        out = _git_ok(self.root, "diff", "--name-only", "HEAD") or ""
        return [l for l in out.split("\n") if l.strip()][:50]

    def _history(self, n: int) -> List[Dict[str, str]]:
        fmt = "%h%x1f%an%x1f%ar%x1f%s"
        out = _git_ok(self.root, "log", f"-{n}", f"--pretty=format:{fmt}") or ""
        commits = []
        for line in out.split("\n"):
            parts = line.split("\x1f")
            if len(parts) == 4:
                commits.append({"hash": parts[0], "author": parts[1],
                                "when": parts[2], "subject": parts[3][:100]})
        return commits

    def _ahead_behind(self) -> Dict[str, int]:
        out = _git_ok(self.root, "rev-list", "--left-right", "--count",
                      "HEAD...@{u}")
        if out:
            try:
                a, b = out.split()
                return {"ahead": int(a), "behind": int(b)}
            except Exception:
                pass
        return {}

    def diff_of(self, path: str) -> str:
        out = _git_ok(self.root, "diff", "HEAD", "--", path, timeout=20)
        return (out or "")[:6000]

    def verify_commit_exists(self, ref: str) -> bool:
        """spec §31: never claim a commit exists unless it does."""
        return _git_ok(self.root, "rev-parse", "--verify", f"{ref}^{{commit}}") is not None

    def render(self) -> str:
        s = self.state()
        if not s.get("is_repo"):
            return f"git: not a repository ({s['root']})"
        lines = [f"Git: {s['branch']} @ {s['head']}  (dirty: {s['dirty_files']})"]
        if s.get("ahead") or s.get("behind"):
            lines.append(f"  vs upstream: ahead {s['ahead']}, behind {s['behind']}")
        if s.get("staged"):
            lines.append("  staged: " + ", ".join(s["staged"][:6]))
        if s.get("modified"):
            lines.append("  modified: " + ", ".join(s["modified"][:6]))
        if s.get("untracked"):
            lines.append("  untracked: " + ", ".join(s["untracked"][:6]))
        if s.get("conflicts"):
            lines.append(f"  ⚠ CONFLICTS: {', '.join(s['conflicts'][:6])}")
        if s.get("merge_in_progress"):
            lines.append("  ⚠ merge/rebase in progress")
        for c in (s.get("history") or [])[:5]:
            lines.append(f"  {c['hash']} {c['when']:<10} {c['subject'][:70]}")
        return "\n".join(lines)


def git_status_line(root: Optional[Path] = None) -> str:
    """One-liner for /status: branch + dirty count + last commit."""
    gi = GitIntelligence(root)
    try:
        return gi.render().split("\n")[0]
    except Exception:
        return "git: unavailable"


# ──────────────────────────────────────────────────────────────────────────────
# Smart rollback (spec §33)
# ──────────────────────────────────────────────────────────────────────────────

class SmartRollback:
    """File-level snapshots of agent-modified files, restorable on failure."""

    def __init__(self, task_id: str, root: Optional[Path] = None) -> None:
        self.task_id = task_id
        self.root = Path(root or Path.cwd()).resolve()
        self.dir = ROLLBACK_DIR / re.sub(r"[^a-zA-Z0-9_-]", "", task_id)
        self.manifest_path = self.dir / "manifest.json"

    def _manifest(self) -> Dict[str, Any]:
        try:
            if self.manifest_path.exists():
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"task_id": self.task_id, "root": str(self.root), "snapshots": []}

    def snapshot(self, paths: List[str], reason: str = "") -> Optional[str]:
        """Backup current contents of `paths` before modification.
        Returns snapshot id, or None if nothing to snapshot / git-clean."""
        paths = [p for p in paths if p]
        if not paths:
            return None
        manifest = self._manifest()
        sid = f"snap{len(manifest['snapshots']) + 1}-{int(time.time())}"
        snap_dir = self.dir / sid
        backed: List[Dict[str, Any]] = []
        head = ""
        try:
            head = _git_ok(self.root, "rev-parse", "HEAD") or ""
        except Exception:
            pass
        for rel in paths:
            src = Path(rel)
            if not src.is_absolute():
                src = self.root / rel
            if not src.exists() or not src.is_file():
                continue
            dst = snap_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dst)
                backed.append({"path": rel, "size": src.stat().st_size,
                               "mtime": src.stat().st_mtime})
            except OSError as e:
                logger.debug(f"[Rollback] copy failed {rel}: {e}")
        if not backed:
            return None
        try:
            from app.state import Journal
            gi = GitIntelligence(self.root)
            git_head = head or ""
            _ = Journal  # (journal records rollback events; imported lazily elsewhere)
        except Exception:
            git_head = head
        manifest["snapshots"].append({
            "id": sid, "at": time.time(), "reason": reason[:200],
            "git_head": head, "files": backed})
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception as e:
            logger.debug(f"[Rollback] manifest write failed: {e}")
            return None
        return sid

    def restore(self, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        """Restore files from the latest (or given) snapshot. Only files the
        agent snapshotted are touched — never unrelated user work."""
        manifest = self._manifest()
        snaps = manifest.get("snapshots") or []
        if not snaps:
            return {"ok": False, "error": "no snapshots for this task"}
        snap = snaps[-1]
        if snapshot_id:
            snap = next((s for s in snaps if s["id"] == snapshot_id), snap)
        restored, missing = [], []
        for f in snap.get("files", []):
            rel = f["path"]
            src = self.dir / snap["id"] / rel
            dst = self.root / rel
            if src.exists():
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    restored.append(rel)
                except OSError as e:
                    logger.warning(f"[Rollback] restore failed {rel}: {e}")
            else:
                missing.append(rel)
        return {"ok": bool(restored), "restored": restored, "missing": missing,
                "snapshot": snap["id"], "reason": snap.get("reason", "")}

    def list_snapshots(self) -> List[Dict[str, Any]]:
        return self._manifest().get("snapshots") or []
