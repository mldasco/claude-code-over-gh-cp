#!/usr/bin/env python3
"""CLI helper — replaces the Makefile.

Usage:
    python scripts/run.py <command>

Commands:
    help             Show this help message
    setup            Create venv, install dependencies, generate .env
    install-claude   Install Claude Code globally via npm
    start            Start the LiteLLM proxy
    stop             Stop the LiteLLM proxy
    test             Test proxy connection
    claude-enable    Configure Claude Code to use the local proxy
    claude-disable   Restore Claude Code to default Anthropic settings
    claude-status    Show current Claude Code configuration and proxy health
    list-models      List all available GitHub Copilot models
    list-models-enabled  List only enabled GitHub Copilot models
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent
ROOT = SCRIPTS.parent


def _python() -> str:
    return sys.executable


def _venv_python() -> Path:
    if sys.platform == "win32":
        return ROOT / "venv" / "Scripts" / "python.exe"
    return ROOT / "venv" / "bin" / "python"


def _run(cmd: list[str], **kwargs) -> int:
    return subprocess.call(cmd, **kwargs)


def _check(cmd: list[str], **kwargs) -> None:
    subprocess.check_call(cmd, **kwargs)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_help() -> int:
    print(__doc__)
    return 0


def cmd_setup() -> int:
    print("Setting up environment...")
    Path(ROOT / "scripts").mkdir(exist_ok=True)
    _check([_python(), "-m", "venv", str(ROOT / "venv")], cwd=ROOT)
    _check([str(_venv_python()), "-m", "pip", "install", "-r", "requirements.txt"], cwd=ROOT)
    env_file = ROOT / ".env"
    if env_file.exists():
        print("[OK] .env file already exists, skipping generation")
    else:
        print("Generating .env file...")
        _check([_python(), "generate_env.py"], cwd=ROOT)
    print("[OK] Setup complete")
    return 0


def cmd_install_claude() -> int:
    npm = shutil.which("npm")
    if not npm:
        print("npm not found. Install Node.js from https://nodejs.org/ then retry.")
        return 1
    print("Installing Claude Code via npm...")
    rc = _run([npm, "install", "-g", "@anthropic-ai/claude-code"])
    if rc == 0:
        print("Claude Code installed successfully.")
        print("Run:  python scripts/run.py claude-enable")
    return rc


def cmd_start() -> int:
    print("Starting LiteLLM proxy...")
    return _run([_python(), str(SCRIPTS / "start_litellm.py")], cwd=ROOT)


def cmd_stop() -> int:
    print("Stopping processes...")
    rc = _run([str(_venv_python()), str(SCRIPTS / "stop_litellm.py")], cwd=ROOT)
    if rc == 0:
        print("[OK] Processes stopped")
    return rc


def cmd_test() -> int:
    print("Testing proxy connection...")
    rc = _run([_python(), str(SCRIPTS / "test_proxy.py")], cwd=ROOT)
    if rc == 0:
        print("\n[OK] Test completed successfully!")
    return rc


def cmd_claude_enable() -> int:
    print("Configuring Claude Code to use local proxy...")
    rc = _run([_python(), str(SCRIPTS / "claude_enable_with_backup.py")], cwd=ROOT)
    if rc == 0:
        print("[OK] Claude Code configured to use local proxy")
        print("[TIP] Run 'python scripts/run.py start' to start the LiteLLM proxy")
    return rc


def cmd_claude_disable() -> int:
    print("Restoring Claude Code to default settings...")
    return _run([_python(), str(SCRIPTS / "claude_disable_with_restore.py")], cwd=ROOT)


def cmd_claude_status() -> int:
    print("Current Claude Code configuration:")
    print("==================================")
    return _run([_python(), str(SCRIPTS / "claude_status.py")], cwd=ROOT)


def cmd_list_models() -> int:
    print("Listing available GitHub Copilot models...")
    return _run([_python(), str(SCRIPTS / "list_copilot_models.py")], cwd=ROOT)


def cmd_list_models_enabled() -> int:
    print("Listing enabled GitHub Copilot models...")
    return _run([_python(), str(SCRIPTS / "list_copilot_models.py"), "--enabled-only"], cwd=ROOT)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

COMMANDS: dict[str, object] = {
    "help": cmd_help,
    "setup": cmd_setup,
    "install-claude": cmd_install_claude,
    "start": cmd_start,
    "stop": cmd_stop,
    "test": cmd_test,
    "claude-enable": cmd_claude_enable,
    "claude-disable": cmd_claude_disable,
    "claude-status": cmd_claude_status,
    "list-models": cmd_list_models,
    "list-models-enabled": cmd_list_models_enabled,
}


def main() -> int:
    if len(sys.argv) < 2:
        return cmd_help()

    name = sys.argv[1].lower()
    fn = COMMANDS.get(name)
    if fn is None:
        print(f"Unknown command: {name}")
        print(f"Available: {', '.join(COMMANDS)}")
        return 1

    return fn()  # type: ignore[call-arg]


if __name__ == "__main__":
    raise SystemExit(main())
