# Claude Code over GitHub Copilot

## Overview

Routes Claude Code through the GitHub Copilot API instead of Anthropic's servers, using a local LiteLLM proxy as a translation layer. No company data leaves to Anthropic — all traffic goes through our existing GitHub Copilot agreement.

**References:**
- [Claude Code LLM Gateway](https://docs.anthropic.com/en/docs/claude-code/llm-gateway)
- [LiteLLM GitHub Copilot Provider](https://docs.litellm.ai/docs/providers/github_copilot)

## Prerequisites

| Dependency | Minimum version | Install |
|---|---|---|
| **Python** | 3.11+ | [python.org/downloads](https://www.python.org/downloads/) |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) — includes `npm` |
| **GitHub Copilot** | Active subscription | Required for API access |

### Verify prerequisites

```bash
python --version    # should be 3.11+
node --version      # should be 18+
npm --version
```

## Quick Start

Use `run <command>` from this repo root.
- PowerShell: `.\run <command>`
- Bash/Zsh: `./run <command>`

### 1. Install Claude Code (if not already installed)
```bash
run install-claude
```

### 2. Initial Setup
```bash
run setup
```
Creates a Python virtual environment, installs dependencies, and generates API keys in `.env`.

### 3. Configure Claude Code
```bash
run claude-enable
```
Backs up existing Claude settings and configures Claude Code to use `http://localhost:4444`.

### 4. Start the Proxy
> **Note:** The first run will prompt for GitHub device authentication — follow the terminal instructions.
```bash
run start
```

### 5. Test the Connection
```bash
run test
```

### 6. Start Claude Code in your project
```bash
claude
```

## Available Models

The proxy exposes these Anthropic models (configured in `copilot-config.yaml`):

| Model name | GitHub Copilot model | Context |
|---|---|---|
| `claude-opus-4-6` | `github_copilot/claude-opus-4.6` | 200k |
| `claude-sonnet-4-6` | `github_copilot/claude-sonnet-4.6` | 200k |
| `claude-sonnet-4-5` *(default)* | `github_copilot/claude-sonnet-4.5` | 200k |
| `claude-haiku-4-5` | `github_copilot/claude-haiku-4.5` | 200k |

To switch the default model, edit `ANTHROPIC_MODEL` in `~/.claude/settings.json`, or update `scripts/claude_enable.py` and re-run `run claude-enable`.

A `gpt-4` model is also available as the fast/small fallback (`ANTHROPIC_SMALL_FAST_MODEL`).

## Additional Commands

| Command | Description |
|---|---|
| `run claude-status` | Show current Claude settings and proxy health |
| `run claude-disable` | Restore Claude Code to default Anthropic servers |
| `run stop` | Stop the LiteLLM proxy |
| `run list-models` | List all available GitHub Copilot models |
| `run list-models-enabled` | List only enabled models |

## Troubleshooting

- **First run authentication**: `run.py start` will prompt for GitHub device auth — complete it in the browser.
- **Connection errors**: Run `run.py test` to verify the proxy is reachable, and `run.py claude-status` to check settings.
- **Unsupported parameter errors**: Already handled — `drop_params: true` is set in `copilot-config.yaml`.
- **Wrong model name**: Run `run.py list-models-enabled` to see valid model IDs, then update `copilot-config.yaml`.
- **Reset everything**: `run.py claude-disable` → `run.py claude-enable`.
