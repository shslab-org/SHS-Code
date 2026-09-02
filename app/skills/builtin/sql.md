---
name: sql
description: SQL: schema design, queries, indexes, transactions, optimization
version: 1.0.0
tags: ['sql', 'database', 'query', 'index']
required_config: []
platform: []
---

# SQL Skill

## When to Use
Queries, schema design, index work, query optimization.

## Protocol
1. Design schema first: keys, constraints, nullability.
2. Index for the actual query patterns; drop dead indexes.
3. EXPLAIN before optimizing; measure before/after.
4. Transactions around multi-statement invariants.

## Verification
EXPLAIN confirms index usage; row counts match expectations.
