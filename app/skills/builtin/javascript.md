---
name: javascript
description: JavaScript/Node.js development: ES modules, npm, async patterns
version: 1.0.0
tags: ['javascript', 'node', 'npm', 'esm']
required_config: []
platform: []
---

# JavaScript Skill

## When to Use
Node.js servers, npm packages, browser JS, or build config.

## Protocol
1. Use ESM ('type': 'module') for new code unless CommonJS is required.
2. Pin exact dependency versions; run npm ci in clean envs.
3. Handle async with explicit try/catch or Result patterns.
4. Keep node_modules out of git; commit lockfile.

## Verification
node --check passes; npm test (if present) green.
