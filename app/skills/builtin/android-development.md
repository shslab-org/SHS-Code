---
name: android-development
description: Android app development with Kotlin/Java, Gradle, Jetpack
version: 1.0.0
tags: ['android', 'kotlin', 'java', 'gradle', 'jetpack', 'mobile']
required_config: []
platform: []
---

# Android Development Skill

## When to Use
Building Android apps: Activities/Fragments, Gradle setup, permissions, releases.

## Protocol
1. Identify minSdk/targetSdk and applicationId before touching code.
2. Prefer Kotlin + Jetpack (ViewModel, Room) unless the project says otherwise.
3. Manage all permissions in the manifest + runtime requests.
4. Build with ./gradlew assembleDebug first; release builds need signing.
5. Keep versionCode strictly increasing.

## Verification
gradle build succeeds; APK installs and launches; no runtime crash on open.
