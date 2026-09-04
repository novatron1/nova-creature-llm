"""Scoped API clients, key hashing, IP rules, and in-process rate limiting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
from threading import RLock
import time
from typing import Any, Mapping

from .config import GatewayConfig
from .errors import AuthenticationError, PermissionDeniedError, RateLimitError


CLIENT_REGISTRY_VERSION = "1.0"
KEY_ITERATIONS = 240_000
ALL_PERMISSION_SCOPES = frozenset(
    {
        "chat.generate", "chat.stream", "memory.read", "memory.write", "tools.list", "tools.execute",
        "files.read", "files.write", "image.generate", "video.generate", "audio.transcribe",
        "robot.observe", "robot.move", "game.observe", "game.control", "system.execute",
        "admin.providers", "admin.models", "admin.config",
    }
)
LOCAL_SAFE_SCOPES = frozenset(
    {"chat.generate", "chat.stream", "memory.read", "memory.write", "tools.list", "files.read", "admin.models"}
)
ENV_CLIENT_SCOPES = frozenset({"chat.generate", "chat.stream", "tools.list", "admin.models"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_api_key(api_key: str, *, salt: bytes | None = None, iterations: int = KEY_ITERATIONS) -> str:
    if not api_key or len(api_key) < 8:
        raise ValueError("Nova API keys must contain at least 8 characters.")
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", api_key.encode("utf-8"), actual_salt, iterations)
    return f"pbkdf2_sha256${iterations}${actual_salt.hex()}${digest.hex()}"


def verify_api_key(api_key: str, stored_hash: str) -> bool:
    try:
        algorithm, raw_iterations, raw_salt, expected = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hash_api_key(api_key, salt=bytes.fromhex(raw_salt), iterations=int(raw_iterations)).rsplit("$", 1)[-1]
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


@dataclass
class NovaClient:
    client_id: str
    display_name: str
    key_hash: str
    scopes: list[str]
    enabled: bool = True
    created_at: str = field(default_factory=_now)
    last_used_at: str | None = None
    allowed_ips: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CLIENT_REGISTRY_VERSION

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("key_hash", None)
        return data


class NovaClientRegistry:
    """JSON-backed client registry that never persists plaintext keys."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).resolve() if path else None
        self._clients: dict[str, NovaClient] = {}
        self._lock = RLock()
        if self.path and self.path.exists():
            self.reload()

    def reload(self) -> None:
        if not self.path or not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        loaded: dict[str, NovaClient] = {}
        for item in data.get("clients") or []:
            client = NovaClient(**item)
            loaded[client.client_id] = client
        with self._lock:
            self._clients = loaded

    def add_client(
        self,
        client_id: str,
        display_name: str,
        api_key: str,
        scopes: list[str] | set[str],
        *,
        allowed_ips: list[str] | None = None,
        persist: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> NovaClient:
        unknown = set(scopes) - ALL_PERMISSION_SCOPES
        if unknown:
            raise ValueError(f"Unknown Nova permission scopes: {', '.join(sorted(unknown))}")
        client = NovaClient(
            client_id=str(client_id),
            display_name=str(display_name),
            key_hash=hash_api_key(api_key),
            scopes=sorted(set(scopes)),
            allowed_ips=list(allowed_ips or []),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._clients[client.client_id] = client
        if persist:
            self.save()
        return client

    def add_hashed_client(self, client: NovaClient) -> None:
        with self._lock:
            self._clients[client.client_id] = client

    def authenticate(self, api_key: str, client_ip: str) -> NovaClient | None:
        with self._lock:
            clients = list(self._clients.values())
        for client in clients:
            if not client.enabled or not verify_api_key(api_key, client.key_hash):
                continue
            if client.allowed_ips and not any(self._ip_matches(client_ip, rule) for rule in client.allowed_ips):
                continue
            client.last_used_at = _now()
            return client
        return None

    @staticmethod
    def _ip_matches(client_ip: str, rule: str) -> bool:
        try:
            address = ipaddress.ip_address(client_ip)
            if "/" in str(rule):
                return address in ipaddress.ip_network(str(rule), strict=False)
            return address == ipaddress.ip_address(str(rule))
        except ValueError:
            return False

    def list_clients(self) -> list[dict[str, Any]]:
        with self._lock:
            return [client.public_dict() for client in self._clients.values()]

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {"schema_version": CLIENT_REGISTRY_VERSION, "clients": [asdict(item) for item in self._clients.values()]}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = int(limit)
        self.window_seconds = int(window_seconds)
        self._events: dict[str, list[float]] = {}
        self._lock = RLock()

    def check(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = [event for event in self._events.get(key, []) if event > cutoff]
            if len(events) >= self.limit:
                self._events[key] = events
                return False
            events.append(current)
            self._events[key] = events
            return True


@dataclass(frozen=True)
class AuthContext:
    client_id: str
    scopes: frozenset[str]
    local: bool
    authenticated: bool


class NovaAuthenticator:
    def __init__(self, config: GatewayConfig, registry: NovaClientRegistry, *, env: Mapping[str, str] | None = None):
        self.config = config
        self.registry = registry
        self.rate_limiter = SlidingWindowRateLimiter(config.rate_limit_per_minute)
        self._load_environment_keys(env or os.environ)

    def _load_environment_keys(self, env: Mapping[str, str]) -> None:
        for index, api_key in enumerate(str(env.get("NOVA_API_KEYS") or "").split(","), start=1):
            value = api_key.strip()
            if not value:
                continue
            self.registry.add_client(
                f"env-client-{index}", f"Environment client {index}", value, set(ENV_CLIENT_SCOPES),
                persist=False, metadata={"source": "environment"},
            )

    @staticmethod
    def is_local_address(client_ip: str) -> bool:
        try:
            return ipaddress.ip_address(str(client_ip).split("%", 1)[0]).is_loopback
        except ValueError:
            return False

    def authorize(self, client_ip: str, authorization: str | None, required_scope: str | None = None) -> AuthContext:
        local = self.is_local_address(client_ip)
        if not local and not self.config.enable_remote_access:
            raise PermissionDeniedError("Nova remote API access is disabled.")
        scheme, _, token = str(authorization or "").partition(" ")
        client = (
            self.registry.authenticate(token.strip(), client_ip)
            if scheme.lower() == "bearer" and token.strip()
            else None
        )
        if client is not None:
            context = AuthContext(client.client_id, frozenset(client.scopes), local, True)
        elif local and self.config.allow_local_no_auth:
            # Local development is already trusted by explicit configuration.
            # A stale web-app pairing token must not make localhost less usable
            # than the same request with no Authorization header.
            context = AuthContext("local-client", LOCAL_SAFE_SCOPES, True, False)
        else:
            raise AuthenticationError()
        if required_scope and required_scope not in context.scopes:
            raise PermissionDeniedError(f"Client {context.client_id!r} lacks required scope {required_scope!r}.")
        if self.config.rate_limit_enabled and not self.rate_limiter.check(context.client_id):
            raise RateLimitError()
        return context
