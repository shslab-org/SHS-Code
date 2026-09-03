# AI Providers Configuration Templates

This directory contains configuration templates for various free and paid AI providers supported by SHS Code.

## How to use

You can use these templates in several ways:

1. **Directly**: Copy the contents of any `.toml` file to your `config.toml` in the project root.
   ```bash
   cp providers/ollama.toml config.toml
   ```

2. **As Profiles**: Move them to your SHS Code profiles directory and use the `SHSCODE_PROFILE` environment variable.
   ```bash
   mkdir -p ~/.shscode/profiles/ollama
   cp providers/ollama.toml ~/.shscode/profiles/ollama/config.toml
   SHSCODE_PROFILE=ollama shscode "Your task"
   ```

## Included Providers

- **Ollama** (Free / Local)
- **Ollama Cloud** (Paid/Free / API)
- **OpenRouter** (Paid / API)
- **7LLM** (Paid / API)
- **Pollinations** (Free / API)
