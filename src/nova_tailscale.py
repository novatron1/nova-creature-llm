"""Private Tailscale Serve management for Nova's loopback web application."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable


CommandRunner = Callable[[list[str], float], subprocess.CompletedProcess[str]]


class TailscaleError(RuntimeError):
    """Nova could not safely inspect or update its private Serve mapping."""


def _default_runner(
    arguments: list[str], timeout: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _discover_tailscale(explicit: str | Path | None) -> str | None:
    if explicit is not None:
        value = str(explicit).strip()
        return value or None
    discovered = shutil.which("tailscale") or shutil.which("tailscale.exe")
    if discovered:
        return discovered
    candidates = []
    program_files = str(os.environ.get("ProgramFiles") or "").strip()
    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if program_files:
        candidates.append(Path(program_files) / "Tailscale" / "tailscale.exe")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Tailscale" / "tailscale.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


class NovaTailscaleManager:
    """Own one private HTTPS Serve mapping without disturbing other mappings."""

    def __init__(
        self,
        nova_port: int = 3000,
        https_port: int = 8443,
        *,
        executable: str | Path | None = None,
        command_runner: CommandRunner | None = None,
    ):
        self.executable = _discover_tailscale(executable)
        self.https_port = self._validate_port(https_port)
        self.nova_port = self._validate_port(nova_port)
        self._runner = command_runner or _default_runner

    @staticmethod
    def _validate_port(port: int) -> int:
        try:
            value = int(port)
        except (TypeError, ValueError) as error:
            raise ValueError("Tailscale ports must be between 1 and 65535.") from error
        if not 1 <= value <= 65535:
            raise ValueError("Tailscale ports must be between 1 and 65535.")
        return value

    @property
    def expected_proxy(self) -> str:
        return f"http://127.0.0.1:{self.nova_port}"

    def set_nova_port(self, port: int) -> None:
        self.nova_port = self._validate_port(port)

    def _arguments(self, *parts: str) -> list[str]:
        if not self.executable:
            raise TailscaleError("Tailscale is not installed on this PC.")
        return [self.executable, *parts]

    def _run(self, *parts: str) -> subprocess.CompletedProcess[str]:
        try:
            result = self._runner(self._arguments(*parts), 10.0)
        except (OSError, subprocess.SubprocessError) as error:
            raise TailscaleError("Tailscale could not update the private connection.") from error
        if result.returncode != 0:
            raise TailscaleError("Tailscale could not update the private connection.")
        return result

    def _run_json(self, *parts: str) -> dict[str, Any]:
        result = self._run(*parts)
        try:
            payload = json.loads(result.stdout or "{}")
        except (TypeError, ValueError) as error:
            raise TailscaleError("Tailscale returned an unreadable status.") from error
        if not isinstance(payload, dict):
            raise TailscaleError("Tailscale returned an unreadable status.")
        return payload

    def _base_status(self) -> dict[str, Any]:
        return {
            "ok": False,
            "installed": bool(self.executable),
            "connected": False,
            "backend_state": "Unavailable",
            "serve_enabled": False,
            "serve_conflict": False,
            "private_url": None,
            "nova_port": self.nova_port,
            "https_port": self.https_port,
            "reason": "tailscale_not_installed",
            "message": "Install Tailscale on this PC to enable private phone access.",
        }

    def status(self) -> dict[str, Any]:
        status = self._base_status()
        if not self.executable:
            return status
        try:
            network = self._run_json("status", "--json")
        except TailscaleError:
            status.update(
                {
                    "reason": "command_failed",
                    "message": "Tailscale status is unavailable on this PC.",
                }
            )
            return status

        backend_state = str(network.get("BackendState") or "Unavailable")[:64]
        self_status = network.get("Self") if isinstance(network.get("Self"), dict) else {}
        connected = backend_state.casefold() == "running" and bool(
            self_status.get("Online", True)
        )
        status.update(
            {
                "backend_state": backend_state,
                "connected": connected,
                "reason": "tailscale_disconnected",
                "message": "Open Tailscale on this PC and sign in.",
            }
        )
        if not connected:
            return status

        dns_name = str(self_status.get("DNSName") or "").strip().rstrip(".")
        if not dns_name or not dns_name.casefold().endswith(".ts.net"):
            status.update(
                {
                    "reason": "https_name_unavailable",
                    "message": "Tailscale HTTPS is not ready for this PC.",
                }
            )
            return status
        port_suffix = "" if self.https_port == 443 else f":{self.https_port}"
        status["private_url"] = f"https://{dns_name}{port_suffix}"

        try:
            serve = self._run_json("serve", "status", "--json")
        except TailscaleError:
            status.update(
                {
                    "reason": "command_failed",
                    "message": "Tailscale Serve status is unavailable on this PC.",
                }
            )
            return status

        service_key = f"{dns_name}:{self.https_port}"
        web = serve.get("Web") if isinstance(serve.get("Web"), dict) else {}
        web_entry = web.get(service_key) if isinstance(web.get(service_key), dict) else {}
        handlers = (
            web_entry.get("Handlers")
            if isinstance(web_entry.get("Handlers"), dict)
            else {}
        )
        root_handler = handlers.get("/") if isinstance(handlers.get("/"), dict) else {}
        actual_proxy = str(root_handler.get("Proxy") or "").strip().rstrip("/")
        funnel = (
            serve.get("AllowFunnel")
            if isinstance(serve.get("AllowFunnel"), dict)
            else {}
        )
        funnel_enabled = bool(funnel.get(service_key))
        owned = actual_proxy == self.expected_proxy and not funnel_enabled
        conflict = bool(actual_proxy and actual_proxy != self.expected_proxy) or funnel_enabled

        if funnel_enabled:
            status.update(
                {
                    "serve_conflict": True,
                    "reason": "https_port_public",
                    "message": (
                        f"Tailscale HTTPS port {self.https_port} has public Funnel enabled."
                    ),
                }
            )
        elif conflict:
            status.update(
                {
                    "serve_conflict": True,
                    "reason": "https_port_in_use",
                    "message": (
                        f"Tailscale HTTPS port {self.https_port} is used by another service."
                    ),
                }
            )
        elif owned:
            status.update(
                {
                    "ok": True,
                    "serve_enabled": True,
                    "reason": "ready",
                    "message": "Private phone access is ready.",
                }
            )
        else:
            status.update(
                {
                    "ok": True,
                    "reason": "serve_not_configured",
                    "message": "Tailscale is ready for private Nova phone access.",
                }
            )
        return status

    def enable(self) -> dict[str, Any]:
        before = self.status()
        if not before["installed"]:
            raise TailscaleError("Tailscale is not installed on this PC.")
        if not before["connected"]:
            raise TailscaleError("Open Tailscale on this PC and sign in.")
        if before["serve_conflict"]:
            if before["reason"] == "https_port_public":
                raise TailscaleError(
                    f"Tailscale HTTPS port {self.https_port} has public Funnel enabled."
                )
            raise TailscaleError(
                f"Tailscale HTTPS port {self.https_port} is already in use."
            )
        if before["serve_enabled"]:
            return before

        self._run(
            "serve",
            "--bg",
            "--yes",
            f"--https={self.https_port}",
            self.expected_proxy,
        )
        after = self.status()
        if not after["serve_enabled"] or after["serve_conflict"]:
            raise TailscaleError("Tailscale did not confirm Nova's private connection.")
        return after

    def disable(self) -> dict[str, Any]:
        before = self.status()
        if before["serve_conflict"]:
            raise TailscaleError(
                f"Nova does not own Tailscale HTTPS port {self.https_port}."
            )
        if not before["serve_enabled"]:
            return before
        self._run("serve", f"--https={self.https_port}", "off")
        after = self.status()
        if after["serve_enabled"] or after["serve_conflict"]:
            raise TailscaleError("Tailscale did not remove Nova's private connection.")
        return after


__all__ = ["NovaTailscaleManager", "TailscaleError"]
