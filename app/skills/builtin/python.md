---
name: python
description: Python development: scripting, packaging, virtualenvs, best practices
version: 1.0.0
tags: ['python', 'scripting', 'pip', 'packaging']
required_config: []
platform: []
---

# Python Skill

## When to Use
Python scripts, CLIs, libraries, packaging, or dependency work.

## Protocol
1. Choose Python 3.10+; use venv or uv for isolation.
2. Write type hints; keep public APIs annotated.
3. Package with pyproject.toml (setuptools/hatchling).
4. Pin dependencies; never mutate global state in libraries.
5. Prefer stdlib before adding deps.

## Verification
python -m py_compile passes on all changed files; script runs without import errors.
