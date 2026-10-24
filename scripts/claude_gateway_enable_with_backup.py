#!/usr/bin/env python3
"""Enable Claude Code Transurban AI Gateway settings with backup handling.

Resolves the personal gateway key (sk-...) from, in priority order:
  1. the first command-line argument
  2. the GATEWAY_KEY environment variable
  3. a GATEWAY_KEY=... line in .env
  4. an interactive prompt

Backs up any existing ~/.claude/settings.json before switching, so
'run claude-disable' can restore it.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

from user_home import resolve_workspace_user_home


def read_env_value(env_path: Path, name: str) -> str | None:
    if not env_path.exists():
        return None
    prefix = f"{name}="
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(prefix):
            val = line.split("=", 1)[1].strip().strip('"')
            if val:
                return val
    return None


def resolve_key(argv: list[str]) -> str:
    if len(argv) > 1 and argv[1].strip():
        return argv[1].strip()

    env_key = os.environ.get("GATEWAY_KEY", "").strip()
    if env_key:
        return env_key

    file_key = read_env_value(Path(".env"), "GATEWAY_KEY")
    if file_key:
        return file_key

    try:
        entered = input("Enter your Transurban AI Gateway personal key (sk-...): ").strip()
    except EOFError:
        entered = ""
    if entered:
        return entered

    raise ValueError(
        "No gateway key provided. Pass it as an argument, set GATEWAY_KEY, "
        "or add GATEWAY_KEY=sk-... to .env. Request a key via the "
        "'Code Assisted Development' MS Teams channel."
    )


def main(argv: list[str]) -> int:
    key = resolve_key(argv)
    if not key.startswith("sk-"):
        print("[WARN] Gateway keys normally start with 'sk-'; continuing anyway.")

    settings = resolve_workspace_user_home() / ".claude" / "settings.json"
    if settings.exists():
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = settings.with_name(f"settings.json.backup.{ts}")
        backup.write_text(settings.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backed up existing settings to {backup}")

    helper = Path(__file__).with_name("claude_gateway_enable.py")
    subprocess.check_call([sys.executable, str(helper), key])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except ValueError as exc:
        print(str(exc))
        raise SystemExit(1)
