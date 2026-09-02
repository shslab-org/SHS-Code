---
name: c
description: C programming: memory management, build systems, debugging
version: 1.0.0
tags: ['c', 'systems', 'gcc', 'make']
required_config: []
platform: []
---

# C Skill

## When to Use
Systems C code, memory-sensitive work, build systems.

## Protocol
1. Every malloc needs a matching free path — document ownership.
2. Compile with -Wall -Wextra; fix warnings, don't silence them.
3. Valgrind/ASan for suspicious paths.
4. Prefer make with explicit targets.

## Verification
Compiles warning-free under -Wall -Wextra; ASan clean on test runs.
