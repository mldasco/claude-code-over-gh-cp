#!/usr/bin/env python3
"""Start LiteLLM with workspace-user home environment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from user_home import apply_user_home_to_env, resolve_workspace_user_home


def main() -> int:
    if os.name == "nt":
        litellm_path = Path("venv") / "Scripts" / "litellm.exe"
    else:
        litellm_path = Path("venv") / "bin" / "litellm"

    if not litellm_path.exists():
        print(f"LiteLLM executable not found at {litellm_path}")
        print("Run 'make setup' first")
        return 1

    home = resolve_workspace_user_home()
    env = apply_user_home_to_env(os.environ, home)
    print(f"Using user home: {home}")

    cmd = [str(litellm_path), "--config", "copilot-config.yaml", "--port", "4444"]
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
