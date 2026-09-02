---
name: kotlin
description: Kotlin: coroutines, data classes, idiomatic patterns, multiplatform
version: 1.0.0
tags: ['kotlin', 'jvm', 'coroutines']
required_config: []
platform: []
---

# Kotlin Skill

## When to Use
Kotlin/JVM work: coroutines, data classes, KMP.

## Protocol
1. data class for pure data; sealed class for closed hierarchies.
2. Coroutines: structured concurrency, never GlobalScope.
3. Prefer val; use let/run sparingly for readability.
4. Kotlin + Java interop: nullability annotations at boundaries.

## Verification
Compiles without warnings as errors where configured; tests green.
