#!/usr/bin/env python3
"""Start LiteLLM with workspace-user home environment."""

from __future__ import annotations

import base64
import os
import site
import ssl
import subprocess
import sys
from pathlib import Path

from user_home import apply_user_home_to_env, resolve_workspace_user_home


def _venv_python() -> Path:
    if os.name == "nt":
        return Path("venv") / "Scripts" / "python.exe"
    return Path("venv") / "bin" / "python"


def _ensure_windows_ca_bundle(env: dict[str, str]) -> None:
    """Merge Windows cert store (ROOT + CA) with certifi so httpx/requests trust corporate TLS."""
    if os.name != "nt":
        return
    if env.get("SSL_CERT_FILE") or env.get("REQUESTS_CA_BUNDLE"):
        return

    dest = Path("venv").resolve() / "ca-bundle.pem"
    pem_parts: list[str] = []

    # Include certifi bundle from venv or user site-packages if present
    search_roots = [Path("venv"), Path(site.getusersitepackages())]
    for root in search_roots:
        if not root.exists():
            continue
        certifi_candidates = list(root.glob("**/certifi/cacert.pem"))
        if certifi_candidates:
            try:
                pem_parts.append(certifi_candidates[0].read_text(encoding="utf-8"))
                break
            except OSError:
                pass

    for store in ("ROOT", "CA"):
        try:
            for cert_data, encoding_type, _trust in ssl.enum_certificates(store):
                if encoding_type == "x509_asn":
                    b64 = base64.b64encode(cert_data).decode("ascii")
                    wrapped = "\n".join(b64[i : i + 64] for i in range(0, len(b64), 64))
                    pem_parts.append(
                        f"-----BEGIN CERTIFICATE-----\n{wrapped}\n-----END CERTIFICATE-----"
                    )
        except (AttributeError, OSError):
            pass

    if pem_parts:
        dest.write_text("\n".join(pem_parts) + "\n", encoding="utf-8")
        env["SSL_CERT_FILE"] = str(dest)
        env["REQUESTS_CA_BUNDLE"] = str(dest)


def _ensure_copilot_token(env: dict[str, str], home: Path) -> int:
    """Ensure GitHub Copilot device-code login is completed before starting proxy event loop."""
    token_dir = Path(
        env.get(
            "GITHUB_COPILOT_TOKEN_DIR",
            str(home / ".config" / "litellm" / "github_copilot"),
        )
    )
    token_file = token_dir / env.get("GITHUB_COPILOT_ACCESS_TOKEN_FILE", "access-token")
    if token_file.exists() and token_file.read_text(encoding="utf-8").strip():
        return 0

    print("GitHub Copilot access token not found - starting one-time device login...")
    py = _venv_python()
    return subprocess.call(
        [
            str(py),
            "-c",
            "from litellm.llms.github_copilot.authenticator import Authenticator; Authenticator().get_access_token()",
        ],
        env=env,
    )


def main() -> int:
    py = _venv_python()
    if not py.exists():
        print(f"Python executable not found at {py}")
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

    _ensure_windows_ca_bundle(env)

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

    rc = _ensure_copilot_token(env, home)
    if rc != 0:
        print("ERROR: GitHub Copilot authentication failed.")
        return rc

    no_db = os.environ.get("LITELLM_WITH_DB", "").lower() not in ("1", "true", "yes")
    config = str(Path("copilot-config.yaml").resolve())
    if no_db:
        # Strip database settings so the proxy never tries to connect to Postgres.
        env.pop("DATABASE_URL", None)
        # .env was already loaded above; stop litellm re-reading DATABASE_URL from it.
        env["PYTHON_DOTENV_DISABLED"] = "1"
        db_keys = ("database_url:", "store_model_in_db:", "store_prompts_in_spend_logs:")
        lines = Path(config).read_text(encoding="utf-8").splitlines()
        kept = [l for l in lines if not l.strip().startswith(db_keys)]
        nodb = Path("venv").resolve() / "copilot-config.nodb.yaml"
        nodb.write_text("\n".join(kept) + "\n", encoding="utf-8")
        config = str(nodb)
        print("Running without database (no cost tracking; use --with-db to enable)")

    # Invoke via signed python.exe instead of unsigned litellm.exe wrapper
    # so Windows Defender Application Control (WDAC) does not block execution.
    cmd = [
        str(py),
        "-c",
        "import sys; from litellm import run_server; sys.exit(run_server())",
        "--config",
        config,
        "--host",
        "127.0.0.1",
        "--port",
        "4444",
    ]
    if not no_db:
        # Use db push instead of migrate deploy (our DB was initialized with db push)
        cmd.append("--use_prisma_db_push")
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
