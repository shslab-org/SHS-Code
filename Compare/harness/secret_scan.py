#!/usr/bin/env python3
"""Scan all Compare/ files for secrets. FAIL if any found (post-redaction check)."""
import re
import sys
from pathlib import Path

COMPARE = Path("/home/z/my-project/benchmark/Compare")

PATTERNS = {
    "nvapi-key": re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
    "github-token": re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    "hf-token": re.compile(r"hf_[A-Za-z0-9]{30,}"),
    "bearer": re.compile(r"[Bb]earer\s+[A-Za-z0-9_\-\.]{30,}"),
    "auth-header-full": re.compile(r"Authorization[\"':\s=]+[A-Za-z0-9_\-\.]{30,}"),
    "password-assign": re.compile(r"(?i)password[\"'\s:=]+[^\s\"']{12,}"),
}

found = 0
for f in COMPARE.rglob("*"):
    if not f.is_file() or f.suffix in (".png", ".jpg"):
        continue
    try:
        text = f.read_text(errors="replace")
    except Exception:
        continue
    for name, pat in PATTERNS.items():
        for m in pat.finditer(text):
            # allow the redacted marker itself
            frag = m.group(0)
            if "[REDACTED]" in frag:
                continue
            print(f"SECRET? [{name}] {f.relative_to(COMPARE)}: {frag[:50]}...")
            found += 1

if found:
    print(f"\nFAILED: {found} potential secrets found")
    sys.exit(1)
print("CLEAN: no secrets found in", sum(1 for _ in COMPARE.rglob('*') if _.is_file()), "files")
