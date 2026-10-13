#!/usr/bin/env python3
"""Project command runner.

Usage:
    run <command>
    python scripts/run.py <command>

Commands:
    help             Show this help message
    setup            Create venv, install dependencies, generate .env
    install-claude   Install Claude Code globally via npm
    start            Start the LiteLLM proxy
    stop             Stop the LiteLLM proxy
    test             Test proxy connection
    claude-enable    Configure Claude Code to use the local proxy
    claude-disable   Restore Claude Code to default Anthropic settings
    claude-status    Show current Claude Code configuration and proxy health
    list-models      List all available GitHub Copilot models
    list-models-enabled  List only enabled GitHub Copilot models
    cost-tracking-init [--postgres-url URL]  Set up cost tracking (auto-installs PostgreSQL if needed)
    postgres-init    Explicitly set up local portable PostgreSQL (Windows) or use system (macOS/Linux)
    postgres-start   Start the local portable PostgreSQL instance
    postgres-stop    Stop the local portable PostgreSQL instance
    prisma-init      Run Prisma generate + DB migration

Options:
    --with-db        (setup/start) Use PostgreSQL for cost tracking. By default the proxy
                     runs without a database. Same as setting LITELLM_WITH_DB=1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent
ROOT = SCRIPTS.parent

# ---------------------------------------------------------------------------
# Local (no-admin) PostgreSQL — downloaded once into postgres/ subdirectory
# ---------------------------------------------------------------------------
_LOCAL_PG_DIR = ROOT / "postgres"
_LOCAL_PG_DATA = _LOCAL_PG_DIR / "data"
_LOCAL_PG_BIN = _LOCAL_PG_DIR / "pgsql" / "bin"
_LOCAL_PG_LOG = _LOCAL_PG_DIR / "pg.log"
_LOCAL_PG_PORT = 5433        # non-default avoids conflict with any system Postgres
_LOCAL_PG_USER = "postgres"
_LOCAL_PG_DB = "litellm"
# Portable binary version to download from EnterpriseDB.
# Override with PG_VERSION env var or update here if the download 404s:
#   https://www.enterprisedb.com/download-postgresql-binaries
_LOCAL_PG_VERSION = os.environ.get("PG_VERSION", "17.5")
# Marker written after a successful full cost-tracking initialisation.
# Stored inside venv/ so it's reset whenever the venv is recreated.
_COST_TRACKING_MARKER = ROOT / "venv" / ".cost_tracking_ready"


def _python() -> str:
    return sys.executable


def _base_python() -> str:
    """Return the system (non-venv) Python, even when a venv is active."""
    return getattr(sys, "_base_executable", sys.executable)


def _venv_python() -> Path:
    if sys.platform == "win32":
        return ROOT / "venv" / "Scripts" / "python.exe"
    return ROOT / "venv" / "bin" / "python"


def _run(cmd: list[str], **kwargs) -> int:
    return subprocess.call(cmd, **kwargs)


def _check(cmd: list[str], **kwargs) -> None:
    subprocess.check_call(cmd, **kwargs)


def _find_litellm_schema() -> "Path | None":
    """Return path to LiteLLM's bundled Prisma schema, or None."""
    # Check the venv directly first — works when this script is running under
    # the system Python (e.g. during 'run setup' before the venv is activated).
    if sys.platform == "win32":
        venv_schema = ROOT / "venv" / "Lib" / "site-packages" / "litellm" / "proxy" / "schema.prisma"
        if venv_schema.exists():
            return venv_schema
    else:
        for candidate in sorted(
            (ROOT / "venv" / "lib").glob("python*/site-packages/litellm/proxy/schema.prisma")
        ):
            return candidate
    # Fallback: try importing litellm from the current interpreter.
    try:
        import litellm as _litellm
        schema = Path(_litellm.__file__).parent / "proxy" / "schema.prisma"
        if schema.exists():
            return schema
    except ImportError:
        pass
    return None


def _prisma_bin() -> "Path | None":
    """Return the prisma CLI path inside the venv, or None."""
    if sys.platform == "win32":
        candidates = [
            ROOT / "venv" / "Scripts" / "prisma.exe",
            ROOT / "venv" / "Scripts" / "prisma",
        ]
    else:
        candidates = [ROOT / "venv" / "bin" / "prisma"]
    for p in candidates:
        if p.exists():
            return p
    return None


