#!/usr/bin/env python3
"""Fast, read-only smoke check for a running Nova server."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def fetch(base_url: str, path: str) -> tuple[int, str, bytes]:
    request = Request(urljoin(base_url.rstrip("/") + "/", path.lstrip("/")))
    with urlopen(request, timeout=15) as response:
        return response.status, response.headers.get_content_type(), response.read()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a running Nova app without changing data.")
    parser.add_argument("--url", default="http://127.0.0.1:3000", help="Nova base URL")
    args = parser.parse_args()
    checks: list[str] = []

    try:
        status, content_type, payload = fetch(args.url, "/healthz")
        health = json.loads(payload)
        require(status == 200 and content_type == "application/json", "Health endpoint is not healthy JSON.")
        require(health.get("ok") is True, "Nova health check reported a failure.")
        require(str(health.get("version") or "").startswith("2026."), "Nova version is missing from health.")
        checks.append("health")

        _, _, payload = fetch(args.url, "/status")
        app_status = json.loads(payload)
        require(app_status.get("ok") is True, "Nova status did not report healthy.")
        checks.append("status")

        _, _, payload = fetch(args.url, "/api/reliability/status")
        reliability = json.loads(payload)
        require(reliability.get("ok") is True, "Reliability status failed.")
        require("diagnostics" in reliability and "backups" in reliability, "Reliability details are incomplete.")
        require("encryption_available" in reliability and "vault_exports" in reliability, "Encrypted backup status is incomplete.")
        checks.append("reliability")

        _, _, payload = fetch(args.url, "/api/desktop/status")
        desktop = json.loads(payload)
        require(desktop.get("ok") is True, "Desktop app status failed.")
        require("autostart_enabled" in desktop and "autostart_available" in desktop, "Desktop startup controls are incomplete.")
        checks.append("desktop controls")

        _, content_type, payload = fetch(args.url, "/assets/nova_foundation_ui.js")
        require(content_type == "application/javascript", "Foundation JavaScript has the wrong content type.")
        require(
            b"loadReliabilityStatus" in payload
            and b"applyPairingLink" in payload
            and b"installNovaApp" in payload
            and b"submitEncryptedBackupVault" in payload,
            "Foundation JavaScript is incomplete.",
        )
        checks.append("foundation script")

        _, content_type, payload = fetch(args.url, "/assets/nova_foundation_ui.css")
        require(content_type == "text/css", "Foundation styles have the wrong content type.")
        require(
            b".reliability-check" in payload
            and b".pairing-qr-wrap" in payload
            and b".nova-vault-dialog" in payload,
            "Foundation styles are incomplete.",
        )
        checks.append("foundation styles")

        _, content_type, payload = fetch(args.url, "/manifest.webmanifest")
        manifest = json.loads(payload)
        require(content_type == "application/manifest+json", "App manifest has the wrong content type.")
        require(manifest.get("display") == "standalone" and manifest.get("icons"), "App manifest is incomplete.")
        checks.append("installable app")

        _, content_type, payload = fetch(args.url, "/service-worker.js")
        require(content_type == "application/javascript", "Offline app worker has the wrong content type.")
        require(b"url.pathname.startsWith('/api/')" in payload, "Offline app worker could cache private API data.")
        checks.append("offline shell")

        _, content_type, payload = fetch(args.url, "/recovery")
        require(content_type == "text/html" and b"Nova Recovery" in payload, "Recovery screen is unavailable.")
        checks.append("recovery screen")
    except (HTTPError, URLError, OSError, ValueError, RuntimeError) as error:
        print(f"NOVA SMOKE CHECK FAILED: {error}", file=sys.stderr)
        return 1

    print(f"NOVA SMOKE CHECK PASSED: {', '.join(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
