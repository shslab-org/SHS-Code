---
name: automation
description: Automation: scripting, cron, CI/CD pipelines, task runners
version: 1.0.0
tags: ['automation', 'cron', 'ci', 'pipelines']
required_config: []
platform: []
---

# Automation Skill

## When to Use
Scripts, cron jobs, CI/CD pipelines, task automation.

## Protocol
1. Idempotency: running twice must equal running once.
2. Explicit failure: exit non-zero + actionable message.
3. Logging to a file, not just stdout, for scheduled contexts.
4. CI pipelines: fast feedback first, thorough checks second.

## Verification
Re-run produces same end state; failing step exits non-zero; logs exist.
