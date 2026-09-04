"""Local-only HTTP boundary for Nova desktop integration."""

from __future__ import annotations

from typing import Any, Callable

from nova_desktop import DesktopError, NovaDesktopManager
from nova_tailscale import TailscaleError


class DesktopHttpController:
    def __init__(
        self,
        desktop_provider: Callable[[], NovaDesktopManager],
        local_management_guard: Callable[[Any], bool],
    ):
        self._desktop_provider = desktop_provider
        self._local_management_guard = local_management_guard

    @property
    def desktop(self) -> NovaDesktopManager:
        return self._desktop_provider()

    def handle_get(self, handler: Any, parsed: Any) -> bool:
        if parsed.path != "/api/desktop/status":
            return False
        if not self._local_management_guard(handler):
            return True
        handler._send_json(self.desktop.status())
        return True

    def handle_post(self, handler: Any, parsed: Any) -> bool:
        if parsed.path not in {
            "/api/desktop/autostart",
            "/api/desktop/remote-access",
        }:
            return False
        if not self._local_management_guard(handler):
            return True
        body = handler._read_json_body()
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            handler._send_json(
                {"ok": False, "error": "enabled must be true or false."}, status=400
            )
            return True
        try:
            result = (
                self.desktop.set_remote_access(enabled)
                if parsed.path == "/api/desktop/remote-access"
                else self.desktop.set_autostart(enabled)
            )
        except (DesktopError, TailscaleError, OSError, ValueError) as error:
            handler._send_json({"ok": False, "error": str(error)}, status=400)
            return True
        handler._send_json(result)
        return True


__all__ = ["DesktopHttpController"]
