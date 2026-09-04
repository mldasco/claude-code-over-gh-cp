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
Creates a Python virtual environment, installs dependencies, generates API keys in `.env`, and **automatically sets up cost tracking**:
- **Windows**: downloads portable PostgreSQL (~350 MB, no admin required) into `postgres/`
- **macOS**: starts your Homebrew PostgreSQL if available
- **No PostgreSQL found**: setup completes without cost tracking — run `run cost-tracking-init` later

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
| `claude-opus-4-8` *(default)* | `github_copilot/claude-opus-4.8` | 200k |
| `claude-opus-5` | `github_copilot/claude-opus-5` | 200k |
| `claude-sonnet-5` | `github_copilot/claude-sonnet-5` | 200k |
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
| `run cost-tracking-init` | Set up cost tracking — auto-detects or installs PostgreSQL |
| `run cost-tracking-init --postgres-url URL` | Set up cost tracking with a specific PostgreSQL URL |
| `run postgres-init` | Explicitly set up local PostgreSQL (Windows: portable install; macOS: system/Homebrew) |
| `run postgres-start` | Start the local portable PostgreSQL |
| `run postgres-stop` | Stop the local portable PostgreSQL |
| `run prisma-init` | Re-run Prisma generate + DB migration |

## Optional: Spend Tracking & Access Control

LiteLLM provides an Admin UI for managing virtual keys, tracking spend, setting budgets, and controlling model access. This is useful for:

- **Tracking costs** per user or team
- **Setting spending limits** (daily/monthly budgets)
- **Restricting model access** (e.g., limit expensive models)

### Prerequisites for Cost Tracking

LiteLLM requires a PostgreSQL database. The setup command handles it automatically:

```
run cost-tracking-init
```

| Platform | What happens |
|----------|-------------|
| **Windows** | Downloads portable PostgreSQL binaries (~350 MB, no admin required) into `postgres/`, initializes on port 5433, and runs the Prisma migration. |
| **macOS** | Uses a running Homebrew PostgreSQL if found; starts it automatically if a formula is installed. |
| **Linux / other** | Checks for a running local PostgreSQL. If none found, prints install instructions. |

Once set up, `run start` auto-starts the local PostgreSQL on every launch.

To use a specific existing database instead:
```
run cost-tracking-init --postgres-url postgresql://user:password@host:5432/litellm
```

To re-run the Prisma migration separately (e.g. after a LiteLLM upgrade):
```
run prisma-init
```

### Enable the Admin UI

1. **Get virtual key** with admin permissions:
  Get `LITELLM_MASTER_KEY` in `.env`

2. **Access the Admin UI** at `http://localhost:4444/ui`:
   - Login with the generated key
   - View usage metrics and costs
   - Set budget

### Key Management Workflow

1. **Create virtual keys** for user via the UI
2. **Set budgets** (e.g., $50/month per user)
3. **Restrict models** (e.g., only allow Claude Haiku for testing)
4. **Update Claude settings** to use the virtual key instead of master key

**Full documentation:** [LiteLLM Docker Quick Start - Virtual Keys](https://docs.litellm.ai/docs/proxy/docker_quick_start#optional-generate-a-virtual-key)

## Troubleshooting

- **First run authentication**: `run start` will prompt for GitHub device auth — complete it in the browser.
- **Connection errors**: Run `run test` to verify the proxy is reachable, and `run claude-status` to check settings.
- **SSL certificate errors during `run cost-tracking-init`**: Prisma CLI is a Node.js binary. On Windows, this tool automatically exports the Windows trusted root store (including corporate CA certs from IT policy) and passes it to Node.js via `NODE_EXTRA_CA_CERTS`. If you still see SSL errors, set `NODE_EXTRA_CA_CERTS` manually:
  ```powershell
  $env:NODE_EXTRA_CA_CERTS = "C:\path\to\ca-bundle.pem"
  .\run cost-tracking-init --postgres-url URL
  ```
- **SSL certificate trust errors**: LiteLLM may fail when connecting to `api.individual.githubcopilot.com` if your machine is behind a corporate TLS proxy or firewall that intercepts HTTPS traffic (for example, Zscaler). In that case the proxy presents its own intermediate/root certificate, and Python/OpenSSL must trust that certificate chain.
  - The proxy now preserves and merges any existing `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` bundle with the venv `certifi` bundle, but you still need the proxy root cert in the trusted bundle.
  - On macOS, export the trusted bundle from the system keychain and use it when starting LiteLLM:
    ```bash
    security find-certificate -a -c 'Zscaler' -p > /tmp/zscaler_keychain_certs.pem
    export SSL_CERT_FILE=/tmp/zscaler_keychain_certs.pem
    export REQUESTS_CA_BUNDLE=$SSL_CERT_FILE
    ./run start
    ```
  - If `run test` still fails with `[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate`, the current CA bundle does not include the intercepting proxy root. Add that root cert to your trusted bundle or use the exported keychain PEM above.
- **Unsupported parameter errors**: Already handled — `drop_params: true` is set in `copilot-config.yaml`.
- **Wrong model name**: Run `run list-models-enabled` to see valid model IDs, then update `copilot-config.yaml`.
- **Reset everything**: `run claude-disable` → `run claude-enable`.
- **macOS permission denied on `./run`**: Run `chmod +x run` to make the script executable.
- **macOS `python` not found**: Use `python3` instead, or run `./run` which already uses `python3`.
- **PowerShell `run` not recognized**: Use `.\run <command>` — PowerShell requires the explicit `./` prefix for local scripts.
- **Cost tracking DB errors on Windows (`All connection attempts failed`)**: LiteLLM's DB health watchdog uses `os.kill(pid, 0)` to check whether the Prisma query-engine process is alive. On Windows, signal 0 equals `CTRL_C_EVENT`, so this call actually **terminates** the engine instead of probing it. `run setup` and `run start` automatically patch the affected function in the installed litellm package with a safe Windows API call (`OpenProcess`). If you see these errors after upgrading litellm, run `run setup` again to re-apply the patch.
