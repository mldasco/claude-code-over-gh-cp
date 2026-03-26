#!/usr/bin/env python3
"""List GitHub Copilot chat models in copilot-config YAML format."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from urllib.request import Request, urlopen

from user_home import resolve_workspace_user_home


def read_token(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enabled-only", action="store_true")
    args = parser.parse_args()

    token_path = (
        resolve_workspace_user_home()
        / ".config"
        / "litellm"
        / "github_copilot"
        / "access-token"
    )
    token = read_token(token_path)
    if not token:
        print(f"GitHub Copilot token not found at {token_path}")
        print("Run 'run start' first to authenticate with GitHub")
        return 1

    req = Request(
        "https://api.githubcopilot.com/models",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )

    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))

    models = payload.get("data", [])

    print("# GitHub Copilot Models Available")
    print(f"# Generated on {dt.datetime.now().isoformat(sep=' ', timespec='seconds')}")
    print("# Usage: Copy the desired models to your copilot-config.yaml")
    print("")
    if args.enabled_only:
        print("# Showing only enabled models")
    else:
        print("# Showing all models (enabled and unconfigured)")
    print("")
    print("model_list:")

    for model in models:
        caps = model.get("capabilities") or {}
        if caps.get("type") != "chat":
            continue

        policy = model.get("policy") or {}
        state = policy.get("state") or "enabled"
        if args.enabled_only and state != "enabled":
            continue

        model_id = model.get("id", "")
        name = model.get("name", "unknown")
        vendor = model.get("vendor", "unknown")
        limits = caps.get("limits") or {}
        max_out = limits.get("max_output_tokens", "unknown")
        max_ctx = limits.get("max_context_window_tokens", "unknown")

        print(f"  - model_name: {model_id}")
        print("    litellm_params:")
        print(f"      model: github_copilot/{model_id}")
        print(
            "      extra_headers: {\"Editor-Version\": \"vscode/1.85.1\", \"Copilot-Integration-Id\": \"vscode-chat\"}"
        )
        print(f"    # {name} ({vendor}) - {state}")
        print(f"    # Max tokens: {max_out}, Context: {max_ctx}")

    print("")
    print("# To use these models:")
    print("# 1. Copy desired model entries to your copilot-config.yaml")
    print("# 2. Restart LiteLLM: run stop && run start")
    print("# 3. Test with: run test")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
