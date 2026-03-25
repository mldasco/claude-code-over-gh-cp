#!/usr/bin/env python3
"""Stop running litellm processes in a cross-platform way."""

from __future__ import annotations

import os
import sys


try:
    import psutil
except ImportError:
    print("psutil not installed in the selected Python environment")
    print("Run make setup and then retry")
    raise SystemExit(1)


def main() -> int:
    stopped = 0
    current_pid = os.getpid()
    target_pids: set[int] = set()

    # Prefer stopping processes bound to the LiteLLM default port.
    try:
        for conn in psutil.net_connections(kind="inet"):
            laddr = conn.laddr
            pid = conn.pid
            if not laddr or pid is None:
                continue
            if getattr(laddr, "port", None) == 4444 and pid != current_pid:
                target_pids.add(pid)
    except (psutil.AccessDenied, RuntimeError):
        pass

    for pid in sorted(target_pids):
        try:
            psutil.Process(pid).kill()
            stopped += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if stopped > 0:
        print(f"Stopped {stopped} litellm process(es)")
        return 0

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = proc.info.get("pid")
            if pid == current_pid:
                continue

            name = (proc.info.get("name") or "").lower()
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()

            if "litellm" not in cmdline:
                continue
            if "stop_litellm.py" in cmdline:
                continue
            if name.startswith("make") or name.startswith("mingw32-make"):
                continue

            proc.kill()
            stopped += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if stopped == 0:
        print("No litellm processes found")
    else:
        print(f"Stopped {stopped} litellm process(es)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
