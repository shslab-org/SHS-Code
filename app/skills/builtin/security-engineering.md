---
name: security-engineering
description: Security engineering: authn/authz, OWASP, secrets handling, crypto
version: 1.0.0
tags: ['security', 'auth', 'owasp', 'crypto']
required_config: []
platform: []
---

# Security Engineering Skill

## When to Use
Authn/authz, secrets, input hardening, crypto choices.

## Protocol
1. Secrets never in code or logs — env/secret manager only.
2. Authz checks server-side at every boundary.
3. Parameterized queries; output encoding by context.
4. crypto: vetted libraries, boring choices, no custom ciphers.

## Verification
No secret strings in git; authz tests cover forbidden paths; dependency audit clean.
