"""Reversible desktop integration for Nova Creature."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Any


STARTUP_MARKER = "Nova Creature managed startup v1"
STARTUP_FILENAME = "Nova Creature (Managed).cmd"


class DesktopError(RuntimeError):
    """A desktop integration action could not be completed safely."""


class NovaDesktopManager:
    def __init__(
        self,
        application_root: str | Path,
        port: int = 3000,
        *,
        startup_directory: str | Path | None = None,
        platform_name: str | None = None,
        remote_access_manager: Any | None = None,
    ):
        self.root = Path(application_root).expanduser().resolve()
        self.port = int(port)
        self.platform_name = platform_name or sys.platform
        self.remote_access_manager = remote_access_manager
        self._startup_directory_override = (
            Path(startup_directory).expanduser().resolve()
            if startup_directory is not None
            else None
        )

    @property
    def is_windows(self) -> bool:
        return self.platform_name.startswith("win")

    @staticmethod
    def tailscale_management_available() -> bool:
        return str(os.environ.get("NOVA_TRUST_TAILSCALE_SERVE", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "enabled",
        }

    def startup_directory(self) -> Path | None:
        if self._startup_directory_override is not None:
            return self._startup_directory_override
        appdata = str(os.environ.get("APPDATA") or "").strip()
        if not self.is_windows or not appdata:
            return None
        return (
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        ).resolve()

    def startup_file(self) -> Path | None:
        folder = self.startup_directory()
        return folder / STARTUP_FILENAME if folder is not None else None

    def status(self) -> dict[str, Any]:
        startup_file = self.startup_file()
        managed = False
        if startup_file and startup_file.is_file():
            try:
                managed = STARTUP_MARKER in startup_file.read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                managed = False
        remote_access = dict(
            self.remote_access_manager.status()
            if self.remote_access_manager is not None
            else {
                "ok": False,
                "installed": False,
                "connected": False,
                "serve_enabled": False,
                "serve_conflict": False,
                "private_url": None,
                "reason": "unsupported",
                "message": "Private phone access is unavailable on this system.",
            }
        )
        remote_access["management_available"] = self.tailscale_management_available()
        return {
            "ok": True,
            "platform": self.platform_name,
            "windows": self.is_windows,
            "autostart_available": startup_file is not None,
            "autostart_enabled": bool(startup_file and startup_file.is_file() and managed),
            "autostart_conflict": bool(startup_file and startup_file.is_file() and not managed),
            "pwa_supported": True,
            "port": self.port,
            "remote_access": remote_access,
        }

    def set_remote_access(self, enabled: bool) -> dict[str, Any]:
        if self.remote_access_manager is None:
            raise DesktopError("Private phone access is unavailable on this system.")
        if enabled and not self.tailscale_management_available():
            raise DesktopError(
                "Start Nova with the Anywhere launcher before enabling remote phone access."
            )
        return (
            self.remote_access_manager.enable()
            if enabled
            else self.remote_access_manager.disable()
        )

    def set_autostart(self, enabled: bool) -> dict[str, Any]:
        startup_file = self.startup_file()
        if startup_file is None:
            raise DesktopError("Start with Windows is only available on Windows.")
        if enabled:
            launcher = self.root / "tools" / "nova_autostart.py"
            if not launcher.is_file():
                raise DesktopError("Nova's automatic startup helper is missing.")
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            executable = pythonw if pythonw.is_file() else Path(sys.executable)
            command = subprocess.list2cmdline(
                [
                    str(executable),
                    str(launcher),
                    "--root",
                    str(self.root),
                    "--port",
                    str(self.port),
                ]
            )
            startup_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = startup_file.with_suffix(".cmd.tmp")
            temporary.write_text(
                f"@echo off\r\nREM {STARTUP_MARKER}\r\n{command}\r\n",
                encoding="utf-8",
            )
            os.replace(temporary, startup_file)
        elif startup_file.is_file():
            content = startup_file.read_text(encoding="utf-8", errors="replace")
            if STARTUP_MARKER not in content:
                raise DesktopError(
                    "Nova found an unmanaged startup file with the same name and left it unchanged."
                )
            startup_file.unlink()
        result = self.status()
        result["message"] = (
            "Nova will start quietly when you sign in to Windows."
            if result["autostart_enabled"]
            else "Start with Windows is off."
        )
        return result


__all__ = [
    "DesktopError",
    "NovaDesktopManager",
    "STARTUP_FILENAME",
    "STARTUP_MARKER",
]
