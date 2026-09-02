---
name: debugging
description: Systematic debugging: root cause analysis, breakpoints, logging, profiling
version: 1.0.0
tags: ['debug', 'diagnosis', 'profiling']
required_config: []
platform: []
---

# Debugging Skill

## When to Use
Diagnosing failures, crashes, wrong behavior, performance.

## Protocol
1. Reproduce reliably; capture exact error + stack.
2. Bisect: halve the search space (input, commit, code path).
3. Form one hypothesis; instrument; verify; repeat.
4. Fix the root cause, never the symptom.

## Verification
Failure no longer reproduces after fix; a regression test exists.
