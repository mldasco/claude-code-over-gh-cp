#!/usr/bin/env python3
"""List GitHub Copilot chat models in local model-config YAML format."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from urllib.request import Request, urlopen

import yaml

from user_home import resolve_workspace_user_home

CLAUDE_MODEL_ALIASES = {
    "claude-opus-4.8": "claude-opus-4-8",
    "claude-opus-5.5": "claude-opus-5-5",
    "claude-sonnet-5.5": "claude-sonnet-5-5",
    "claude-haiku-4.5": "claude-haiku-4-5",
    "claude-haiku-5.5": "claude-haiku-5-5",
}


def read_token(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def refresh_config(config_path: Path, models: list[dict]) -> list[str]:
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else "model_list:\n"
    config = yaml.safe_load(text)
    if not isinstance(config, dict):
        raise ValueError(f"No model_list sequence found in {config_path}")
    if config.get("model_list") is None:
        config["model_list"] = []
    if not isinstance(config["model_list"], list):
        raise ValueError(f"No model_list sequence found in {config_path}")

    configured_models = {
        params.get("model")
        for entry in config["model_list"]
        if isinstance(entry, dict)
        for params in [entry.get("litellm_params") or {}]
        if isinstance(params, dict)
    }
    additions = []
    for model in models:
        capabilities = model.get("capabilities") or {}
        policy = model.get("policy") or {}
        model_id = model.get("id")
        backend_model = f"github_copilot/{model_id}" if model_id else ""
        if (
            capabilities.get("type") != "chat"
            or (policy.get("state") or "enabled") != "enabled"
            or not model_id
            or backend_model in configured_models
        ):
            continue
        additions.append(model)
        configured_models.add(backend_model)

    if not additions:
        print("No new enabled chat models to add.")
        return []

    lines = text.splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if line.strip() == "model_list:"),
        None,
    )
    if header_index is None:
        raise ValueError(f"Could not locate model_list in {config_path}")

    block_end = next(
        (
            index
            for index in range(header_index + 1, len(lines))
            if lines[index].strip()
            and not lines[index].lstrip().startswith("#")
            and not lines[index][0].isspace()
        ),
        len(lines),
    )
    last_content = next(
        (
            index
            for index in range(block_end - 1, header_index, -1)
            if lines[index].strip() and not lines[index].lstrip().startswith("#")
        ),
        header_index,
    )

    additions_text = []
    for model in additions:
        model_id = model["id"]
        capabilities = model.get("capabilities") or {}
        limits = capabilities.get("limits") or {}
        name = model.get("name", "unknown")
        vendor = model.get("vendor", "unknown")
        max_output = limits.get("max_output_tokens", "unknown")
        max_context = limits.get("max_context_window_tokens", "unknown")
        model_name = CLAUDE_MODEL_ALIASES.get(model_id, model_id)
        additions_text.extend(
            [
            f"  - model_name: {json.dumps(model_name)}",
                "    litellm_params:",
                f"      model: {json.dumps(f'github_copilot/{model_id}')}",
                '      extra_headers: {"editor-version": "vscode/1.121.0", "copilot-integration-id": "vscode-chat"}',
                f"    # {name} ({vendor}) - enabled",
                f"    # Max tokens: {max_output}, Context: {max_context}",
            ]
        )

    lines[last_content + 1:last_content + 1] = additions_text
    updated_text = "\n".join(lines) + "\n"
    yaml.safe_load(updated_text)
    config_path.write_text(updated_text, encoding="utf-8")
    added_ids = [model["id"] for model in additions]
    print(f"Added {len(added_ids)} model(s) to {config_path}:")
    for model_id in added_ids:
        print(f"  {model_id}")
    return added_ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enabled-only", action="store_true")
    parser.add_argument("--refresh-config", action="store_true")
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

    try:
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except OSError as exc:
        print(f"Could not fetch GitHub Copilot models: {exc}")
        return 1

    models = payload.get("data", [])

    if args.refresh_config:
        try:
            refresh_config(
                Path(__file__).resolve().parent.parent / "copilot-models.local.yaml",
                models,
            )
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"Could not update copilot-models.local.yaml: {exc}")
            return 1
        return 0

    print("# GitHub Copilot Models Available")
    print(f"# Generated on {dt.datetime.now().isoformat(sep=' ', timespec='seconds')}")
    print("# Usage: Copy desired entries to copilot-models.local.yaml")
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
    print("# 1. Copy desired model entries to copilot-models.local.yaml")
    print("# 2. Restart LiteLLM: run stop && run start")
    print("# 3. Test with: run test")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
