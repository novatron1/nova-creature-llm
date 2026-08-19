"""HTTP controller for Nova's Reliability Pack."""

from __future__ import annotations

import re
from typing import Any, Callable

from nova_foundation import JobError, NovaFoundation
from nova_reliability import ReliabilityError, ReliabilityManager, VaultError


class ReliabilityHttpController:
    def __init__(
        self,
        reliability_provider: Callable[[], ReliabilityManager],
        foundation_provider: Callable[[], NovaFoundation],
        local_management_guard: Callable[[Any], bool],
    ):
        self._reliability_provider = reliability_provider
        self._foundation_provider = foundation_provider
        self._local_management_guard = local_management_guard

    @property
    def reliability(self) -> ReliabilityManager:
        return self._reliability_provider()

    @property
    def foundation(self) -> NovaFoundation:
        return self._foundation_provider()

    def handle_get(self, handler: Any, parsed: Any) -> bool:
        vault_prefix = "/api/reliability/vault/"
        vault_suffix = "/download"
        if parsed.path.startswith(vault_prefix) and parsed.path.endswith(vault_suffix):
            if not self._local_management_guard(handler):
                return True
            vault_id = parsed.path[len(vault_prefix) : -len(vault_suffix)].strip("/")
            selected = self.reliability.get_vault_export(vault_id)
            if selected is None:
                handler._send_json({"ok": False, "error": "Encrypted backup not found."}, status=404)
                return True
            metadata, path = selected
            download_name = re.sub(
                r"[^A-Za-z0-9._-]+",
                "_",
                str(metadata.get("filename") or "nova-backup.novavault"),
            )[:180]
            handler.send_response(200)
            handler.send_header("Content-Type", "application/octet-stream")
            handler.send_header("Content-Length", str(path.stat().st_size))
            handler.send_header(
                "Content-Disposition", f'attachment; filename="{download_name}"'
            )
            handler.send_header("Cache-Control", "no-store")
            handler._send_cors_headers()
            handler.end_headers()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    if not handler._write_bytes(chunk):
                        break
            return True
        if parsed.path == "/api/reliability/status":
            handler._send_json(self.reliability.status())
            return True
        if parsed.path == "/recovery":
            payload = self.reliability.recovery_html().encode("utf-8")
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html; charset=utf-8")
            handler.send_header("Content-Length", str(len(payload)))
            handler.send_header("Cache-Control", "no-store")
            handler.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
            )
            handler._send_cors_headers()
            handler.end_headers()
            handler._write_bytes(payload)
            return True
        return False

    def handle_post(self, handler: Any, parsed: Any) -> bool:
        if parsed.path == "/api/reliability/diagnostics":
            if not self._local_management_guard(handler):
                return True
            handler._read_json_body()
            report = self.reliability.run_diagnostics()
            handler._send_json({"ok": report.get("ok", False), "diagnostics": report})
            return True
        if parsed.path == "/api/reliability/backup":
            if not self._local_management_guard(handler):
                return True
            body = handler._read_json_body()
            try:
                job = self.foundation.jobs.start(
                    "reliability_backup",
                    payload={"reason": str(body.get("reason") or "manual")[:80]},
                )
            except (JobError, TypeError, ValueError) as error:
                handler._send_json({"ok": False, "error": str(error)}, status=400)
                return True
            handler._send_json({"ok": True, "job": job}, status=202)
            return True
        if parsed.path == "/api/reliability/vault":
            if not self._local_management_guard(handler):
                return True
            body = handler._read_json_body()
            backup_id = str(body.get("backup_id") or "").strip()
            passphrase = body.get("passphrase")
            try:
                exported = self.reliability.create_vault_export(
                    backup_id, passphrase
                )
            except (ReliabilityError, VaultError, OSError, TypeError, ValueError) as error:
                handler._send_json({"ok": False, "error": str(error)}, status=400)
                return True
            handler._send_json(
                {
                    "ok": True,
                    "vault": exported,
                    "message": "Encrypted portable backup created. Keep its passphrase somewhere safe; Nova does not save it.",
                },
                status=201,
            )
            return True
        if parsed.path == "/api/reliability/restore":
            if not self._local_management_guard(handler):
                return True
            body = handler._read_json_body()
            if str(body.get("confirm") or "") != "RESTORE":
                handler._send_json(
                    {
                        "ok": False,
                        "error": "Type RESTORE to confirm this protected operation.",
                    },
                    status=400,
                )
                return True
            backup_id = str(body.get("backup_id") or "").strip()
            if self.reliability.get_backup(backup_id) is None:
                handler._send_json({"ok": False, "error": "Backup not found."}, status=404)
                return True
            try:
                job = self.foundation.jobs.start(
                    "reliability_restore", payload={"backup_id": backup_id}
                )
            except (JobError, TypeError, ValueError) as error:
                handler._send_json({"ok": False, "error": str(error)}, status=400)
                return True
            handler._send_json({"ok": True, "job": job}, status=202)
            return True
        return False


__all__ = ["ReliabilityHttpController"]
