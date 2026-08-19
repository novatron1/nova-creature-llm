#!/usr/bin/env python3
"""Quietly start Nova at sign-in unless its local port is already active."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Callable


def port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.4):
            return True
    except OSError:
        return False


def launch_nova(root: Path, port: int) -> subprocess.Popen:
    """Launch one quiet Nova server process and return its live handle."""

    log_dir = root / "artifacts" / "server_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    output = (log_dir / "nova_autostart.out.log").open("ab")
    error = (log_dir / "nova_autostart.err.log").open("ab")
    server = root / "nova_enhanced_server.py"
    command = [sys.executable, "-u", str(server), str(port)]
    options: dict[str, object] = {
        "cwd": str(root),
        "stdin": subprocess.DEVNULL,
        "stdout": output,
        "stderr": error,
        "close_fds": True,
        "env": {**os.environ, "NOVA_PORT": str(port)},
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    try:
        return subprocess.Popen(command, **options)
    finally:
        output.close()
        error.close()


def supervise_nova(
    root: Path,
    port: int,
    *,
    launch_server: Callable[[Path, int], subprocess.Popen] = launch_nova,
    port_checker: Callable[[int], bool] = port_is_open,
    sleeper: Callable[[float], None] = time.sleep,
    stop_requested: Callable[[], bool] = lambda: False,
    restart_delay_seconds: float = 3.0,
    poll_interval_seconds: float = 2.0,
) -> None:
    """Keep Nova available, restarting it whenever the server process exits."""

    process: subprocess.Popen | None = None
    while not stop_requested():
        if process is None:
            if port_checker(port):
                sleeper(poll_interval_seconds)
                continue
            process = launch_server(root, port)

        if process.poll() is None:
            sleeper(poll_interval_seconds)
            continue

        process = None
        if not stop_requested():
            sleeper(restart_delay_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    server = root / "nova_enhanced_server.py"
    if not server.is_file() or not 1 <= args.port <= 65535:
        return 2
    try:
        supervise_nova(root, args.port)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
