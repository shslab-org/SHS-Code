---
name: linux
description: Linux: shell, systemd, permissions, processes, networking tools
version: 1.0.0
tags: ['linux', 'bash', 'shell', 'systemd']
required_config: []
platform: []
---

# Linux Skill

## When to Use
Shell work, services, permissions, process/network debugging.

## Protocol
1. Read error messages fully before acting.
2. Check permissions/ownership before blaming software.
3. journalctl/systemctl for service issues; ss/netstat for network.
4. Prefer idempotent shell scripts with set -euo pipefail.

## Verification
Command exits 0; service active; expected output produced.
