# Contributing to SHS Code

Welcome to the most fire autonomous agent ecosystem on the planet. SHS Code is a no-GUI, pure-power AI agent framework — and we need builders who think in systems, not just snippets.

This guide will walk you through everything you need to start contributing effectively.

---

## The SHS Code Contribution Philosophy

SHS Code is not a chatbot wrapper. It is a **production-grade autonomous agent** with a PAORR reasoning loop, 14+ tools, 10+ LLM providers, 12+ messaging channels, voice I/O, SSH gateway, and three sandbox backends. Every contribution should reflect this ethos: **build for production, test for chaos, ship with confidence.**

We value:
- **Brutal efficiency** — clean code that does more with less
- **System-level thinking** — understand how your change ripples across the architecture
- **Testing rigor** — every feature ships with tests (we run 210+ tests on every PR)
- **Documentation discipline** — if you add a feature, you update the docs

---

## Getting Started

### Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|--------------|
| Python | 3.11 | 3.12+ |
| OS | Linux | Ubuntu 22.04+ / Termux (Android) |
| Git | 2.30+ | Latest |
| Tests | pytest, pytest-asyncio, pytest-xdist | Latest |

### Quick Setup

```bash
# 1. Fork the repository on GitHub
# 2. Clone YOUR fork locally
git clone https://github.com/YOUR_USERNAME/manusclaw.git
cd manusclaw

# 3. Install with all dependencies
pip install -e ".[all-plus]"

# 4. Run the test suite to verify your environment
APP_ENV=test pytest -n 4 -q
# Expected: 210 passed, 2 skipped
```

---

## Contribution Workflow

### 1. Fork & Branch

```bash
# Always work on a feature branch — NEVER on main
git checkout -b feat/your-feature-name
# or
git checkout -b fix/your-bug-fix
# or
git checkout -b docs/your-doc-update
```

**Branch Naming Convention**:
- `feat/` — New features (e.g., `feat/mcp-protocol-support`)
- `fix/` — Bug fixes (e.g., `fix/credential-pool-deadlock`)
- `docs/` — Documentation only (e.g., `docs/ssh-gateway-guide`)
- `refactor/` — Code refactoring (e.g., `refactor/llm-retry-logic`)
- `test/` — Test additions/improvements (e.g., `test/canvas-edge-cases`)

### 2. Write Your Code

Follow the SHS Code codebase conventions:
- **Type hints** on all public functions and methods
- **Docstrings** on all modules, classes, and public functions
- **Pydantic models** for configuration and data structures
- **Async-first** — SHS Code is heavily async; follow the existing patterns
- **Error handling** — use SHS Code's custom exceptions from `app/exceptions.py`

### 3. Test on Linux / Termux

SHS Code runs on both full Linux environments and Android Termux. Test on both if possible:

```bash
# Full Linux test
APP_ENV=test pytest -n 4 -q

# Single test file (if you can't run the full suite)
APP_ENV=test pytest tests/test_your_new_feature.py -v
```

**Testing Requirements**:
- All new features must include tests
- Tests must pass with `APP_ENV=test` (MockLLM — no API keys needed)
- Follow the existing test patterns in `tests/conftest.py`
- Use `pytest-asyncio` for async tests
- Target: maintain 210+ passing tests

### 4. Commit

Write professional, descriptive commit messages:

```bash
# Good examples:
git commit -m "feat: add MCP protocol client and server integration"
git commit -m "fix: resolve credential pool deadlock on concurrent exhaustion"
git commit -m "docs: update SSH gateway setup with authorized_keys instructions"
git commit -m "refactor: extract LLM retry logic into dedicated strategy module"
git commit -m "test: add Canvas A2UI edge case tests for concurrent updates"

# Bad examples (WILL BE REJECTED):
git commit -m "fixed stuff"
git commit -m "update"
git commit -m "wip"
git commit -m "asdf"
```

### 5. Push & Pull Request

```bash
# Push to your fork
git push origin feat/your-feature-name

# Open a PR on GitHub targeting the `main` branch
```

**PR Checklist** (verify before submitting):
- [ ] Code follows existing style and conventions
- [ ] All tests pass (`APP_ENV=test pytest -n 4 -q`)
- [ ] New features include corresponding tests
- [ ] Documentation is updated (README.md, setup guide, or docstrings)
- [ ] No hardcoded API keys, secrets, or credentials
- [ ] Commit messages are descriptive and follow convention

---

## Architecture Overview for Contributors

Understanding the SHS Code architecture is essential for making effective contributions:

```
app/
├── agent/          # PAORR loop, routing, multi-agent orchestrator
├── llm/            # Universal LLM router, credential pool, offline routers
├── tool/           # 14+ tools (bash, python, browser, editor, etc.)
├── sandbox/        # Docker, SSH, OpenShell execution backends
├── messaging/      # 12+ channel adapters (Telegram, Discord, etc.)
├── server/         # FastAPI server, webhooks, static UI
├── voice/          # TTS providers, wake word, talk mode
├── db/             # SessionDB (SQLite WAL + FTS5)
├── memory/         # Short-term, long-term memory
├── canvas/         # A2UI protocol
├── config.py       # 7-layer configuration system
├── cli.py          # Interactive shell
└── permissions/    # Identity guard, permission gate
```

### Key Files for Common Contributions

| If you want to... | Look at... |
|---|---|
| Add a new LLM provider | `app/llm/llm.py`, `app/llm/offline_router.py` |
| Add a new messaging channel | `app/messaging/base.py`, any existing adapter |
| Add a new tool | `app/tool/base.py`, any existing tool |
| Add a new sandbox backend | `app/sandbox/factory.py`, any existing backend |
| Modify the PAORR loop | `app/agent/react.py`, `app/agent/manus.py` |
| Add a new voice TTS provider | `app/voice/tts.py` |
| Modify config system | `app/config.py` |

---

## Areas We Need Help With

- **New LLM Providers**: DeepSeek, Cohere, Together AI, Fireworks AI
- **New Tools**: Git operations, database queries, API testing, deployment
- **New Channels**: Rocket.Chat, Zulip, Webex, Threema
- **Performance**: LLM response caching, tool execution parallelization
- **Documentation**: Translation (Bengali, Hindi, Arabic), video tutorials
- **Testing**: Edge case coverage, fuzz testing, integration tests
- **Desktop Apps**: Qt-based desktop client, KDE/GNOME integration

---

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for our community standards.

---

## Questions?

- Open a [GitHub Discussion](https://github.com/ManusAgents/manusclaw/discussions) for general questions
- Email security issues to [thejddev.official@gmail.com](mailto:thejddev.official@gmail.com)
- Join [Telegram](https://t.me/singularityos) for community chat

---

*SHS Code is built by The-JDdev (SHS Lab). Contributing to SHS Code means you're building the future of autonomous AI agents.*
