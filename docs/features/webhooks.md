# Webhook System

**Status:** ✅ Implemented

## Description
Incoming webhook management with HMAC-SHA256 verification and template-based prompt formatting.

## Configuration
Webhooks configured via API or `shscode-webhook` CLI. No env vars needed.

## Features
- HMAC-SHA256 signature verification (per-hook secret)
- Template variables: `{{payload.field}}` and `{{payload.nested.field}}`
- SQLite persistence
- Trigger count tracking
- Enable/disable per hook

## Entry Point
```bash
shscode-webhook
```

## Architecture
`WebhookManager` → SQLite → Agent trigger. Each trigger creates a `SHSCode()` agent with the formatted prompt.