def _export_windows_ca_bundle() -> "str | None":
    """Export Windows trusted root certs to a PEM file for Node.js SSL.

    Uses Python's ssl.enum_certificates() which reads the Windows cert store
    directly — no PowerShell, no subprocess, no escaping issues.
    """
    import base64
    import ssl

    dest = ROOT / "venv" / "windows-ca-bundle.pem"
    pem_parts = []

    for store in ("ROOT", "CA"):
        try:
            for cert_data, encoding_type, _trust in ssl.enum_certificates(store):
                if encoding_type == "x509_asn":
                    b64 = base64.b64encode(cert_data).decode("ascii")
                    wrapped = "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
                    pem_parts.append(
                        f"-----BEGIN CERTIFICATE-----\n{wrapped}\n-----END CERTIFICATE-----"
                    )
        except (AttributeError, OSError):
            pass

    if not pem_parts:
        return None
    dest.write_text("\n".join(pem_parts) + "\n", encoding="utf-8")
    return str(dest)


def _node_ssl_env() -> dict:
    """Return NODE_EXTRA_CA_CERTS for the Prisma CLI (Node.js) subprocess.

    Priority:
      1. Already-set NODE_EXTRA_CA_CERTS / SSL_CERT_FILE / REQUESTS_CA_BUNDLE
      2. Windows cert store export (includes corporate CA certs from IT policy)
      3. Nothing (Prisma uses its own bundled CA — fine on most machines)
    """
    existing = (
        os.environ.get("NODE_EXTRA_CA_CERTS")
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
    )
    if existing:
        return {"NODE_EXTRA_CA_CERTS": existing}
    if sys.platform == "win32":
        bundle = _export_windows_ca_bundle()
        if bundle:
            return {"NODE_EXTRA_CA_CERTS": bundle}
    return {}


def _local_pg_bin(name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return _LOCAL_PG_BIN / (name + suffix)


def _pg_clear_stale_pid() -> None:
    """Remove postmaster.pid if the recorded PID is no longer alive.

    When postgres processes are force-killed the lock file is left behind.
    pg_ctl status then returns 'server is starting up' and loops until it
    times out; pg_ctl start refuses to start at all. Removing the stale file
    lets pg_ctl behave correctly on the next call.
    """
    pid_file = _LOCAL_PG_DATA / "postmaster.pid"
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text(encoding="utf-8").splitlines()[0].strip())
    except (ValueError, IndexError, OSError):
        return

    alive = False
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if handle:
            alive = True
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            alive = True
        except (ProcessLookupError, PermissionError):
            pass

    if not alive:
        print(f"  Removing stale postgres lock file (PID {pid} is gone)...")
        pid_file.unlink(missing_ok=True)


