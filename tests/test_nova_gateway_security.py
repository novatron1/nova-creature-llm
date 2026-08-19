from __future__ import annotations

import json
from pathlib import Path
import sys
from threading import RLock

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.auth import (  # noqa: E402
    NovaAuthenticator,
    NovaClientRegistry,
    SlidingWindowRateLimiter,
    hash_api_key,
    verify_api_key,
)
from nova_gateway.config import GatewayConfig  # noqa: E402
from nova_gateway.errors import (  # noqa: E402
    AuthenticationError,
    InvalidRequestError,
    PermissionDeniedError,
    RateLimitError,
    ToolValidationError,
)
from nova_gateway.memory import ExistingNovaMemoryStore  # noqa: E402
from nova_gateway.structured import parse_structured_output, validate_json_schema  # noqa: E402
from nova_gateway.tools import NovaRegisteredTool, NovaToolRegistry  # noqa: E402


def test_paired_remote_device_gets_only_safe_gateway_scopes(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from nova_gateway.http import NovaGatewayHttpController

    config = GatewayConfig(
        enable_remote_access=False,
        allow_local_no_auth=True,
        rate_limit_enabled=False,
        client_registry_path=tmp_path / "clients.json",
    )
    registry = NovaClientRegistry(config.client_registry_path)
    auth = NovaAuthenticator(config, registry, env={})
    controller = NovaGatewayHttpController(SimpleNamespace(), auth, config)
    handler = SimpleNamespace(
        _paired_device={"device_id": "phone-1"},
        client_address=("127.0.0.1", 50000),
        headers={},
    )

    context = controller._authorize(handler, "chat.stream")
    assert context.client_id == "paired-device:phone-1"
    assert context.authenticated is True
    assert context.local is False
    with pytest.raises(PermissionDeniedError, match="robot.move"):
        controller._authorize(handler, "robot.move")
    with pytest.raises(PermissionDeniedError, match="image.generate"):
        controller._authorize(handler, "image.generate")

    handler._paired_device["scopes"] = ["image.generate", "robot.move"]
    media_context = controller._authorize(handler, "image.generate")
    assert "image.generate" in media_context.scopes
    with pytest.raises(PermissionDeniedError, match="robot.move"):
        controller._authorize(handler, "robot.move")


def test_cloudflare_loopback_proxy_is_not_mistaken_for_localhost(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from nova_gateway.http import NovaGatewayHttpController

    config = GatewayConfig(
        enable_remote_access=False,
        allow_local_no_auth=True,
        trust_proxy_headers=False,
        rate_limit_enabled=False,
        client_registry_path=tmp_path / "clients.json",
    )
    auth = NovaAuthenticator(config, NovaClientRegistry(config.client_registry_path), env={})
    controller = NovaGatewayHttpController(SimpleNamespace(), auth, config)
    cloudflare_handler = SimpleNamespace(
        client_address=("127.0.0.1", 50000),
        headers={"CF-Connecting-IP": "203.0.113.42", "CF-Ray": "test-IAD"},
    )
    direct_lan_handler = SimpleNamespace(
        client_address=("192.168.1.20", 50000),
        headers={"CF-Connecting-IP": "127.0.0.1", "CF-Ray": "spoofed"},
    )

    assert controller._client_ip(cloudflare_handler) == "203.0.113.42"
    assert controller.client_is_local(cloudflare_handler) is False
    assert controller._client_ip(direct_lan_handler) == "192.168.1.20"
    assert controller.client_is_local(direct_lan_handler) is False


def test_tailscale_loopback_proxy_is_not_mistaken_for_localhost(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from nova_gateway.http import NovaGatewayHttpController

    config = GatewayConfig(
        enable_remote_access=True,
        allow_local_no_auth=True,
        trust_tailscale_serve=True,
        rate_limit_enabled=False,
        client_registry_path=tmp_path / "clients.json",
    )
    auth = NovaAuthenticator(
        config, NovaClientRegistry(config.client_registry_path), env={}
    )
    controller = NovaGatewayHttpController(SimpleNamespace(), auth, config)
    tailscale_handler = SimpleNamespace(
        client_address=("127.0.0.1", 50000),
        headers={"Tailscale-User-Login": "phone@example.test"},
    )
    spoofed_lan_handler = SimpleNamespace(
        client_address=("192.0.2.44", 50000),
        headers={"Tailscale-User-Login": "phone@example.test"},
    )

    assert controller._client_ip(tailscale_handler).startswith("tailscale:")
    assert controller.client_is_local(tailscale_handler) is False
    assert controller._client_ip(spoofed_lan_handler) == "192.0.2.44"


def test_paired_local_web_app_token_uses_safe_scopes_without_remote_access(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from nova_gateway.http import NovaGatewayHttpController

    config = GatewayConfig(
        enable_remote_access=False,
        allow_local_no_auth=True,
        rate_limit_enabled=False,
        client_registry_path=tmp_path / "clients.json",
    )
    registry = NovaClientRegistry(config.client_registry_path)
    auth = NovaAuthenticator(config, registry, env={})
    controller = NovaGatewayHttpController(SimpleNamespace(), auth, config)
    handler = SimpleNamespace(
        _paired_device={"id": "desktop-browser"},
        _paired_device_local=True,
        client_address=("127.0.0.1", 50000),
        headers={"Authorization": "Bearer nova_foundation_device_token"},
    )

    context = controller._authorize(handler, "chat.generate")

    assert context.client_id == "paired-device:desktop-browser"
    assert context.authenticated is True
    assert context.local is True
    with pytest.raises(PermissionDeniedError, match="system.execute"):
        controller._authorize(handler, "system.execute")


def test_api_keys_are_slow_hashed_and_never_persist_plaintext(tmp_path: Path) -> None:
    key = "nova-test-key-123"
    stored = hash_api_key(key)
    assert key not in stored
    assert verify_api_key(key, stored)
    assert not verify_api_key("wrong-key", stored)

    path = tmp_path / "clients.json"
    registry = NovaClientRegistry(path)
    registry.add_client("phone", "Phone", key, {"chat.generate"})
    raw = path.read_text(encoding="utf-8")
    assert key not in raw
    assert json.loads(raw)["clients"][0]["key_hash"].startswith("pbkdf2_sha256$")
    assert NovaClientRegistry(path).authenticate(key, "192.168.1.20").client_id == "phone"

    cidr_registry = NovaClientRegistry()
    cidr_registry.add_client("lan", "LAN", "nova-lan-key", {"chat.generate"}, allowed_ips=["192.168.1.0/24"], persist=False)
    assert cidr_registry.authenticate("nova-lan-key", "192.168.1.42").client_id == "lan"
    assert cidr_registry.authenticate("nova-lan-key", "10.0.0.2") is None


def test_authentication_enforces_remote_default_keys_scopes_and_rate_limit(tmp_path: Path) -> None:
    config = GatewayConfig(
        enable_remote_access=False,
        allow_local_no_auth=True,
        rate_limit_enabled=True,
        rate_limit_per_minute=1,
        client_registry_path=tmp_path / "clients.json",
    )
    registry = NovaClientRegistry(config.client_registry_path)
    registry.add_client("phone", "Phone", "nova-phone-key", {"chat.generate"})
    auth = NovaAuthenticator(config, registry, env={})

    local = auth.authorize("127.0.0.1", None, "chat.generate")
    assert local.local is True and local.authenticated is False
    with pytest.raises(RateLimitError):
        auth.authorize("127.0.0.1", None, "chat.generate")
    with pytest.raises(PermissionDeniedError, match="remote"):
        auth.authorize("192.168.1.20", "Bearer nova-phone-key", "chat.generate")

    remote_config = GatewayConfig(enable_remote_access=True, allow_local_no_auth=False, rate_limit_enabled=False)
    remote_auth = NovaAuthenticator(remote_config, registry, env={})
    with pytest.raises(AuthenticationError):
        remote_auth.authorize("192.168.1.20", None, "chat.generate")
    remote = remote_auth.authorize("192.168.1.20", "Bearer nova-phone-key", "chat.generate")
    assert remote.client_id == "phone"
    with pytest.raises(PermissionDeniedError, match="chat.stream"):
        remote_auth.authorize("192.168.1.20", "Bearer nova-phone-key", "chat.stream")


def test_local_no_auth_mode_ignores_stale_web_app_token(tmp_path: Path) -> None:
    config = GatewayConfig(
        allow_local_no_auth=True,
        rate_limit_enabled=False,
        client_registry_path=tmp_path / "clients.json",
    )
    auth = NovaAuthenticator(config, NovaClientRegistry(config.client_registry_path), env={})

    context = auth.authorize(
        "127.0.0.1",
        "Bearer nova_stale_paired_device_token",
        "chat.generate",
    )

    assert context.client_id == "local-client"
    assert context.local is True
    assert context.authenticated is False


def test_sliding_window_rate_limiter_expires_old_events() -> None:
    limiter = SlidingWindowRateLimiter(2, window_seconds=60)
    assert limiter.check("client", now=0)
    assert limiter.check("client", now=1)
    assert not limiter.check("client", now=2)
    assert limiter.check("client", now=61)


def test_tool_registry_validates_schema_permissions_and_confirmation() -> None:
    registry = NovaToolRegistry()
    calls = []
    registry.register(
        NovaRegisteredTool(
            name="robot_move",
            version="1.0",
            description="Move a simulated robot.",
            input_schema={
                "type": "object",
                "required": ["distance"],
                "properties": {"distance": {"type": "number"}},
                "additionalProperties": False,
            },
            output_schema={"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}},
            required_permissions=["robot.move"],
            confirmation_policy="always",
            risk_level="high",
            handler=lambda args: calls.append(args) or {"ok": True},
        )
    )

    with pytest.raises(ToolValidationError, match="distance"):
        registry.execute("robot_move", {}, {"robot.move"}, confirmed=True)
    with pytest.raises(ToolValidationError, match="must be number"):
        registry.execute("robot_move", {"distance": "far"}, {"robot.move"}, confirmed=True)
    with pytest.raises(PermissionDeniedError, match="robot.move"):
        registry.execute("robot_move", {"distance": 2}, set(), confirmed=True)
    with pytest.raises(PermissionDeniedError, match="confirmation"):
        registry.execute("robot_move", {"distance": 2}, {"robot.move"})

    assert registry.execute("robot_move", {"distance": 2}, {"robot.move"}, confirmed=True) == {"ok": True}
    assert calls == [{"distance": 2}]


def test_tool_public_metadata_never_deep_copies_live_handler_state() -> None:
    class LockedHandler:
        def __init__(self) -> None:
            self.lock = RLock()

        def run(self, arguments):
            return {"ok": True, "arguments": arguments}

    live_handler = LockedHandler()
    registry = NovaToolRegistry()
    registry.register(
        NovaRegisteredTool(
            name="locked_runtime",
            version="1.0",
            description="A live handler that owns unpicklable runtime state.",
            input_schema={"type": "object"},
            required_permissions=["tools.execute"],
            handler=live_handler.run,
        )
    )

    public_tool = registry.list()[0]

    assert public_tool["name"] == "locked_runtime"
    assert "handler" not in public_tool
    assert registry.health_check() == {"ok": True, "registered": 1, "dynamic": 0}


@pytest.mark.parametrize(
    ("value", "schema", "error_fragment"),
    [
        ({"name": "Nova"}, {"type": "object", "required": ["age"]}, "required"),
        ({"age": "old"}, {"type": "object", "properties": {"age": {"type": "integer"}}}, "integer"),
        ({"items": [1, "two"]}, {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "integer"}}}}, "[1]"),
        ({"nested": {"ok": "yes"}}, {"type": "object", "properties": {"nested": {"type": "object", "properties": {"ok": {"type": "boolean"}}}}}, "boolean"),
    ],
)
def test_json_schema_subset_catches_required_types_nested_objects_and_arrays(value, schema, error_fragment) -> None:
    assert any(error_fragment in error for error in validate_json_schema(value, schema))


def test_structured_output_accepts_valid_json_repairs_fences_and_rejects_invalid_schema() -> None:
    schema_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "answer",
            "schema": {
                "type": "object",
                "required": ["answer", "tags"],
                "properties": {"answer": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}},
            },
        },
    }
    value = parse_structured_output('```json\n{"answer":"ready","tags":["nova"],}\n```', schema_format)
    assert value == {"answer": "ready", "tags": ["nova"]}
    with pytest.raises(InvalidRequestError, match="required"):
        parse_structured_output('{"answer":"ready"}', schema_format)
    with pytest.raises(InvalidRequestError):
        parse_structured_output("not json", {"type": "json_object"})


