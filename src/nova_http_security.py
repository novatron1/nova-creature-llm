"""Shared outbound HTTP confinement for Nova model-control traffic."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Iterable
from urllib.parse import urlsplit
import urllib.request


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Turn every HTTP redirect into an error before a new request is made."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_without_redirects(request, timeout):
    return urllib.request.build_opener(RejectRedirects()).open(request, timeout=timeout)


def exact_host_allowlist(value: str | Iterable[object] | None) -> frozenset[str]:
    if isinstance(value, str):
        values = re.split(r"[,;\s]+", value)
    else:
        values = value or ()
    return frozenset(
        str(host).strip().lower().rstrip(".")
        for host in values
        if str(host).strip()
    )


def worker_address_allowed(address: object) -> bool:
    try:
        parsed = ipaddress.ip_address(str(address).split("%", 1)[0])
    except ValueError:
        return False
    if parsed.is_loopback:
        return True
    if isinstance(parsed, ipaddress.IPv4Address) and parsed in ipaddress.ip_network(
        "100.64.0.0/10"
    ):
        return True
    return bool(
        parsed.is_private
        and not parsed.is_link_local
        and not parsed.is_unspecified
        and not parsed.is_multicast
        and not parsed.is_reserved
    )


def validate_worker_url(
    value: object,
    *,
    allowed_hosts: str | Iterable[object] | None = None,
) -> str:
    """Require HTTP(S) traffic to stay on a private/Tailscale/exact host."""

    endpoint = str(value or "").strip()
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("A valid credential-free HTTP(S) endpoint is required.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as error:
        raise ValueError("A valid credential-free HTTP(S) endpoint is required.") from error
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in exact_host_allowlist(allowed_hosts):
        return endpoint
    try:
        addresses = [str(ipaddress.ip_address(hostname))]
    except ValueError:
        try:
            addresses = [
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname,
                    port,
                    type=socket.SOCK_STREAM,
                )
                if item and len(item) > 4 and item[4]
            ]
        except socket.gaierror:
            addresses = []
    if addresses and all(worker_address_allowed(address) for address in addresses):
        return endpoint
    raise ValueError(
        "Model traffic only allows local, private, Tailscale, or exact server-approved hosts."
    )