def _local_pg_is_running() -> bool:
    ctl = _local_pg_bin("pg_ctl")
    if not ctl.exists() or not _LOCAL_PG_DATA.exists():
        return False
    try:
        r = subprocess.run(
            [str(ctl), "status", "-D", str(_LOCAL_PG_DATA)],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0


def _pg_ensure_binaries() -> int:
    """Download and extract the portable PostgreSQL binaries (Windows only)."""
    if _local_pg_bin("pg_ctl").exists():
        return 0

    import ssl
    import urllib.request
    import zipfile

    version = _LOCAL_PG_VERSION
    url = (
        f"https://get.enterprisedb.com/postgresql/"
        f"postgresql-{version}-1-windows-x64-binaries.zip"
    )
    zip_path = _LOCAL_PG_DIR / f"postgresql-{version}-binaries.zip"
    _LOCAL_PG_DIR.mkdir(exist_ok=True)

    if not zip_path.exists():
        print(f"Downloading PostgreSQL {version} binaries (~350 MB)...")
        print(f"  {url}")
        ctx = ssl.create_default_context()
        bundle = _export_windows_ca_bundle()
        if bundle:
            ctx.load_verify_locations(bundle)
        try:
            with urllib.request.urlopen(url, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                with open(zip_path, "wb") as fh:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded * 100 // total
                            print(
                                f"\r  {pct}% ({downloaded // 1_000_000} MB)",
                                end="", flush=True,
                            )
            print()
        except Exception as exc:
            zip_path.unlink(missing_ok=True)
            print(f"\nERROR: Download failed: {exc}")
            print("  If the version is wrong, set PG_VERSION env var and retry:")
            print("    $env:PG_VERSION = '17.7'")
            print("    .\\run postgres-init")
            print("  Or check the latest version at:")
            print("    https://www.enterprisedb.com/download-postgresql-binaries")
            return 1
        print("[OK] Downloaded")
    else:
        print(f"[OK] Using cached download: {zip_path}")

    print("Extracting (may take a minute)...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(_LOCAL_PG_DIR)
    print(f"[OK] Extracted to {_LOCAL_PG_DIR}")
    return 0


def _find_system_postgres() -> "str | None":
    """Return a working postgres URL if a system postgres is already running, else None."""
    import shutil

    pg_isready = shutil.which("pg_isready")
    if not pg_isready:
        return None
    try:
        r = subprocess.run([pg_isready, "-h", "localhost"], capture_output=True, timeout=5)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    # Server is running — ensure the litellm database exists
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "postgres"
    createdb_cmd = shutil.which("createdb")
    if createdb_cmd:
        subprocess.run([createdb_cmd, _LOCAL_PG_DB], capture_output=True)
    return f"postgresql://{user}@localhost/{_LOCAL_PG_DB}"


def _start_brew_postgres() -> "str | None":
    """macOS: start any installed Homebrew PostgreSQL service. Return URL or None."""
    import shutil

    brew = shutil.which("brew")
    if not brew:
        return None
    result = subprocess.run(
        [brew, "services", "list"], capture_output=True, text=True
    )
    pg_services = [
        line.split()[0] for line in result.stdout.splitlines()
        if line.startswith("postgresql")
    ]
    if not pg_services:
        return None
    formula = sorted(pg_services)[-1]  # highest installed version
    print(f"Starting {formula} via Homebrew...")
    subprocess.run([brew, "services", "start", formula], capture_output=True)
    import time
    time.sleep(3)
    return _find_system_postgres()


def _install_portable_pg_windows() -> "str | None":
    """Download, extract, initialize, and start portable PostgreSQL (Windows only)."""
    rc = _pg_ensure_binaries()
    if rc != 0:
        return None
    if not (_LOCAL_PG_DATA / "PG_VERSION").exists():
        print("Initializing PostgreSQL data directory...")
        _LOCAL_PG_DATA.mkdir(parents=True, exist_ok=True)
        rc = _run([
            str(_local_pg_bin("initdb")),
            "-D", str(_LOCAL_PG_DATA),
            "-U", _LOCAL_PG_USER,
            "-E", "UTF8",
            "--auth=trust",
        ])
        if rc != 0:
            return None
        pg_conf = _LOCAL_PG_DATA / "postgresql.conf"
        text = pg_conf.read_text(encoding="utf-8")
        text = text.replace("#port = 5432", f"port = {_LOCAL_PG_PORT}")
        pg_conf.write_text(text, encoding="utf-8")
        print(f"[OK] Initialized at {_LOCAL_PG_DATA} on port {_LOCAL_PG_PORT}")
    else:
        print("[OK] Data directory already initialized")
    if not _local_pg_is_running():
        print("Starting local PostgreSQL...")
        rc = _run([
            str(_local_pg_bin("pg_ctl")),
            "-D", str(_LOCAL_PG_DATA),
            "-l", str(_LOCAL_PG_LOG),
            "start",
        ])
        if rc != 0:
            print(f"ERROR: Failed to start. Check log: {_LOCAL_PG_LOG}")
            return None
        import time
        time.sleep(2)
    result = subprocess.run(
        [str(_local_pg_bin("psql")), "-U", _LOCAL_PG_USER,
         "-p", str(_LOCAL_PG_PORT), "-lqt"],
        capture_output=True, text=True,
    )
    if _LOCAL_PG_DB not in result.stdout:
        print(f"Creating '{_LOCAL_PG_DB}' database...")
        rc = _run([
            str(_local_pg_bin("createdb")),
            "-U", _LOCAL_PG_USER, "-p", str(_LOCAL_PG_PORT), _LOCAL_PG_DB,
        ])
        if rc != 0:
            return None
    db_url = f"postgresql://{_LOCAL_PG_USER}@localhost:{_LOCAL_PG_PORT}/{_LOCAL_PG_DB}"
    print(f"[OK] Local PostgreSQL ready: {db_url}")
    return db_url


def _setup_postgres_and_get_url() -> "str | None":
    """Find, start, or install PostgreSQL. Returns a working connection URL or None."""
    # 1. Local portable install (postgres/ subdir) — any platform
    if _local_pg_bin("pg_ctl").exists() and _LOCAL_PG_DATA.exists():
        if not _local_pg_is_running():
            subprocess.run(
                [str(_local_pg_bin("pg_ctl")), "-D", str(_LOCAL_PG_DATA),
                 "-l", str(_LOCAL_PG_LOG), "start"],
                capture_output=True,
            )
            import time
            time.sleep(2)
        result = subprocess.run(
            [str(_local_pg_bin("psql")), "-U", _LOCAL_PG_USER,
             "-p", str(_LOCAL_PG_PORT), "-lqt"],
            capture_output=True, text=True,
        )
        if _LOCAL_PG_DB not in result.stdout:
            subprocess.run([
                str(_local_pg_bin("createdb")),
                "-U", _LOCAL_PG_USER, "-p", str(_LOCAL_PG_PORT), _LOCAL_PG_DB,
            ], capture_output=True)
        return f"postgresql://{_LOCAL_PG_USER}@localhost:{_LOCAL_PG_PORT}/{_LOCAL_PG_DB}"

    # 2. Already-running system postgres
    url = _find_system_postgres()
    if url:
        return url

    # 3. macOS: try starting a Homebrew postgres service
    if sys.platform == "darwin":
        return _start_brew_postgres()

    # 4. Windows: auto-install portable postgres
    if sys.platform == "win32":
        return _install_portable_pg_windows()

    return None


def _do_cost_tracking_init(postgres_url: str) -> int:
    """Write DATABASE_URL, enable config, and run prisma generate + push."""
    import re

    env_file = ROOT / ".env"
    env_content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    if "DATABASE_URL" in env_content:
        env_content = re.sub(
            r'^DATABASE_URL=.*$',
            f'DATABASE_URL="{postgres_url}"',
            env_content,
            flags=re.MULTILINE,
        )
        env_file.write_text(env_content, encoding="utf-8")
        print("[OK] Updated DATABASE_URL in .env")
    else:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write(f'\nDATABASE_URL="{postgres_url}"\n')
        print("[OK] DATABASE_URL written to .env")

    config_file = ROOT / "copilot-config.yaml"
    config_text = config_file.read_text(encoding="utf-8")
    updated = (
        config_text
        .replace("  # database_url: os.environ/DATABASE_URL",
                 "  database_url: os.environ/DATABASE_URL")
        .replace("  # store_model_in_db: true",
                 "  store_model_in_db: true")
        .replace("  # store_prompts_in_spend_logs: true",
                 "  store_prompts_in_spend_logs: true")
    )
    if updated != config_text:
        config_file.write_text(updated, encoding="utf-8")
        print("[OK] Enabled database settings in copilot-config.yaml")
    else:
        print("[OK] Database settings already enabled in copilot-config.yaml")

    rc = cmd_prisma_init()
    if rc == 0:
        _COST_TRACKING_MARKER.touch()
    return rc


def _apply_litellm_patches() -> None:
    """Apply in-venv patches to litellm that fix Windows-specific bugs.

    Patch: _poll_engine_proc sends CTRL_C_EVENT on Windows
    -------------------------------------------------------
    litellm's DB health watchdog calls ``os.kill(pid, 0)`` to check whether
    the Prisma query-engine process is still alive.  On Unix, signal 0 is a
    harmless "does this process exist?" probe.  On Windows, signal.CTRL_C_EVENT
    equals 0, so ``os.kill(pid, 0)`` sends CTRL+C to the engine's process
    group — which *terminates* the engine within ~1 second of startup, causing
    all subsequent DB queries to fail with "All connection attempts failed".

    The fix replaces the ``os.kill`` call with an OpenProcess-based liveness
    check that is safe on Windows.

    This patch is idempotent (checks for the sentinel string before applying)
    and is re-applied automatically on each ``run setup`` and ``run start`` so
    that it survives a ``pip install --upgrade litellm``.
    """
    # Locate utils.py inside the venv
    if sys.platform == "win32":
        utils_path = ROOT / "venv" / "Lib" / "site-packages" / "litellm" / "proxy" / "utils.py"
    else:
        # On POSIX the path includes the Python version directory
        venv_lib = ROOT / "venv" / "lib"
        candidates = sorted(venv_lib.glob("python*/site-packages/litellm/proxy/utils.py"))
        utils_path = candidates[0] if candidates else None  # type: ignore[assignment]

    if utils_path is None or not utils_path.exists():
        return  # litellm not installed yet

    text = utils_path.read_text(encoding="utf-8")

    # Already patched — nothing to do
    if "_is_process_alive_windows" in text:
        return

    OLD = (
        "    async def _poll_engine_proc(self) -> None:\n"
        '        """poll via os.kill(pid, 0) every 1s.\n'
        "        Only used when BOTH waitpid thread and pidfd are unavailable\n"
        "        (e.g., PID is not our child process and pidfd_open fails)\n"
        '        """\n'
        "        while self._watching_engine and self._engine_pid > 0:\n"
        "            try:\n"
        "                os.kill(self._engine_pid, 0)\n"
    )
    NEW = (
        "    @staticmethod\n"
        "    def _is_process_alive_windows(pid: int) -> bool:\n"
        '        """Check if a process is alive on Windows without sending any signal.\n'
        "\n"
        "        On Windows, os.kill(pid, 0) sends CTRL_C_EVENT (signal 0 == CTRL_C_EVENT)\n"
        "        which terminates the process instead of checking liveness. Use OpenProcess\n"
        "        with SYNCHRONIZE access to check existence safely.\n"
        '        """\n'
        "        import ctypes\n"
        "        SYNCHRONIZE = 0x00100000\n"
        "        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)\n"
        "        if handle == 0:\n"
        "            return False\n"
        "        ctypes.windll.kernel32.CloseHandle(handle)\n"
        "        return True\n"
        "\n"
        "    async def _poll_engine_proc(self) -> None:\n"
        '        """poll via os.kill(pid, 0) every 1s.\n'
        "        Only used when BOTH waitpid thread and pidfd are unavailable\n"
        "        (e.g., PID is not our child process and pidfd_open fails)\n"
        '        """\n'
        "        while self._watching_engine and self._engine_pid > 0:\n"
        "            try:\n"
        "                if sys.platform == \"win32\":\n"
        "                    # os.kill(pid, 0) on Windows sends CTRL_C_EVENT (signal value 0)\n"
        "                    # which actually TERMINATES the process. Use OpenProcess instead.\n"
        "                    if not self._is_process_alive_windows(self._engine_pid):\n"
        "                        raise ProcessLookupError(\n"
        "                            f\"Process {self._engine_pid} not found\"\n"
        "                        )\n"
        "                else:\n"
        "                    os.kill(self._engine_pid, 0)\n"
    )

    if OLD not in text:
        # Pattern not found — litellm version may have changed; skip silently
        print("[WARN] Could not apply litellm Windows patch (pattern not found). "
              "Cost tracking may fail on Windows. "
              "See README Troubleshooting for details.")
        return

    utils_path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("[OK] Applied litellm Windows Prisma engine patch")


def _no_db() -> bool:
    return os.environ.get("LITELLM_WITH_DB", "").lower() not in ("1", "true", "yes")


def _auto_setup_cost_tracking() -> None:
    """Non-fatal: called at the end of setup to configure cost tracking.

    - If already configured and the prisma marker exists, skips.
    - If DATABASE_URL is in .env but prisma hasn't been run, runs prisma only.
    - Otherwise tries to find/install PostgreSQL and sets everything up.
    """
    if _no_db():
        print("[INFO] Skipping PostgreSQL / cost tracking setup (use --with-db to enable)")
        return
    env_file = ROOT / ".env"
    db_configured = (
        env_file.exists() and "DATABASE_URL" in env_file.read_text(encoding="utf-8")
    )
    if db_configured and _COST_TRACKING_MARKER.exists():
        print("[OK] Cost tracking already configured")
        return
    if db_configured:
        # .env has a URL but prisma hasn't been initialised yet
        rc = cmd_prisma_init()
        if rc == 0:
            _COST_TRACKING_MARKER.touch()
        else:
            print("[WARN] Prisma init failed. Run 'run cost-tracking-init' to retry.")
        return

    print("Looking for a PostgreSQL instance for cost tracking...")
    url = _setup_postgres_and_get_url()
    if not url:
        print("[INFO] No PostgreSQL available — skipping cost tracking for now.")
        print("  Run 'run cost-tracking-init' when PostgreSQL is ready.")
        return
    rc = _do_cost_tracking_init(url)
    if rc != 0:
        print("[WARN] Cost tracking setup incomplete. Run 'run cost-tracking-init' to retry.")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_help() -> int:
    print(__doc__)
    return 0


def cmd_setup() -> int:
    vi = sys.version_info
    if vi >= (3, 14):
        print(
            f"ERROR: Python {vi.major}.{vi.minor} is not supported.\n"
            "litellm requires Python >=3.10,<3.14.\n"
            "Install Python 3.12 or 3.13 from https://python.org/downloads/ "
            "and re-run this script with that interpreter, e.g.:\n"
            "  py -3.12 scripts\\run.py setup"
        )
        return 1
    print("Setting up environment...")
    Path(ROOT / "scripts").mkdir(exist_ok=True)
    _check([_base_python(), "-m", "venv", str(ROOT / "venv")], cwd=ROOT)
    _check([str(_venv_python()), "-m", "pip", "install", "-r", "requirements.txt"], cwd=ROOT)
    _apply_litellm_patches()
    env_file = ROOT / ".env"
    if env_file.exists():
        print("[OK] .env file already exists, skipping generation")
    else:
        print("Generating .env file...")
        _check([_python(), "generate_env.py"], cwd=ROOT)
    print("[OK] Setup complete")
    print()
    _auto_setup_cost_tracking()
    return 0


def cmd_install_claude() -> int:
    npm = shutil.which("npm")
    if not npm:
        print("npm not found. Install Node.js from https://nodejs.org/ then retry.")
        return 1
    print("Installing Claude Code via npm...")
    rc = _run([npm, "install", "-g", "@anthropic-ai/claude-code"])
    if rc == 0:
        print("Claude Code installed successfully.")
        print("Run:  run claude-enable")
    return rc


def cmd_start() -> int:
    # Re-apply patches in case litellm was upgraded since setup
    _apply_litellm_patches()
    # Kill any leftover litellm process from a previous run before starting.
    # This prevents port-already-in-use errors and zombie process buildup.
    subprocess.run(
        [str(_venv_python()), str(SCRIPTS / "stop_litellm.py")],
        capture_output=True,
    )
    if _no_db():
        print("[INFO] Starting proxy without PostgreSQL (use --with-db to enable)")
        print("Starting LiteLLM proxy...")
        return _run([_python(), str(SCRIPTS / "start_litellm.py")], cwd=ROOT)
    # Auto-start local PostgreSQL if it was installed by postgres-init
    if _local_pg_bin("pg_ctl").exists() and _LOCAL_PG_DATA.exists():
        # Remove stale PID file left by force-killed postgres (causes pg_ctl to hang).
        _pg_clear_stale_pid()
        if not _local_pg_is_running():
            print("Starting local PostgreSQL...")
            try:
                # On Windows, use CREATE_NO_WINDOW so postgres is not attached to
                # the calling console session and won't be killed when the terminal
                # is closed (e.g. VS Code kill_terminal sends a console close event).
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.run(
                    [str(_local_pg_bin("pg_ctl")), "-D", str(_LOCAL_PG_DATA),
                     "-l", str(_LOCAL_PG_LOG), "start"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                print("[WARN] pg_ctl start timed out — postgres may still be starting.")
    # If cost tracking is configured but prisma hasn't been initialised (e.g. fresh
    # venv after postgres was already set up), run prisma before starting the proxy.
    env_file = ROOT / ".env"
    if (env_file.exists()
            and "DATABASE_URL" in env_file.read_text(encoding="utf-8")
            and not _COST_TRACKING_MARKER.exists()):
        print("Initialising Prisma client for cost tracking...")
        rc = cmd_prisma_init()
        if rc == 0:
            _COST_TRACKING_MARKER.touch()
        else:
            print("[WARN] Prisma init failed — starting proxy without cost tracking.")
    print("Starting LiteLLM proxy...")
    return _run([_python(), str(SCRIPTS / "start_litellm.py")], cwd=ROOT)


def cmd_stop() -> int:
    print("Stopping processes...")
    rc = _run([str(_venv_python()), str(SCRIPTS / "stop_litellm.py")], cwd=ROOT)
    if rc == 0:
        print("[OK] Processes stopped")
    # Also stop local PostgreSQL if running
    if _local_pg_is_running():
        print("Stopping local PostgreSQL...")
        try:
            subprocess.run(
                [str(_local_pg_bin("pg_ctl")), "-D", str(_LOCAL_PG_DATA), "stop"],
                capture_output=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            print("[WARN] pg_ctl stop timed out.")
    return rc


def cmd_test() -> int:
    print("Testing proxy connection...")
    rc = _run([_python(), str(SCRIPTS / "test_proxy.py")], cwd=ROOT)
    if rc == 0:
        print("\n[OK] Test completed successfully!")
    return rc


def cmd_claude_enable() -> int:
    print("Configuring Claude Code to use local proxy...")
    rc = _run([_python(), str(SCRIPTS / "claude_enable_with_backup.py")], cwd=ROOT)
    if rc == 0:
        print("[OK] Claude Code configured to use local proxy")
        print("[TIP] Run 'run start' to start the LiteLLM proxy")
    return rc


def cmd_claude_disable() -> int:
    print("Restoring Claude Code to default settings...")
    return _run([_python(), str(SCRIPTS / "claude_disable_with_restore.py")], cwd=ROOT)


def cmd_claude_status() -> int:
    print("Current Claude Code configuration:")
    print("==================================")
    return _run([_python(), str(SCRIPTS / "claude_status.py")], cwd=ROOT)


def cmd_list_models() -> int:
    print("Listing available GitHub Copilot models...")
    return _run([_python(), str(SCRIPTS / "list_copilot_models.py")], cwd=ROOT)


def cmd_list_models_enabled() -> int:
    print("Listing enabled GitHub Copilot models...")
    return _run([_python(), str(SCRIPTS / "list_copilot_models.py"), "--enabled-only"], cwd=ROOT)


def cmd_cost_tracking_init() -> int:
    """Set up cost tracking (auto-detects or installs PostgreSQL if needed).

    Usage:
        run cost-tracking-init                     # auto-detect/install
        run cost-tracking-init --postgres-url URL  # use a specific DB
    """
    args = sys.argv[2:]
    postgres_url: "str | None" = None

    i = 0
    while i < len(args):
        if args[i] == "--postgres-url" and i + 1 < len(args):
            postgres_url = args[i + 1]
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            print("Usage: run cost-tracking-init [--postgres-url URL]")
            return 1

    if not postgres_url:
        print("Looking for a PostgreSQL instance...")
        postgres_url = _setup_postgres_and_get_url()
        if not postgres_url:
            print("ERROR: Could not find or set up a PostgreSQL instance.")
            print()
            if sys.platform == "darwin":
                print("  Install: brew install postgresql@16")
                print("  Start:   brew services start postgresql@16")
                print("  Retry:   run cost-tracking-init")
            elif sys.platform.startswith("linux"):
                print("  Install: sudo apt install postgresql")
                print("  Start:   sudo systemctl start postgresql")
                print("  Retry:   run cost-tracking-init")
            print("  Or provide a URL directly:")
            print("    run cost-tracking-init --postgres-url postgresql://user:pass@host/db")
            return 1

    return _do_cost_tracking_init(postgres_url)


def cmd_postgres_init() -> int:
    """Set up cost tracking using a local or system PostgreSQL instance.

    Windows: auto-downloads portable PostgreSQL into postgres/ (no admin needed).
    macOS/Linux: uses system PostgreSQL (starts via Homebrew if available).
    """
    if sys.platform == "win32":
        url = _install_portable_pg_windows()
    else:
        url = _setup_postgres_and_get_url()

    if not url:
        if sys.platform == "darwin":
            print("Could not find or start a PostgreSQL instance.")
            print("Install:  brew install postgresql@16")
            print("Start:    brew services start postgresql@16")
            print("Retry:    run postgres-init")
        elif sys.platform.startswith("linux"):
            print("Install: sudo apt install postgresql")
            print("Start:   sudo systemctl start postgresql")
            print("Retry:   run postgres-init")
        return 1

    return _do_cost_tracking_init(url)


def cmd_postgres_start() -> int:
    if not _local_pg_bin("pg_ctl").exists():
        print("Local PostgreSQL not installed. Run: .\\run postgres-init")
        return 1
    if _local_pg_is_running():
        print("[OK] Local PostgreSQL is already running")
        return 0
    print("Starting local PostgreSQL...")
    return _run([
        str(_local_pg_bin("pg_ctl")),
        "-D", str(_LOCAL_PG_DATA),
        "-l", str(_LOCAL_PG_LOG),
        "start",
    ])


def cmd_postgres_stop() -> int:
    if not _local_pg_bin("pg_ctl").exists() or not _local_pg_is_running():
        print("[OK] Local PostgreSQL is not running")
        return 0
    print("Stopping local PostgreSQL...")
    return _run([str(_local_pg_bin("pg_ctl")), "-D", str(_LOCAL_PG_DATA), "stop"])


def _prisma_in_venv() -> bool:
    """True if the prisma package is installed inside the venv."""
    if sys.platform == "win32":
        return (_venv_python().parent.parent / "Lib" / "site-packages" / "prisma").is_dir()
    return bool(list(
        (_venv_python().parent.parent / "lib").glob("python*/site-packages/prisma")
    ))


def cmd_prisma_init() -> int:
    print("Running Prisma generate + migration...")

    # Auto-install prisma if missing.
    # Use a venv path check rather than `import prisma` — the import will fail
    # when this script is running under the system Python (e.g. during setup).
    if not _prisma_in_venv():
        print("  prisma package not found — installing...")
        rc = _run([str(_venv_python()), "-m", "pip", "install", "prisma"])
        if rc != 0:
            print("ERROR: Failed to install prisma. Run 'run setup' to reinstall dependencies.")
            return rc

    prisma = _prisma_bin()
    if prisma is None:
        print("ERROR: prisma CLI not found in venv. Run 'run setup' first.")
        return 1

    schema = _find_litellm_schema()
    if schema is None:
        print("ERROR: LiteLLM schema not found. Run 'run setup' first.")
        return 1
    print(f"  schema: {schema}")

    # Add venv Scripts/bin to PATH so prisma can spawn prisma-client-py
    venv_bin = ROOT / "venv" / ("Scripts" if sys.platform == "win32" else "bin")
    run_env = {**os.environ, **_node_ssl_env()}
    if venv_bin.exists():
        run_env["PATH"] = f"{venv_bin}{os.pathsep}{run_env.get('PATH', '')}"

    rc = _run([str(prisma), "generate", "--schema", str(schema)], env=run_env)
    if rc != 0:
        print("ERROR: prisma generate failed.")
        print("  If you see an SSL certificate error, set NODE_EXTRA_CA_CERTS")
        print("  to your corporate CA bundle, then re-run this command. E.g.:")
        print("    $env:NODE_EXTRA_CA_CERTS = 'C:\\path\\to\\ca-bundle.pem'")
        print("    .\\run cost-tracking-init")
        return rc

    rc = _run([str(prisma), "db", "push", "--schema", str(schema)], env=run_env)
    if rc == 0:
        print("[OK] Database schema initialized")
    return rc


def cmd_generate_key() -> int:
    """Create (or verify) a virtual key with budget limits, store as LITELLM_CLAUDE_KEY in .env.

    The key is what Claude Code uses to authenticate to the proxy, and its
    spend/budget is visible in the admin UI at http://127.0.0.1:4444/ui.

    Requires the proxy to be running (run 'run start' first).
    """
    import json as _json
    import urllib.error
    import urllib.request

    env_path = ROOT / ".env"
    if not env_path.exists():
        print("ERROR: .env not found — run 'run setup' first.")
        return 1

    env_lines = env_path.read_text(encoding="utf-8").splitlines()

    def _read_env(key: str) -> "str | None":
        for ln in env_lines:
            if ln.startswith(f"{key}="):
                return ln.split("=", 1)[1].strip().strip('"')
        return None

    master_key = _read_env("LITELLM_MASTER_KEY")
    if not master_key:
        print("ERROR: LITELLM_MASTER_KEY not found in .env")
        return 1

    base_url = "http://127.0.0.1:4444"
    headers_base = {
        "Authorization": f"Bearer {master_key}",
        "Content-Type": "application/json",
    }

    def _api(method: str, path: str, body: "dict | None" = None) -> "tuple[int, dict]":
        data = _json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            f"{base_url}{path}", data=data, headers=headers_base, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, _json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, {}
        except OSError:
            return 0, {}

    # Check existing key is still valid
    existing = _read_env("LITELLM_CLAUDE_KEY")
    if existing:
        status, info = _api("GET", f"/key/info?key={existing}")
        if status == 200 and info.get("key_name") or info.get("key"):
            budget_info = info.get("info", {})
            spent = budget_info.get("spend", 0)
            limit = budget_info.get("max_budget", "?")
            print(f"[OK] Virtual key already exists: {existing[:24]}...")
            print(f"     Spend: ${spent:.4f} / ${limit}/day")
            print(f"     Admin UI: {base_url}/ui")
            return 0
        print("  Existing key not found on proxy — regenerating...")

    # Proxy reachability check
    status, _ = _api("GET", "/health/liveliness")
    if status == 0:
        print(f"ERROR: Could not reach proxy at {base_url} — is it running?")
        print("  Start it first with: run start")
        return 1

    # Generate new key
    status, resp = _api("POST", "/key/generate", {
        "key_alias": "claude-code",
        "max_budget": 20.0,
        "budget_duration": "1d",
        "models": ["*"],
    })
    if status != 200 or not resp.get("key"):
        print(f"ERROR: /key/generate returned {status}: {resp}")
        return 1

    new_key = resp["key"]

    # Write LITELLM_CLAUDE_KEY into .env (update or append)
    env_text = env_path.read_text(encoding="utf-8")
    if "LITELLM_CLAUDE_KEY=" in env_text:
        new_lines = [
            f"LITELLM_CLAUDE_KEY={new_key}" if ln.startswith("LITELLM_CLAUDE_KEY=") else ln
            for ln in env_text.splitlines()
        ]
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        env_path.write_text(env_text.rstrip() + f"\nLITELLM_CLAUDE_KEY={new_key}\n", encoding="utf-8")

    print(f"[OK] Virtual key created: {new_key[:24]}...")
    print(f"     Budget: $20.00/day  —  resets daily")
    print(f"     Visible in admin UI: {base_url}/ui")
    print("     Run 'run claude-enable' to apply this key to Claude Code.")
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

COMMANDS: dict[str, object] = {
    "help": cmd_help,
    "setup": cmd_setup,
    "install-claude": cmd_install_claude,
    "start": cmd_start,
    "stop": cmd_stop,
    "test": cmd_test,
    "claude-enable": cmd_claude_enable,
    "claude-disable": cmd_claude_disable,
    "claude-status": cmd_claude_status,
    "list-models": cmd_list_models,
    "list-models-enabled": cmd_list_models_enabled,
    "cost-tracking-init": cmd_cost_tracking_init,
    "generate-key": cmd_generate_key,
    "postgres-init": cmd_postgres_init,
    "postgres-start": cmd_postgres_start,
    "postgres-stop": cmd_postgres_stop,
    "prisma-init": cmd_prisma_init,
}


def main() -> int:
    if len(sys.argv) < 2:
        return cmd_help()

    if "--with-db" in sys.argv[2:]:
        os.environ["LITELLM_WITH_DB"] = "1"
        sys.argv.remove("--with-db")
    name = sys.argv[1].lower()
    fn = COMMANDS.get(name)
    if fn is None:
        print(f"Unknown command: {name}")
        print(f"Available: {', '.join(COMMANDS)}")
        return 1

    return fn()  # type: ignore[call-arg]


if __name__ == "__main__":
    raise SystemExit(main())
