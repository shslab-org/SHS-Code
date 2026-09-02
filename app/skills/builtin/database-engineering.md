---
name: database-engineering
description: Database engineering: modeling, migrations, ORMs, scaling
version: 1.0.0
tags: ['database', 'schema', 'orm', 'migration']
required_config: []
platform: []
---

# Database Engineering Skill

## When to Use
Data models, migrations, ORM work, scaling.

## Protocol
1. Schema in migrations, never ad-hoc DDL.
2. Forward-only migrations; each one reversible in plan if not in code.
3. N+1 audits before shipping ORM features.
4. Backup/restore tested, not assumed.

## Verification
Migrations apply cleanly on a fresh DB; queries under ORM show no N+1.
