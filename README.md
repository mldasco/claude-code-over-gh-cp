# Claude Code over GitHub Copilot

## Overview

Routes Claude Code through the GitHub Copilot API instead of Anthropic's servers, using a local LiteLLM proxy as a translation layer. No company data leaves to Anthropic — all traffic goes through our existing GitHub Copilot agreement.

**References:**
- [Claude Code LLM Gateway](https://docs.anthropic.com/en/docs/claude-code/llm-gateway)
- [LiteLLM GitHub Copilot Provider](https://docs.litellm.ai/docs/providers/github_copilot)

## Prerequisites

| Dependency | Minimum version | Install |
|---|---|---|
| **Python** | 3.13+ | [python.org/downloads](https://www.python.org/downloads/) or `brew install python` on macOS |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) or `brew install node` on macOS — includes `npm` |
| **Visual Studio Code (Windows)** | 1.94+ | [code.visualstudio.com](https://code.visualstudio.com/) — enable **Add to PATH** during installation so `code` works in a terminal |
| **Claude Code for VS Code (Windows)** | Latest compatible version | Install extension **Anthropic.claude-code** in local VS Code; `run install-claude` / `run setup` install it if missing |
| **GitHub Copilot** | Active subscription | Required for API access |

On Windows, VS Code and its Claude Code extension are required: setup uses the extension's bundled `claude.exe`, not a global npm installation. Node.js/npm remain needed for the existing Prisma cost-tracking tooling and for Claude installation on macOS/Linux.

> **macOS note:** Xcode Command Line Tools (`xcode-select --install`) provide `python3` and `git`. Alternatively install Python via [Homebrew](https://brew.sh).

### Verify prerequisites

```bash
python3 --version   # should be 3.13+  (use 'python' on Windows)
node --version       # should be 18+
npm --version
```

On Windows, also check `code --version`. After installing VS Code, reopen your terminal if `code` is not found.

## Quick Start

The root launchers dispatch commands to the Python runner in `scripts/run.py` and use the project virtual environment when available:

| Shell | Command style |
|---|---|
| macOS / Linux (Bash/Zsh) | `./run <command>` |
| Windows Command Prompt | `run <command>` |

> **macOS tip:** If `./run` gives a permission error after cloning, run `chmod +x run` once.

The steps below show the command without a prefix — add the appropriate one for your shell.

### 1. Install / configure Claude Code
```
run install-claude
```

**Windows:** Required even if an npm/native Claude installation already exists. This command:
- Requires VS Code's `code` command and installs **Claude Code for VS Code** (`Anthropic.claude-code`) if missing.
- Locates the installed extension using `code --locate-extension anthropic.claude-code`, without hard-coding its version or architecture.
- Copies the bundled `resources\native-binary\claude.exe` to `claude.exe` in the extension root.
- Prepends the extension root to your persistent **user PATH**, preserving unrelated entries and removing stale Claude extension version entries from the same extensions directory. No admin rights are needed.

The resulting location is `%USERPROFILE%\.vscode\extensions\anthropic.claude-code-<version>-<platform>\claude.exe`: the root executable is an exact copy of the bundled native executable, and that root directory is first in user PATH. The extension version and platform suffix depend on your installation.

Restart terminals and VS Code after setup so they pick up the updated PATH. If they still inherit the old PATH, sign out of Windows and back in. In a new PowerShell terminal, verify:
```powershell
where.exe claude
claude --version
```
The first match should be the extension-root `claude.exe`, not an old npm shim or standalone installation. An earlier **system PATH** entry can still take precedence over user PATH; resolve that conflict through your normal workstation administration process.

**macOS / Linux:** Uses the existing global npm installation (`npm install -g @anthropic-ai/claude-code`); VS Code is not required.

### 2. Initial Setup
```
run setup
```
On Windows, also performs the Claude extension copy/PATH configuration from step 1 before installing Python dependencies, so step 1 can be skipped when running `run setup`.

Windows dependencies are installed into the workspace user's `%APPDATA%\Python\Python313\site-packages` (the version follows the Python interpreter). Setup removes existing dependencies from the venv's `Lib\site-packages`, preserving only pip and `roaming_user_site.pth`. The venv provides the interpreter; roaming provides application packages. Run `run setup` again to migrate an existing installation. This user package directory is shared with other projects using the same Python version, and setup upgrades its dependencies. Application Control policy still applies; contact your administrator if a native dependency remains blocked.

Creates a Python virtual environment, installs dependencies, generates API keys in `.env`, and, with `--with-db`, **automatically sets up cost tracking**:
- Authenticates with GitHub Copilot when needed and adds newly available enabled chat models to the ignored `copilot-models.local.yaml`; this does not start the proxy
- **With `--with-db`, Windows**: downloads portable PostgreSQL (~350 MB, no admin required) into `postgres/`
- **With `--with-db`, macOS**: starts your Homebrew PostgreSQL if available
- **With `--with-db` but no PostgreSQL found**: setup completes without cost tracking — run `run cost-tracking-init` later
- **Default is no database**: `run setup` and `run start` skip PostgreSQL entirely (no cost tracking or Admin UI). Pass `--with-db` to both (or set `LITELLM_WITH_DB=1`) to enable PostgreSQL-backed cost tracking.

### 3. Configure Claude Code
```
run claude-enable
```
Backs up existing Claude settings and configures Claude Code to use `http://localhost:4444`.

### 4. Start the Proxy
> **Note:** If Copilot authentication was not completed during setup, startup will prompt for GitHub device authentication.
```
run start
```
On Windows, startup requires the pip-only venv layout and verifies that Pydantic Core and LiteLLM import successfully before stopping any existing proxy. If the venv still contains local dependencies, startup asks you to run setup instead of silently using a mixed installation.

### 5. Test the Connection
```
run test
```

### 6. Start Claude Code in your project
```
claude
```

## Available Models

The proxy exposes these Anthropic models (configured in the ignored `copilot-models.local.yaml`):

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
| `run install-claude` | Windows: install/find the VS Code extension, copy its bundled CLI to the extension root, and refresh user PATH; macOS/Linux: install via npm |
| `run claude-status` | Show current Claude settings and proxy health |
| `run claude-disable` | Restore Claude Code to default Anthropic servers |
| `run stop` | Stop the LiteLLM proxy |
| `run list-models` | List all available GitHub Copilot models |
| `run list-models-enabled` | List only enabled models |
| `run refresh-models` | Add newly available enabled models to the ignored local model config and restart LiteLLM |
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

- **WinGuard blocks `claude.exe` on Windows**: Setup reproduces the extension-root placement used on this workstation; it does not change or disable WinGuard policy. Use only an organization-approved VS Code/Claude extension installation. If execution is still blocked, ask IT/security to approve the executable/location rather than disabling protection.
- **Claude extension updated or removed**: VS Code uses versioned extension directories. Re-run `run install-claude` (or `run setup`) after an update to copy the current bundled executable and replace the old extension PATH entry, then restart terminals/VS Code. If the extension was removed, the command reinstalls it. A running Claude process may lock the destination executable; close Claude and retry if copying fails.
- **`claude` still resolves to an old install**: Run `where.exe claude` in a fresh terminal. The extension root must be the first match. Restart VS Code or sign out/in if PATH is stale; check for an earlier system PATH entry if the old install still wins.
- **First run authentication**: `run start` will prompt for GitHub device auth — complete it in the browser.
- **Connection errors**: Run `run test` to verify the proxy is reachable, and `run claude-status` to check settings.
- **SSL certificate errors during `run cost-tracking-init`**: Prisma CLI is a Node.js binary. On Windows, this tool automatically exports the Windows trusted root store (including corporate CA certs from IT policy) and passes it to Node.js via `NODE_EXTRA_CA_CERTS`. If you still see SSL errors, set `NODE_EXTRA_CA_CERTS` manually:
  ```powershell
  $env:NODE_EXTRA_CA_CERTS = "C:\path\to\ca-bundle.pem"
  .\run.cmd cost-tracking-init --postgres-url URL
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
- **Wrong model name**: Run `run list-models-enabled` to see valid model IDs, then update `copilot-models.local.yaml` or run `run refresh-models`.
- **Reset everything**: `run claude-disable` → `run claude-enable`.
- **macOS permission denied on `./run`**: Run `chmod +x run` to make the script executable.
- **macOS `python` not found**: Use `python3` instead, or run `./run` which already uses `python3`.
- **Cost tracking DB errors on Windows (`All connection attempts failed`)**: LiteLLM's DB health watchdog uses `os.kill(pid, 0)` to check whether the Prisma query-engine process is alive. On Windows, signal 0 equals `CTRL_C_EVENT`, so this call actually **terminates** the engine instead of probing it. `run setup` and `run start` automatically patch the affected function in the installed litellm package with a safe Windows API call (`OpenProcess`). If you see these errors after upgrading litellm, run `run setup` again to re-apply the patch.
