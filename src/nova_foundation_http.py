"""HTTP boundary for Nova Foundation.

The main Nova server delegates pairing, device management, durable jobs, and
Foundation UI assets to this controller.  The controller deliberately relies on
the handler's small response/body interface so it stays compatible with the
existing server while allowing the feature to evolve and test independently.
"""

from __future__ import annotations

import ipaddress
import io
import os
from pathlib import Path
import re
import socket
import threading
import time
from typing import Any, Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from nova_foundation import JobError, NovaFoundation, PairingError
from nova_proxy_identity import trusted_tailscale_client_key


class PairingAttemptLimiter:
    """In-memory, per-client protection for six-digit pairing codes."""

    def __init__(self, window_seconds: int = 300):
        self.window_seconds = max(30, int(window_seconds))
        self.attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def attempt_limit() -> int:
        try:
            return max(3, min(int(os.environ.get("NOVA_PAIRING_ATTEMPT_LIMIT", "10")), 50))
        except (TypeError, ValueError):
            return 10

    def check(
        self, client_key: Any, *, failed: bool = False, succeeded: bool = False
    ) -> tuple[bool, int]:
        """Return whether another attempt is allowed and a retry delay."""
        now = time.monotonic()
        key = str(client_key or "unknown")[:120]
        with self._lock:
            attempts = [
                attempted_at
                for attempted_at in self.attempts.get(key, [])
                if now - attempted_at < self.window_seconds
            ]
            if succeeded:
                self.attempts.pop(key, None)
                return True, 0
            if failed:
                attempts.append(now)
                self.attempts[key] = attempts
            elif attempts:
                self.attempts[key] = attempts
            allowed = len(attempts) < self.attempt_limit()
            retry_after = (
                max(1, int(self.window_seconds - (now - attempts[0])))
                if attempts and not allowed
                else 0
            )
            return allowed, retry_after


