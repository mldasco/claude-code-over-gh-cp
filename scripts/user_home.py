#!/usr/bin/env python3
"""Resolve the intended user home for this workspace.

In this repo, commands can run under a service account while the workspace
path is under another user profile. This helper prefers the workspace user
home (e.g., C:\\Users\\mdasco) so tool state is written to the expected
profile.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_workspace_user_home() -> Path:
    override = os.environ.get("CLAUDE_CODE_USER_HOME")
    if override:
        return Path(override).expanduser()

    cwd = Path.cwd().resolve()
    parts = cwd.parts
    for i, part in enumerate(parts[:-1]):
        if part.lower() == "users" and i + 1 < len(parts):
            return Path(parts[0]) / "Users" / parts[i + 1]

    return Path.home()


def apply_user_home_to_env(env: dict[str, str], home: Path) -> dict[str, str]:
    env_out = dict(env)
    home_str = str(home)
    env_out["HOME"] = home_str
    env_out["USERPROFILE"] = home_str
    if os.name == "nt":
        env_out["APPDATA"] = str(home / "AppData" / "Roaming")
        env_out["LOCALAPPDATA"] = str(home / "AppData" / "Local")
    return env_out
