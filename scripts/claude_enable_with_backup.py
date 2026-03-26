#!/usr/bin/env python3
"""Enable Claude proxy settings with backup handling."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

from user_home import resolve_workspace_user_home


def read_master_key(env_path: Path) -> str:
    if not env_path.exists():
        raise FileNotFoundError(".env file not found. Run 'run setup' first.")

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("LITELLM_MASTER_KEY="):
            return line.split("=", 1)[1].strip().strip('"')

    raise ValueError("LITELLM_MASTER_KEY not found in .env")


def main() -> int:
    env_path = Path(".env")
    master_key = read_master_key(env_path)

    settings = resolve_workspace_user_home() / ".claude" / "settings.json"
    if settings.exists():
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = settings.with_name(f"settings.json.backup.{ts}")
        backup.write_text(settings.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backed up existing settings to {backup}")

    helper = Path(__file__).with_name("claude_enable.py")
    subprocess.check_call([sys.executable, str(helper), master_key])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        raise SystemExit(1)
