#!/usr/bin/env python3
"""Show current Claude Code settings and local proxy health."""

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from user_home import resolve_workspace_user_home


def read_master_key(env_path: Path) -> str:
    if not env_path.exists():
        return ""

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("LITELLM_MASTER_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def main() -> int:
    settings = resolve_workspace_user_home() / ".claude" / "settings.json"

    if not settings.exists():
        print("No settings file found - using Claude Code defaults")
        print("Status: Using default Anthropic servers")
        return 0

    print(f"Settings file: {settings}")
    print("")

    text = settings.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
        print(json.dumps(parsed, indent=2))
    except Exception:
        print(text)

    print("")
    if "localhost:4444" in text:
        print("Status: Using local proxy")
        key = read_master_key(Path(".env"))
        headers = {}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = Request("http://localhost:4444/health", headers=headers, method="GET")
        try:
            urlopen(req, timeout=3)
            print("Proxy server: Running")
        except HTTPError as exc:
            # 401/403 still means the server is up; it just rejected auth.
            if exc.code in (401, 403):
                print("Proxy server: Running (auth required)")
            else:
                print("Proxy server: Not running (run 'run start')")
        except Exception:
            print("Proxy server: Not running (run 'run start')")
    else:
        print("Status: Using default Anthropic servers")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