class FakeMemoryModule:
    def __init__(self):
        self.records = []

    def add_memory(self, content, source_command=None):
        record = {
            "memory_id": f"mem_{len(self.records) + 1}", "raw_text": content, "extracted_value": content,
            "category": "semantic", "source_command": source_command, "created_at": "2026-01-01", "active": True,
        }
        self.records.append(record)
        return record

    def get_all(self, active_only=True):
        return [item for item in self.records if item.get("active", True) or not active_only]

    def find_by_query(self, query):
        return [item for item in self.records if query.lower() in item["raw_text"].lower()]

    def update_memory_by_id(self, memory_id, **updates):
        for item in self.records:
            if item["memory_id"] == memory_id:
                if updates.get("raw_text") is not None:
                    item["raw_text"] = updates["raw_text"]
                return item
        return None

    def set_memory_active(self, memory_id, active=True):
        for item in self.records:
            if item["memory_id"] == memory_id:
                item["active"] = active
                return item
        return None


def test_memory_adapter_preserves_store_and_enforces_policy() -> None:
    module = FakeMemoryModule()
    store = ExistingNovaMemoryStore(module, mode="explicit_write")
    with pytest.raises(PermissionDeniedError, match="explicit"):
        store.add_memory("private fact", explicit=False)
    record = store.add_memory("private fact", explicit=True)
    assert record.owner_id == "local-user"
    assert store.search_memory("private")[0].memory_id == record.memory_id
    exported = store.export_memories()
    assert exported["schema_version"] == "1.0"
    assert store.delete_memory(record.memory_id) is True

    disabled = ExistingNovaMemoryStore(module, mode="disabled")
    with pytest.raises(PermissionDeniedError):
        disabled.search_memory("private")
