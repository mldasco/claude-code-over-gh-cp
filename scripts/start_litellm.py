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
        print("Run 'run setup' first")
        return 1

    home = resolve_workspace_user_home()
    env = apply_user_home_to_env(os.environ, home)
    # Force UTF-8 for Python text streams (fixes UnicodeEncodeError in litellm's
    # banner when stdout is not a UTF-8 console). Do NOT set PYTHONUTF8=1 — on
    # Windows that changes the console code page to CP 65001 which causes the
    # Prisma query-engine subprocess to crash.
    env["PYTHONIOENCODING"] = "utf-8"

    # Add venv/Scripts to PATH so the `prisma` CLI is found for migration checks.
    # Use an absolute path — litellm chdir()s to the schema dir during startup,
    # so relative paths in PATH break.
    venv_scripts = str(Path("venv").resolve() / ("Scripts" if os.name == "nt" else "bin"))
    env["PATH"] = venv_scripts + os.pathsep + env.get("PATH", "")

    # Bypass corporate proxy (e.g. Zscaler) for localhost connections.
    # httpx (used by Prisma's Python client) reads NO_PROXY to skip proxy for
    # local addresses; without this the query engine HTTP calls can be routed
    # through the proxy and fail.
    env["NO_PROXY"] = "localhost,127.0.0.1"
    env["no_proxy"] = "localhost,127.0.0.1"

    print(f"Using user home: {home}")

    # Explicitly load .env into the environment, stripping surrounding quotes.
    # This overrides any shell-level values that may have been set incorrectly
    # (e.g. with quoted values from manual testing), ensuring litellm always
    # sees the correct DATABASE_URL and key values from the file.
    env_file = Path(".env")
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                env[key] = val

    no_db = os.environ.get("LITELLM_WITH_DB", "").lower() not in ("1", "true", "yes")
    config = "copilot-config.yaml"
    if no_db:
        # Strip database settings so the proxy never tries to connect to Postgres.
        env.pop("DATABASE_URL", None)
        # .env was already loaded above; stop litellm re-reading DATABASE_URL from it.
        env["PYTHON_DOTENV_DISABLED"] = "1"
        db_keys = ("database_url:", "store_model_in_db:", "store_prompts_in_spend_logs:")
        lines = Path(config).read_text(encoding="utf-8").splitlines()
        kept = [l for l in lines if not l.strip().startswith(db_keys)]
        nodb = Path("venv") / "copilot-config.nodb.yaml"
        nodb.write_text("\n".join(kept) + "\n", encoding="utf-8")
        config = str(nodb)
        print("Running without database (no cost tracking; use --with-db to enable)")

    cmd = [
        str(litellm_path),
        "--config", config,
        "--host", "127.0.0.1",
        "--port", "4444",
    ]
    if not no_db:
        # Use db push instead of migrate deploy (our DB was initialized with db push)
        cmd.append("--use_prisma_db_push")
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
