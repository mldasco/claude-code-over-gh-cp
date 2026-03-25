#!/usr/bin/env python3
"""Send a test chat completion request to the local LiteLLM proxy."""

import json
from pathlib import Path
from urllib.request import Request, urlopen


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
    key = read_master_key(Path(".env"))
    if not key:
        raise SystemExit("LITELLM_MASTER_KEY not found in .env")

    payload = json.dumps(
        {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
        }
    ).encode("utf-8")

    req = Request(
        "http://localhost:4444/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )

    with urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
