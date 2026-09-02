#!/usr/bin/env python3
"""
SHS Code — main entry point.

SHS Code is part of the SHS Lab ecosystem (Sazzad Hussain Shobuj).
Lineage: evolved from ManusClaw, its predecessor and project foundation.

Usage:
    python main.py                # interactive SHS Code shell (the real REPL)
    python main.py "Your task"    # single-shot mode
"""
import sys


def _enter_shell() -> None:
    """Route into the full interactive SHS Code shell (app.cli.main).

    FIX (audit bug #1): this used to run a single-shot prompt with a
    hardcoded demo-task fallback on EOF. The REPL lived in app/cli.py but
    was never reachable from the installed command. Now both paths work.
    """
    from app.cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single-shot mode: python main.py "task..."
        _enter_shell()  # cli.main() handles prompt args itself
    else:
        _enter_shell()