class FoundationHttpController:
    """Pairing, job, authorization, and static-asset HTTP routes."""

    PUBLIC_API_PATHS = {
        "/api/pairing/status",
        "/api/pairing/start",
        "/api/pairing/exchange",
    }
    SUPPORTED_JOB_KINDS = {"full_training_check"}
    UI_ASSETS = {
        "/assets/nova_foundation_ui.css": (
            "assets/nova_foundation_ui.css",
            "text/css; charset=utf-8",
            {},
        ),
        "/assets/nova_foundation_ui.js": (
            "assets/nova_foundation_ui.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_connection_recovery.js": (
            "assets/nova_connection_recovery.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-app.js": (
            "assets/nova_companion/companion-app.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-store.js": (
            "assets/nova_companion/companion-store.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-api.js": (
            "assets/nova_companion/companion-api.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-presence.js": (
            "assets/nova_companion/companion-presence.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-conversation.js": (
            "assets/nova_companion/companion-conversation.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-composer.js": (
            "assets/nova_companion/companion-composer.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-spark.js": (
            "assets/nova_companion/companion-spark.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-senses.js": (
            "assets/nova_companion/companion-senses.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-trust.js": (
            "assets/nova_companion/companion-trust.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-accessibility.js": (
            "assets/nova_companion/companion-accessibility.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-activity.js": (
            "assets/nova_companion/companion-activity.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_companion/companion-shell.css": (
            "assets/nova_companion/companion-shell.css",
            "text/css; charset=utf-8",
            {},
        ),
        "/assets/nova_dream_studio.css": (
            "assets/nova_dream_studio.css",
            "text/css; charset=utf-8",
            {},
        ),
        "/assets/nova_dream_studio.js": (
            "assets/nova_dream_studio.js",
            "application/javascript; charset=utf-8",
            {},
        ),
        "/assets/nova_app_icon.svg": (
            "assets/nova_app_icon.svg",
            "image/svg+xml; charset=utf-8",
            {},
        ),
        "/manifest.webmanifest": (
            "manifest.webmanifest",
            "application/manifest+json; charset=utf-8",
            {},
        ),
        "/service-worker.js": (
            "service-worker.js",
            "application/javascript; charset=utf-8",
            {"Service-Worker-Allowed": "/"},
        ),
        "/offline.html": ("offline.html", "text/html; charset=utf-8", {}),
    }

    def __init__(
        self,
        foundation_provider: Callable[[], NovaFoundation],
        application_root: str | Path,
        remote_phone_url_provider: Callable[[], str | None] | None = None,
    ):
        self._foundation_provider = foundation_provider
        self.application_root = Path(application_root).resolve()
        self._remote_phone_url_provider = remote_phone_url_provider
        self.rate_limiter = PairingAttemptLimiter()
        self._pairing_qr_assets: dict[str, tuple[float, bytes]] = {}
        self._pairing_qr_lock = threading.Lock()

    @property
    def foundation(self) -> NovaFoundation:
        return self._foundation_provider()

    @staticmethod
    def pairing_enabled() -> bool:
        return str(os.environ.get("NOVA_REQUIRE_PAIRING", "auto")).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
            "disabled",
        }

    @staticmethod
    def client_ip(handler: Any) -> str:
        """Return the effective client IP without trusting arbitrary remote peers."""
        tailscale = trusted_tailscale_client_key(handler)
        if tailscale:
            return tailscale
        direct = str((getattr(handler, "client_address", None) or ("",))[0]).split("%", 1)[0]
        headers = getattr(handler, "headers", {})
        cloudflare = str(headers.get("CF-Connecting-IP") or "").strip()
        try:
            direct_is_loopback = ipaddress.ip_address(direct).is_loopback
        except ValueError:
            direct_is_loopback = False
        if direct_is_loopback and cloudflare and headers.get("CF-Ray"):
            try:
                return str(ipaddress.ip_address(cloudflare.split("%", 1)[0]))
            except ValueError:
                pass
        trust_proxy = str(os.environ.get("NOVA_TRUST_PROXY_HEADERS", "false")).strip().lower() in {
            "1", "true", "yes", "on", "enabled",
        }
        if not trust_proxy:
            return direct
        forwarded = str(headers.get("CF-Connecting-IP") or "").strip()
        if not forwarded:
            forwarded = str(headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
        try:
            ipaddress.ip_address(forwarded.split("%", 1)[0])
        except ValueError:
            return direct
        return forwarded.split("%", 1)[0]

    @classmethod
    def client_is_local(cls, handler: Any) -> bool:
        try:
            raw_address = cls.client_ip(handler)
            address = ipaddress.ip_address(raw_address)
            if getattr(address, "ipv4_mapped", None) is not None:
                address = address.ipv4_mapped
            return bool(address.is_loopback)
        except (AttributeError, IndexError, TypeError, ValueError):
            return False

    @staticmethod
    def bearer_token(handler: Any) -> str:
        authorization = str(handler.headers.get("Authorization") or "").strip()
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer":
            return ""
        return token.strip()

    def pairing_required_for_client(self, handler: Any) -> bool:
        if not self.pairing_enabled() or self.client_is_local(handler):
            return False
        return (
            self.foundation.store.validate_device_token(
                self.bearer_token(handler), touch=False
            )
            is None
        )

    def authorize_api(self, handler: Any, parsed_path: str) -> bool:
        if not str(parsed_path).startswith("/api/"):
            return True
        if parsed_path in self.PUBLIC_API_PATHS:
            return True
        if not self.pairing_enabled() or self.client_is_local(handler):
            return True
        device = self.foundation.store.validate_device_token(self.bearer_token(handler))
        if device is None:
            handler._send_json(
                {
                    "ok": False,
                    "error": "This device must be paired with Nova before it can use this API.",
                    "code": "pairing_required",
                    "pairing_required": True,
                },
                status=401,
            )
            return False
        handler._paired_device = device
        return True

    def require_local_management(self, handler: Any) -> bool:
        if self.client_is_local(handler):
            return True
        handler._send_json(
            {
                "ok": False,
                "error": "Pairing and device management can only be changed from Nova's desktop.",
                "code": "local_management_required",
            },
            status=403,
        )
        return False

    def pairing_status_payload(self, handler: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "enabled": self.pairing_enabled(),
            "pairing_required": self.pairing_required_for_client(handler),
            "local_client": self.client_is_local(handler),
            "paired_devices": self.foundation.store.paired_device_count(),
        }

    def handle_get(self, handler: Any, parsed: Any) -> bool:
        if parsed.path.startswith("/api/pairing/qr/") and parsed.path.endswith(".svg"):
            pairing_id = parsed.path[len("/api/pairing/qr/") : -len(".svg")]
            self._send_pairing_qr(handler, pairing_id)
            return True
        asset = self.UI_ASSETS.get(parsed.path)
        if asset is not None:
            self._send_ui_asset(handler, *asset)
            return True
        if parsed.path == "/api/pairing/status":
            handler._send_json(self.pairing_status_payload(handler))
            return True
        if parsed.path == "/api/pairing/devices":
            if not self.require_local_management(handler):
                return True
            handler._send_json(
                {
                    "ok": True,
                    "devices": self.foundation.store.list_paired_devices(
                        include_revoked=False
                    ),
                }
            )
            return True
        if parsed.path == "/api/jobs":
            query = parse_qs(parsed.query or "")
            try:
                limit = int((query.get("limit") or ["25"])[0])
            except (TypeError, ValueError):
                limit = 25
            handler._send_json(
                {"ok": True, "jobs": self.foundation.store.list_jobs(limit=limit)}
            )
            return True
        if parsed.path.startswith("/api/jobs/"):
            job_id = unquote(parsed.path[len("/api/jobs/") :]).strip("/")
            if not job_id or "/" in job_id:
                handler._send_json({"ok": False, "error": "Job not found."}, status=404)
                return True
            job = self.foundation.store.get_job(job_id)
            if job is None:
                handler._send_json({"ok": False, "error": "Job not found."}, status=404)
                return True
            handler._send_json({"ok": True, "job": job})
            return True
        return False

    def handle_post(self, handler: Any, parsed: Any) -> bool:
        if parsed.path == "/api/pairing/start":
            if not self.require_local_management(handler):
                return True
            body = handler._read_json_body()
            try:
                ttl_seconds = int(body.get("ttl_seconds") or 300)
            except (TypeError, ValueError):
                ttl_seconds = 300
            session = self.foundation.store.create_pairing_session(
                ttl_seconds=ttl_seconds
            )
            phone_url, lan_accessible, connection_kind = self._phone_base_url(handler)
            pairing_url = (
                phone_url.rstrip("/") + "/?pair=" + quote(session["code"])
                if phone_url and lan_accessible
                else None
            )
            qr_url = None
            if pairing_url:
                qr_payload = self._create_qr_svg(pairing_url)
                if qr_payload:
                    self._store_pairing_qr(
                        session["session_id"], qr_payload, session["ttl_seconds"]
                    )
                    qr_url = f"/api/pairing/qr/{session['session_id']}.svg"
            handler._send_json(
                {
                    "ok": True,
                    "pairing": session,
                    "phone_url": phone_url,
                    "pairing_url": pairing_url,
                    "qr_url": qr_url,
                    "lan_accessible": lan_accessible,
                    "connection_kind": connection_kind,
                },
                status=201,
            )
            return True
        if parsed.path == "/api/pairing/exchange":
            body = handler._read_json_body()
            client_key = self.client_ip(handler) or "unknown"
            allowed, retry_after = self.rate_limiter.check(client_key)
            if not allowed:
                handler._send_json(
                    {
                        "ok": False,
                        "error": "Too many incorrect pairing attempts. Wait before trying again.",
                        "code": "pairing_rate_limited",
                        "retry_after_seconds": retry_after,
                    },
                    status=429,
                )
                return True
            try:
                result = self.foundation.store.exchange_pairing_code(
                    body.get("code", ""),
                    body.get("device_name", "Nova device"),
                    user_agent=handler.headers.get("User-Agent"),
                )
            except PairingError as error:
                self.rate_limiter.check(client_key, failed=True)
                handler._send_json({"ok": False, "error": str(error)}, status=400)
                return True
            self.rate_limiter.check(client_key, succeeded=True)
            handler._send_json({"ok": True, **result}, status=201)
            return True
        if parsed.path == "/api/pairing/revoke":
            if not self.require_local_management(handler):
                return True
            body = handler._read_json_body()
            device_id = str(body.get("device_id") or "").strip()
            if not device_id:
                handler._send_json(
                    {"ok": False, "error": "device_id is required."}, status=400
                )
                return True
            revoked = self.foundation.store.revoke_device(device_id)
            handler._send_json(
                {"ok": revoked, "revoked": revoked},
                status=200 if revoked else 404,
            )
            return True
        if parsed.path == "/api/pairing/scopes":
            if not self.require_local_management(handler):
                return True
            body = handler._read_json_body()
            device_id = str(body.get("device_id") or "").strip()
            if not device_id:
                handler._send_json(
                    {"ok": False, "error": "device_id is required."}, status=400
                )
                return True
            try:
                scopes = self.foundation.store.set_device_scopes(
                    device_id, body.get("scopes")
                )
            except PairingError as error:
                handler._send_json({"ok": False, "error": str(error)}, status=400)
                return True
            handler._send_json(
                {
                    "ok": True,
                    "device_id": device_id,
                    "scopes": scopes,
                }
            )
            return True
        if parsed.path == "/api/jobs/start":
            body = handler._read_json_body()
            kind = str(body.get("kind") or "").strip()
            if kind not in self.SUPPORTED_JOB_KINDS:
                handler._send_json(
                    {"ok": False, "error": "Unsupported background job."}, status=400
                )
                return True
            try:
                job = self.foundation.jobs.start(
                    kind, payload=body.get("payload") or {}
                )
            except (JobError, TypeError, ValueError) as error:
                handler._send_json({"ok": False, "error": str(error)}, status=400)
                return True
            handler._send_json({"ok": True, "job": job}, status=202)
            return True
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
            job_id = unquote(
                parsed.path[len("/api/jobs/") : -len("/cancel")]
            ).strip("/")
            if not job_id or "/" in job_id:
                handler._send_json({"ok": False, "error": "Job not found."}, status=404)
                return True
            try:
                job = self.foundation.jobs.cancel(job_id)
            except JobError as error:
                handler._send_json({"ok": False, "error": str(error)}, status=404)
                return True
            handler._send_json({"ok": True, "job": job})
            return True
        return False

    def _remote_phone_url(self) -> str | None:
        if self._remote_phone_url_provider is None:
            return None
        try:
            configured = str(self._remote_phone_url_provider() or "").strip().rstrip("/")
            parsed = urlparse(configured)
        except (TypeError, ValueError):
            return None
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.casefold().endswith(".ts.net")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            return None
        return configured

    def _phone_base_url(self, handler: Any) -> tuple[str | None, bool, str]:
        remote_url = self._remote_phone_url()
        if remote_url:
            return remote_url, True, "tailscale"

        configured = str(os.environ.get("NOVA_PUBLIC_URL") or "").strip().rstrip("/")
        if configured:
            try:
                parsed = urlparse(configured)
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    return configured, True, "configured"
            except ValueError:
                pass

        try:
            server_host = str(handler.server.server_address[0])
            server_port = int(handler.server.server_address[1])
            bound_address = ipaddress.ip_address(server_host.split("%", 1)[0])
            lan_accessible = server_host in {"0.0.0.0", "::"} or not bound_address.is_loopback
        except (AttributeError, IndexError, TypeError, ValueError):
            return None, False, "unavailable"
        if not lan_accessible:
            return None, False, "unavailable"

        request_host = str(handler.headers.get("Host") or "").strip()
        if re.fullmatch(r"[A-Za-z0-9.\-\[\]:]+", request_host):
            try:
                parsed_request = urlparse("http://" + request_host)
                if parsed_request.hostname:
                    request_address = ipaddress.ip_address(
                        parsed_request.hostname.split("%", 1)[0]
                    )
                    if not request_address.is_loopback and not request_address.is_unspecified:
                        return "http://" + request_host, True, "lan"
            except (TypeError, ValueError):
                pass

        lan_ip = self._discover_lan_ip()
        if not lan_ip:
            return None, False, "unavailable"
        return f"http://{lan_ip}:{server_port}", True, "lan"

    @staticmethod
    def _discover_lan_ip() -> str | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                connection.connect(("8.8.8.8", 80))
                candidate = connection.getsockname()[0]
                address = ipaddress.ip_address(candidate)
                if not address.is_loopback and not address.is_unspecified:
                    return candidate
        except OSError:
            pass
        try:
            for candidate in socket.gethostbyname_ex(socket.gethostname())[2]:
                address = ipaddress.ip_address(candidate)
                if address.version == 4 and not address.is_loopback and not address.is_unspecified:
                    return candidate
        except (OSError, ValueError):
            pass
        return None

    @staticmethod
    def _create_qr_svg(value: str) -> bytes | None:
        try:
            import qrcode
            import qrcode.image.svg

            image = qrcode.make(
                value,
                image_factory=qrcode.image.svg.SvgPathImage,
                border=2,
                box_size=6,
            )
            output = io.BytesIO()
            image.save(output)
            return output.getvalue()
        except Exception:
            return None

    def _store_pairing_qr(self, pairing_id: str, payload: bytes, ttl_seconds: int) -> None:
        now = time.monotonic()
        with self._pairing_qr_lock:
            self._pairing_qr_assets = {
                key: value
                for key, value in self._pairing_qr_assets.items()
                if value[0] > now
            }
            self._pairing_qr_assets[str(pairing_id)] = (
                now + max(30, min(int(ttl_seconds), 1800)),
                payload,
            )

    def _send_pairing_qr(self, handler: Any, pairing_id: str) -> None:
        if not re.fullmatch(r"[a-fA-F0-9]{32}", str(pairing_id or "")):
            handler._send_json({"ok": False, "error": "Pairing QR not found."}, status=404)
            return
        now = time.monotonic()
        with self._pairing_qr_lock:
            stored = self._pairing_qr_assets.get(pairing_id)
            if stored and stored[0] <= now:
                self._pairing_qr_assets.pop(pairing_id, None)
                stored = None
        if not stored:
            handler._send_json({"ok": False, "error": "Pairing QR expired."}, status=404)
            return
        payload = stored[1]
        handler.send_response(200)
        handler.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Cache-Control", "no-store")
        handler._send_cors_headers()
        handler.end_headers()
        handler._write_bytes(payload)

    def _send_ui_asset(
        self,
        handler: Any,
        relative_path: str,
        content_type: str,
        extra_headers: dict[str, str],
    ) -> None:
        path = (self.application_root / relative_path).resolve()
        try:
            path.relative_to(self.application_root)
        except ValueError:
            handler._send_json({"ok": False, "error": "Asset not found."}, status=404)
            return
        if not path.is_file():
            handler._send_json({"ok": False, "error": "Asset not found."}, status=404)
            return
        payload = path.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Cache-Control", "no-cache")
        for name, value in extra_headers.items():
            handler.send_header(name, value)
        handler._send_cors_headers()
        handler.end_headers()
        handler._write_bytes(payload)


__all__ = ["FoundationHttpController", "PairingAttemptLimiter"]
