---
name: testing
description: Testing: unit, integration, e2e, pytest/jest, coverage, TDD
version: 1.0.0
tags: ['testing', 'pytest', 'jest', 'tdd', 'coverage']
required_config: []
platform: []
---

# Testing Skill

## When to Use
Writing or fixing tests; coverage; TDD flows.

## Protocol
1. Reproduce the failure with the smallest possible test.
2. Unit tests for logic; integration tests for wiring; e2e sparingly.
3. Deterministic tests: freeze time, seed randomness, mock IO.
4. Coverage is a signal, not a target.

## Verification
Full suite green locally; flaky tests quarantined or fixed.
