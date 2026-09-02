---
name: typescript
description: TypeScript: typing, tsconfig, build pipelines, strict mode
version: 1.0.0
tags: ['typescript', 'ts', 'typing']
required_config: []
platform: []
---

# TypeScript Skill

## When to Use
Adding types, tsconfig tuning, or TS project scaffolding.

## Protocol
1. Start strict: strict true, noUncheckedIndexedAccess where feasible.
2. Types for all public functions; avoid any except at boundaries.
3. Use discriminated unions over optional-field soup.
4. Build via tsc --noEmit in CI.

## Verification
tsc --noEmit reports zero errors on changed code.
