---
name: web-development
description: Full-stack web development: frontend, backend, APIs, deployment
version: 1.0.0
tags: ['web', 'frontend', 'backend', 'html', 'css', 'react', 'nodejs']
required_config: []
platform: []
---

# Web Development Skill

## When to Use
Building or modifying websites, web apps, SPAs, or full-stack features.

## Protocol
1. Clarify stack (frontend framework, backend runtime, database).
2. Scaffold project structure; pin dependency versions.
3. Build backend first: data model -> API endpoints -> auth where needed.
4. Build frontend against the real API contract; mock only when blocked.
5. Wire build tooling (bundler, env vars) and error boundaries.
6. Add deployment config (Dockerfile / platform config) last.

## Verification
Dev server starts clean; API returns expected payloads; pages render without console errors; build artifact exists.
