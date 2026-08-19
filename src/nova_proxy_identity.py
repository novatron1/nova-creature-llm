"""Trusted reverse-proxy identity helpers with privacy-safe client keys."""

from __future__ import annotations

import hashlib
import ipaddress
import os
from typing import Any, Mapping


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def trusted_tailscale_client_key(
    handler: Any,
    *,
    enabled: bool | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Return an opaque key only for explicitly trusted loopback Serve traffic."""
    source = os.environ if env is None else env
    allowed = (
        str(source.get("NOVA_TRUST_TAILSCALE_SERVE", "false")).strip().lower()
        in _TRUE_VALUES
        if enabled is None
        else bool(enabled)
    )
    if not allowed:
        return None

    direct = str((getattr(handler, "client_address", None) or ("",))[0]).split(
        "%", 1
    )[0]
    try:
        if not ipaddress.ip_address(direct).is_loopback:
            return None
    except ValueError:
        return None

    headers = getattr(handler, "headers", {})
    login = str(headers.get("Tailscale-User-Login") or "").strip()
    if (
        not login
        or len(login) > 320
        or any(ord(character) < 32 for character in login)
    ):
        return None

    digest = hashlib.sha256(login.encode("utf-8")).hexdigest()[:24]
    return "tailscale:" + digest


__all__ = ["trusted_tailscale_client_key"]
