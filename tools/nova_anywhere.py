#!/usr/bin/env python3
"""Start Nova on loopback behind a private Tailscale Serve address."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable
import urllib.request
from urllib.parse import urlparse
import webbrowser


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT / "src"))

from nova_tailscale import NovaTailscaleManager, TailscaleError  # noqa: E402


def _port(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Ports must be between 1 and 65535.") from error
    if not 1 <= parsed <= 65535:
        raise ValueError("Ports must be between 1 and 65535.")
    return parsed


def _safe_private_url(value: Any) -> str:
    parsed = urlparse(str(value or "").strip())
    hostname = str(parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".ts.net")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise TailscaleError("Tailscale did not return a safe private Nova address.")
    return str(value).strip().rstrip("/")


def wait_for_nova(
    url: str,
    process: subprocess.Popen[Any],
    *,
    timeout_seconds: float = 180.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    """Wait a bounded time for Nova health or stop early if its child exits."""

    timeout = max(0.01, float(timeout_seconds))
    deadline = time.monotonic() + timeout
    maximum_attempts = max(1, int(timeout / 0.25) + 1)
    for _attempt in range(maximum_attempts):
        if process.poll() is not None:
            return False
        try:
            with opener(url, timeout=min(2.0, timeout)) as response:
                if 200 <= int(getattr(response, "status", 0)) < 300:
                    return True
        except (OSError, TimeoutError, ValueError):
            pass
        if time.monotonic() >= deadline:
            return False
        sleeper(min(0.25, max(0.0, deadline - time.monotonic())))
    return False


def _stop_child(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        process.kill()
        try:
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass


def run_anywhere(
    root: Path,
    port: int,
    https_port: int,
    *,
    manager_factory: Callable[..., NovaTailscaleManager] = NovaTailscaleManager,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    browser_open: Callable[[str], Any] = webbrowser.open,
    health_opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
    health_timeout_seconds: float = 180.0,
) -> int:
    """Enable private Serve, launch Nova, open Settings, and supervise it."""

    application_root = Path(root).expanduser().resolve()
    nova_port = _port(port)
    private_https_port = _port(https_port)
    if not (application_root / "nova_enhanced_server.py").is_file():
        raise FileNotFoundError("Nova's enhanced server is missing from this folder.")

    manager = manager_factory(nova_port=nova_port, https_port=private_https_port)
    private_status = manager.enable()
    if (
        not private_status.get("serve_enabled")
        or private_status.get("serve_conflict")
    ):
        raise TailscaleError("Tailscale did not confirm Nova's private connection.")
    private_url = _safe_private_url(private_status.get("private_url"))

    child_env = dict(os.environ)
    child_env.update(
        {
            "NOVA_HOST": "127.0.0.1",
            "NOVA_TRUST_TAILSCALE_SERVE": "true",
            "NOVA_TAILSCALE_HTTPS_PORT": str(private_https_port),
        }
    )
    process = popen_factory(
        [sys.executable, "nova_enhanced_server.py", str(nova_port)],
        cwd=str(application_root),
        env=child_env,
    )
    health_url = f"http://127.0.0.1:{nova_port}/healthz"
    if not wait_for_nova(
        health_url,
        process,
        timeout_seconds=health_timeout_seconds,
        opener=health_opener,
        sleeper=sleeper,
    ):
        _stop_child(process)
        print("[ERROR] Nova did not become ready. Check the server message above.")
        return 3

    local_settings = f"http://127.0.0.1:{nova_port}/classic?panel=settings"
    try:
        browser_open(local_settings)
    except Exception:
        pass
    print(f"[READY] Private phone access: {private_url}")
    print("[READY] Keep this PC awake, Nova running, and Tailscale connected.")
    try:
        return int(process.wait())
    except KeyboardInterrupt:
        _stop_child(process)
        return 130


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Nova Anywhere privately.")
    parser.add_argument("--root", default=str(SCRIPT_ROOT))
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--https-port", type=int, default=8443)
    arguments = parser.parse_args()
    try:
        return run_anywhere(
            Path(arguments.root), arguments.port, arguments.https_port
        )
    except (FileNotFoundError, TailscaleError, ValueError) as error:
        print(f"[ERROR] {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
