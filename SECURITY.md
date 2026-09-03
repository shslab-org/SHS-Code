# Security Policy

## Supported Versions

| Version | Supported | Status |
|---------|-----------|--------|
| 5.0.x | Yes | Latest Stable |
| 4.x.x | Yes | Maintenance |
| < 4.0.0 | No | End of Life |

**Only versions 1.0.x and above are officially supported.** If you are running an older version, upgrade immediately.

## Reporting a Vulnerability

**Do NOT open a public issue for security vulnerabilities.** Public disclosures can put all users at risk before a fix is available.

If you discover a security vulnerability in SHS Code, report it responsibly:

### How to Report

1. **Email**: Send a detailed report to [thejddev.official@gmail.com](mailto:thejddev.official@gmail.com)
2. **Subject Line**: Use `[SHS Code SECURITY]` as the prefix (e.g., `[SHS Code SECURITY] Credential Leak in SessionDB`)
3. **Include**:
   - A clear description of the vulnerability
   - Steps to reproduce the issue
   - The affected component (LLM layer, session DB, sandbox, SSH server, webhook handler, etc.)
   - Potential impact assessment
   - Any proof-of-concept code or screenshots (optional but helpful)

### What to Expect

- **Acknowledgment**: Within 24 hours of receiving your report
- **Assessment**: Within 48 hours — we will evaluate the severity and scope
- **Fix Timeline**:
  - **Critical** (RCE, credential leak, auth bypass): Patch within 72 hours
  - **High** (data exposure, privilege escalation): Patch within 1 week
  - **Medium/Low** (informational, best practices): Address in next release cycle
- **Disclosure**: We will publicly disclose the fix after it is deployed, giving credit to the reporter (unless you request anonymity)

### Scope

This security policy covers:
- The SHS Code core framework (`app/` directory)
- All LLM provider integrations (`app/llm/`)
- Session database and memory systems (`app/db/`, `app/memory/`)
- Sandbox execution environments (`app/sandbox/`)
- SSH server (`app/ssh_server.py`, `app/ssh/`)
- Webhook endpoints (`app/server/webhooks.py`)
- Messaging channel adapters (`app/messaging/`)
- Configuration system and credential handling (`app/config.py`, `app/llm/credential_pool.py`)

Out of scope: Third-party LLM provider APIs (OpenAI, Anthropic, Groq, etc.), user-deployed infrastructure, user-created config files with exposed credentials.

## Security Features in SHS Code

SHS Code includes several built-in security mechanisms:
- **IdentityGuard**: 30+ anti-jailbreak regex patterns protecting against prompt injection
- **Permission Gate**: Three-tier tool authorization (Allow / Ask / Deny)
- **Credential Pool**: API key rotation with 60s cooldown on exhaustion
- **Secret Redaction**: Optional log redaction of API keys (`SHSCODE_REDACT=true`)
- **SSH Restricted Shell**: Command whitelisting with public-key-only authentication
- **Webhook HMAC Verification**: SHA-256 signature verification on incoming webhooks
- **Sandbox Isolation**: Docker, SSH, and OpenShell backends for untrusted code execution

---

*This security policy is maintained by The-JDdev (SHS Lab). For questions, contact [thejddev.official@gmail.com](mailto:thejddev.official@gmail.com).*
