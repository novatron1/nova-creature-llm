"""Safe, non-destructive Nova installation diagnostics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import sys
from typing import Any


def check_path(name: str, path: str | Path, *, required: bool) -> dict[str, Any]:
    target = Path(path).expanduser()
    exists = target.exists()
    if not exists:
        return {
            "name": str(name),
            "kind": "path",
            "status": "missing" if required else "optional_missing",
            "required": bool(required),
        }
    return {
        "name": str(name),
        "kind": "path",
        "status": "ok",
        "required": bool(required),
        "type": "directory" if target.is_dir() else "file",
        "writable": bool(os.access(target, os.W_OK)),
    }


def check_port(name: str, host: str, port: int, *, required: bool) -> dict[str, Any]:
    item = {
        "name": str(name),
        "kind": "port",
        "status": "unreachable",
        "required": bool(required),
        "host": str(host),
        "port": int(port),
    }
    try:
        with socket.create_connection((str(host), int(port)), timeout=0.4):
            item["status"] = "ok"
    except (OSError, ValueError):
        item["status"] = "unreachable"
    return item


def check_command(name: str, command: str, *, required: bool) -> dict[str, Any]:
    found = shutil.which(str(command))
    return {
        "name": str(name),
        "kind": "command",
        "status": "ok" if found else ("missing" if required else "optional_missing"),
        "required": bool(required),
    }


def build_report(*, root: str | Path, checks: list[dict[str, Any]]) -> dict[str, Any]:
    safe_checks = [dict(item) for item in checks]
    required_failures = [
        item
        for item in safe_checks
        if item.get("required") and item.get("status") != "ok"
    ]
    return {
        "schema_version": "1.0",
        "ok": not required_failures,
        "root": str(Path(root).expanduser()),
        "checks": safe_checks,
        "repairable": bool(required_failures),
        "privacy": {
            "prompt_content_stored": False,
            "secrets_read": False,
            "model_weights_modified": False,
        },
    }


def default_report(root: str | Path, *, port: int = 3000) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    checks = [
        check_path("Nova workspace", base, required=True),
        check_path("Nova configuration", base / ".nova_llm_config", required=False),
        check_path("Nova server", base / "nova_enhanced_server.py", required=True),
        check_command("Python", Path(sys.executable).name, required=True),
        check_command("FFmpeg", "ffmpeg", required=False),
        check_port("Nova local gateway", "127.0.0.1", port, required=False),
    ]
    return build_report(root=base, checks=checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run safe Nova installation checks.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args(argv)
    report = default_report(args.root, port=args.port)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
