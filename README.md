# Claude Code over GitHub Copilot

## Overview

Routes Claude Code through the GitHub Copilot API instead of Anthropic's servers, using a local LiteLLM proxy as a translation layer. No company data leaves to Anthropic — all traffic goes through our existing GitHub Copilot agreement.

**References:**
- [Claude Code LLM Gateway](https://docs.anthropic.com/en/docs/claude-code/llm-gateway)
- [LiteLLM GitHub Copilot Provider](https://docs.litellm.ai/docs/providers/github_copilot)

## Prerequisites

| Dependency | Minimum version | Install |
|---|---|---|
| **Python** | 3.11+ | [python.org/downloads](https://www.python.org/downloads/) or `brew install python` on macOS |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) or `brew install node` on macOS — includes `npm` |
| **GitHub Copilot** | Active subscription | Required for API access |

> **macOS note:** Xcode Command Line Tools (`xcode-select --install`) provide `python3` and `git`. Alternatively install Python via [Homebrew](https://brew.sh).

### Verify prerequisites

```bash
python3 --version   # should be 3.11+  (use 'python' on Windows)
node --version       # should be 18+
npm --version
```

## Quick Start

The `run` script lives in the repo root. How you invoke it depends on your shell:

| Shell | Command style |
|---|---|
| macOS / Linux (Bash/Zsh) | `./run <command>` |
| Windows PowerShell | `.\run <command>` |
| Windows cmd | `run <command>` |

> **macOS tip:** If `./run` gives a permission error after cloning, run `chmod +x run` once.

The steps below show the command without a prefix — add the appropriate one for your shell.

### 1. Install Claude Code (if not already installed)
```
run install-claude
```

### 2. Initial Setup
```
run setup
```
Creates a Python virtual environment, installs dependencies, and generates API keys in `.env`.

### 3. Configure Claude Code
```
run claude-enable
```
Backs up existing Claude settings and configures Claude Code to use `http://localhost:4444`.

### 4. Start the Proxy
> **Note:** The first run will prompt for GitHub device authentication — follow the terminal instructions.
```
run start
```

### 5. Test the Connection
```
run test
```

### 6. Start Claude Code in your project
```
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

- **First run authentication**: `run start` will prompt for GitHub device auth — complete it in the browser.
- **Connection errors**: Run `run test` to verify the proxy is reachable, and `run claude-status` to check settings.
- **Unsupported parameter errors**: Already handled — `drop_params: true` is set in `copilot-config.yaml`.
- **Wrong model name**: Run `run list-models-enabled` to see valid model IDs, then update `copilot-config.yaml`.
- **Reset everything**: `run claude-disable` → `run claude-enable`.
- **macOS permission denied on `./run`**: Run `chmod +x run` to make the script executable.
- **macOS `python` not found**: Use `python3` instead, or run `./run` which already uses `python3`.
- **PowerShell `run` not recognized**: Use `.\run <command>` — PowerShell requires the explicit `./` prefix for local scripts.
