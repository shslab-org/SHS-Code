---
name: git
description: Git mastery: branching, rebasing, submodules, recovery, history surgery
version: 1.0.0
tags: ['git', 'vcs', 'branch', 'rebase']
required_config: []
platform: []
---

# Git Skill

## When to Use
Branching strategy, rebases, history repair, recovery.

## Protocol
1. Inspect state first: status, log --graph, stash list.
2. Prefer fixup commits + rebase -i over amend chains.
3. Never force-push shared branches without coordination.
4. Reflog is the recovery net — nothing is truly lost.

## Verification
git status shows intended state; log graph matches plan.
