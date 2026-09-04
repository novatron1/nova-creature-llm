from __future__ import annotations

import pytest

from nova_gateway.errors import PermissionDeniedError, ToolValidationError
from nova_gateway.tools import NovaRegisteredTool
from nova_tool_registry import NovaToolRegistry, create_default_tool_registry


def test_default_registry_exposes_typed_metadata() -> None:
    registry = create_default_tool_registry()
    calculator = registry.get("calculator").public_dict()

    assert calculator["read_write_classification"] == "read"
    assert calculator["idempotency_behavior"] == "idempotent"
    assert calculator["availability_status"] == "available"
    assert calculator["audit_log_policy"] == "metadata_only"
    assert calculator["input_schema"]["required"] == ["expression"]


def test_calculator_is_deterministic_and_audited_without_content() -> None:
    registry = create_default_tool_registry()
    result = registry.execute_typed(
        "calculator",
        {"expression": "(7 + 5) * 3"},
        {"tools.execute"},
    )

    assert result == {
        "expression": "(7 + 5) * 3",
        "result": "36",
        "verified": True,
    }
    audit = registry.audit_log()[-1]
    assert audit["status"] == "verified_result"
    assert audit["arguments_logged"] is False
    assert audit["result_content_logged"] is False


def test_minor_invalid_json_is_repaired_once() -> None:
    registry = create_default_tool_registry()
    result = registry.execute_typed(
        "calculator",
        '```json\n{"expression":"2+3",}\n```',
        {"tools.execute"},
    )
    assert result["result"] == "5"


def test_invalid_arguments_can_be_regenerated_once() -> None:
    registry = create_default_tool_registry()
    calls = []

    result = registry.execute_typed(
        "calculator",
        "not json",
        {"tools.execute"},
        regenerate=lambda prompt: calls.append(prompt) or {"expression": "9*9"},
    )
    assert result["result"] == "81"
    assert len(calls) == 1


def test_unknown_properties_and_missing_scope_fail() -> None:
    registry = create_default_tool_registry()
    with pytest.raises(ToolValidationError):
        registry.execute_typed(
            "calculator",
            {"expression": "1+1", "command": "whoami"},
            {"tools.execute"},
        )
    with pytest.raises(PermissionDeniedError):
        registry.execute_typed("calculator", {"expression": "1+1"}, set())


def test_unavailable_tool_fails_honestly() -> None:
    registry = NovaToolRegistry()
    registry.register(
        NovaRegisteredTool(
            name="future_connector",
            version="1",
            description="Not connected.",
            input_schema={"type": "object"},
            required_permissions=[],
            handler=lambda _: {"ok": True},
            availability_status="unavailable",
        )
    )
    with pytest.raises(ToolValidationError, match="unavailable"):
        registry.execute_typed("future_connector", {}, set())
