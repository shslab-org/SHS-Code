---
name: java
description: Java: Maven/Gradle, JVM tuning, streams, concurrency
version: 1.0.0
tags: ['java', 'jvm', 'maven', 'gradle']
required_config: []
platform: []
---

# Java Skill

## When to Use
Java services, Maven/Gradle modules, JVM behavior.

## Protocol
1. Maven coordinates + BOM for dependency alignment.
2. Streams for transforms; explicit concurrency via executors.
3. Close resources with try-with-resources.
4. Watch JVM memory when adding heavy libs.

## Verification
mvn/gradle build passes; no NoClassDefFound at runtime.
