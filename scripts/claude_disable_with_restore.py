#!/usr/bin/env python3
"""Disable Claude proxy settings and restore latest backup if present."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

from user_home import resolve_workspace_user_home


def main() -> int:
    claude_dir = resolve_workspace_user_home() / ".claude"
    settings = claude_dir / "settings.json"

    if settings.exists():
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        proxy_backup = settings.with_name(f"settings.json.proxy_backup.{ts}")
        proxy_backup.write_text(settings.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backed up proxy settings to {proxy_backup}")

    backups = sorted(
        claude_dir.glob("settings.json.backup.*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if backups:
        settings.write_text(backups[0].read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Restored settings from {backups[0]}")
        return 0

    helper = Path(__file__).with_name("claude_disable.py")
    subprocess.check_call([sys.executable, str(helper)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
