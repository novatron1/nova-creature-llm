"""Typed, permission-aware tool registry for Nova's cognitive operating layer.

This module extends the compatibility gateway's registry instead of creating a
second execution policy. Tool inputs and outputs are validated, unavailable
tools fail honestly, and audit records contain operational metadata only.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, DivisionByZero, InvalidOperation
import json
import math
from pathlib import Path
from threading import RLock
import time
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from nova_gateway.errors import ToolValidationError
from nova_gateway.structured import parse_structured_output
from nova_gateway.tools import (
    TOOL_SCHEMA_VERSION,
    NovaRegisteredTool,
    NovaToolRegistry as GatewayToolRegistry,
    registry_from_existing_tools,
)


NOVA_TOOL_REGISTRY_VERSION = "1.0"


@dataclass(frozen=True)
class ToolAuditRecord:
    tool_name: str
    status: str
    started_at: str
    duration_ms: float
    attempt_count: int
    confirmed: bool
    error_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "started_at": self.started_at,
            "duration_ms": round(self.duration_ms, 2),
            "attempt_count": self.attempt_count,
            "confirmed": self.confirmed,
            "error_type": self.error_type,
            "metadata": dict(self.metadata),
            "arguments_logged": False,
            "result_content_logged": False,
        }


class NovaToolRegistry(GatewayToolRegistry):
    """Gateway-compatible registry with bounded repair, retry, and safe audit."""

    def __init__(self) -> None:
        super().__init__()
        self._audit: list[ToolAuditRecord] = []
        self._audit_lock = RLock()

    def parse_arguments(
        self,
        name: str,
        arguments: dict[str, Any] | str,
        *,
        regenerate: Callable[[str], str | dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if isinstance(arguments, dict):
            candidate = arguments
        elif isinstance(arguments, str):
            try:
                candidate = json.loads(arguments)
            except json.JSONDecodeError:
                try:
                    candidate = parse_structured_output(
                        arguments,
                        {"type": "json_object"},
                        repair_attempts=1,
                    )
                except Exception as first_error:
                    if regenerate is None:
                        raise ToolValidationError(
                            f"Tool {name!r} arguments are not valid JSON."
                        ) from first_error
                    regenerated = regenerate(
                        f"Return one valid JSON object for registered tool {name!r}."
                    )
                    return self.parse_arguments(name, regenerated, regenerate=None)
        else:
            raise ToolValidationError("Tool arguments must be a JSON object or JSON string.")
        if not isinstance(candidate, dict):
            raise ToolValidationError("Tool arguments must decode to a JSON object.")
        self.validate_arguments(name, candidate)
        return candidate

    def execute_typed(
        self,
        name: str,
        arguments: dict[str, Any] | str,
        scopes: set[str] | frozenset[str],
        *,
        confirmed: bool = False,
        regenerate: Callable[[str], str | dict[str, Any]] | None = None,
    ) -> Any:
        parsed = self.parse_arguments(name, arguments, regenerate=regenerate)
        tool = self.get(name)
        retries = max(0, min(int(tool.retry_policy.get("max_retries", 0)), 2))
        started = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        attempts = 0
        last_error: Exception | None = None
        for attempts in range(1, retries + 2):
            try:
                result = super().execute(name, parsed, scopes, confirmed=confirmed)
                self._record(
                    ToolAuditRecord(
                        name,
                        "verified_result",
                        started_at,
                        (time.monotonic() - started) * 1000,
                        attempts,
                        confirmed,
                        metadata={
                            "risk_level": tool.risk_level,
                            "provider": tool.provider,
                            "audit_policy": tool.audit_log_policy,
                        },
                    )
                )
                return result
            except Exception as error:
                last_error = error
                retry_on = set(tool.retry_policy.get("retry_on") or ())
                if attempts > retries or type(error).__name__ not in retry_on:
                    break
        assert last_error is not None
        self._record(
            ToolAuditRecord(
                name,
                "failed",
                started_at,
                (time.monotonic() - started) * 1000,
                attempts,
                confirmed,
                type(last_error).__name__,
                {
                    "risk_level": tool.risk_level,
                    "provider": tool.provider,
                    "audit_policy": tool.audit_log_policy,
                },
            )
        )
        raise last_error

    def _record(self, record: ToolAuditRecord) -> None:
        with self._audit_lock:
            self._audit.append(record)
            del self._audit[:-500]

    def audit_log(self) -> list[dict[str, Any]]:
        with self._audit_lock:
            return [item.to_dict() for item in self._audit]


_BINARY = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}
_UNARY = {ast.UAdd: lambda value: value, ast.USub: lambda value: -value}


def _calculate_node(node: ast.AST, budget: list[int]) -> Decimal:
    budget[0] += 1
    if budget[0] > 40:
        raise ValueError("Expression is too complex.")
    if isinstance(node, ast.Expression):
        return _calculate_node(node.body, budget)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        value = Decimal(str(node.value))
        if abs(value) > Decimal("1e15"):
            raise ValueError("Number is outside the calculator limit.")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_calculate_node(node.operand, budget))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _calculate_node(node.left, budget)
        right = _calculate_node(node.right, budget)
        if isinstance(node.op, ast.Pow) and (abs(right) > 10 or abs(left) > Decimal("1e7")):
            raise ValueError("Power operation is outside the calculator limit.")
        try:
            result = _BINARY[type(node.op)](left, right)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as error:
            raise ValueError("The arithmetic expression is undefined.") from error
        if not math.isfinite(float(result)) or abs(result) > Decimal("1e18"):
            raise ValueError("Result is outside the calculator limit.")
        return result
    raise ValueError("Only numeric arithmetic is supported.")


def _calculator(arguments: dict[str, Any]) -> dict[str, Any]:
    expression = str(arguments["expression"]).strip()
    if len(expression) > 200:
        raise ValueError("Expression is too long.")
    parsed = ast.parse(expression, mode="eval")
    result = _calculate_node(parsed, [0])
    normalized = format(result.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return {"expression": expression, "result": normalized, "verified": True}


def _date_time(arguments: dict[str, Any]) -> dict[str, Any]:
    zone_name = str(arguments.get("timezone") or "UTC")
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown IANA timezone: {zone_name}") from error
    now = datetime.now(zone)
    return {
        "timezone": zone_name,
        "iso8601": now.isoformat(timespec="seconds"),
        "date": now.date().isoformat(),
        "time": now.time().isoformat(timespec="seconds"),
    }


def _memory_search(arguments: dict[str, Any]) -> dict[str, Any]:
    from nova_memory_v2 import get_default_memory

    records = get_default_memory().list_relevant(
        str(arguments["query"]),
        limit=int(arguments.get("limit", 6)),
    )
    return {
        "records": [
            {
                "id": item.memory_id,
                "type": item.memory_type,
                "text": item.text,
                "confidence": item.confidence,
                "importance": item.importance,
                "project_name": item.project_name,
                "tags": list(item.tags),
            }
            for item in records
        ]
    }


def _rag_search(arguments: dict[str, Any]) -> dict[str, Any]:
    from nova_rag import get_default_rag

    result = get_default_rag().search(
        str(arguments["query"]),
        top_k=int(arguments.get("top_k", 6)),
    )
    return {
        "status": result.status,
        "passages": [
            {
                "citation": passage.citation,
                "title": passage.document_title,
                "source": passage.source_location,
                "section": passage.section_heading,
                "text": passage.text,
                "score": passage.score,
            }
            for passage in result.passages
        ],
    }


def _provider_listing(arguments: dict[str, Any]) -> dict[str, Any]:
    from nova_model_provider import ExistingConnectorProvider

    provider = ExistingConnectorProvider()
    return {
        "active_provider": provider.provider_id,
        "models": provider.list_models(),
        "capabilities": [
            provider.get_capabilities(model).to_dict() for model in provider.list_models()
        ],
    }


def _diagnostics(arguments: dict[str, Any]) -> dict[str, Any]:
    from nova_memory_v2 import get_default_memory
    from nova_rag import get_default_rag

    root = Path(__file__).resolve().parents[1]
    return {
        "ok": True,
        "project_root_exists": root.is_dir(),
        "memory": get_default_memory().health_check(),
        "rag": get_default_rag().health_check(),
        "telemetry_enabled": False,
        "secrets_included": False,
    }


def _python_sandbox(arguments: dict[str, Any]) -> dict[str, Any]:
    from nova_code_sandbox import execute_code

    result = execute_code(
        str(arguments["code"]),
        language="python",
        timeout_seconds=int(arguments.get("timeout_seconds", 10)),
        output_limit_bytes=int(arguments.get("output_limit_bytes", 65_536)),
    )
    return result.to_dict()


def _observation_requires_live_input(arguments: dict[str, Any]) -> dict[str, Any]:
    raise ValueError(
        "A fresh client observation must be attached to the active Nova turn."
    )


def _physical_movement_disabled(arguments: dict[str, Any]) -> dict[str, Any]:
    raise PermissionError(
        "Physical robot movement is disabled; use simulation and explicit approval."
    )


def _copy_existing(registry: NovaToolRegistry) -> None:
    existing = registry_from_existing_tools()
    for item in existing.list():
        original = existing.get(item["name"])
        registry.register(original)


def create_default_tool_registry() -> NovaToolRegistry:
    registry = NovaToolRegistry()
    _copy_existing(registry)
    registry.register(
        NovaRegisteredTool(
            name="calculator",
            version="1.0",
            description="Evaluate bounded numeric arithmetic without executing generated code.",
            input_schema={
                "type": "object",
                "required": ["expression"],
                "additionalProperties": False,
                "properties": {"expression": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "required": ["expression", "result", "verified"],
                "properties": {
                    "expression": {"type": "string"},
                    "result": {"type": "string"},
                    "verified": {"type": "boolean"},
                },
            },
            required_permissions=["tools.execute"],
            handler=_calculator,
            risk_level="safe",
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="date_time",
            version="1.0",
            description="Return the current date and time for an IANA timezone.",
            input_schema={
                "type": "object",
                "properties": {"timezone": {"type": "string"}},
                "additionalProperties": False,
            },
            required_permissions=["tools.execute"],
            handler=_date_time,
            risk_level="safe",
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="memory_search",
            version="1.0",
            description="Retrieve relevant structured Nova memories.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            required_permissions=["memory.read"],
            handler=_memory_search,
            risk_level="low",
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="rag_retrieve",
            version="1.0",
            description="Retrieve citation-bearing passages from Nova's local knowledge store.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            required_permissions=["tools.execute"],
            handler=_rag_search,
            risk_level="safe",
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="model_provider_list",
            version="1.0",
            description="List the currently configured Nova model provider and capabilities.",
            input_schema={"type": "object", "additionalProperties": False},
            required_permissions=["tools.list"],
            handler=_provider_listing,
            risk_level="safe",
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="system_diagnostics",
            version="1.0",
            description="Return privacy-safe Nova component health diagnostics.",
            input_schema={"type": "object", "additionalProperties": False},
            required_permissions=["tools.list"],
            handler=_diagnostics,
            risk_level="safe",
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="python_sandbox",
            version="1.0",
            description=(
                "Run bounded Python in a disposable subprocess with no network "
                "or host-file access."
            ),
            input_schema={
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                    "output_limit_bytes": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            required_permissions=["system.execute", "tools.execute"],
            handler=_python_sandbox,
            local_or_remote="local",
            risk_level="medium",
            confirmation_policy="never",
            timeout=35,
            read_write_classification="isolated_write",
            idempotency_behavior="non_idempotent",
            provider="nova-code-sandbox",
            metadata={
                "network_default": "blocked",
                "host_files_default": "blocked",
                "temporary_directory": True,
            },
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="vision.observe",
            version="1.0",
            description=(
                "Inspect a fresh client-provided image through Nova's local "
                "vision, OCR, and deterministic scene pipeline."
            ),
            input_schema={
                "type": "object",
                "properties": {"observation_id": {"type": "string"}},
                "additionalProperties": False,
            },
            required_permissions=["vision.observe"],
            handler=_observation_requires_live_input,
            read_write_classification="read",
            risk_level="low",
            availability_status="requires_live_input",
            provider="nova-perception-fusion",
            metadata={
                "image_content_logged": False,
                "requires_fresh_client_observation": True,
            },
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="robot.observe",
            version="1.0",
            description=(
                "Read a fresh robot sensor snapshot without performing movement."
            ),
            input_schema={
                "type": "object",
                "properties": {"observation_id": {"type": "string"}},
                "additionalProperties": False,
            },
            required_permissions=["robot.observe"],
            handler=_observation_requires_live_input,
            read_write_classification="read",
            risk_level="low",
            availability_status="requires_live_input",
            provider="nova-perception-fusion",
            metadata={
                "movement_authorized": False,
                "sensor_values_logged": False,
            },
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="robot.move",
            version="1.0",
            description=(
                "Physical robot movement boundary. Disabled until a separately "
                "configured controller, calibrated perception, and explicit "
                "authorization are all available."
            ),
            input_schema={
                "type": "object",
                "required": ["command"],
                "properties": {"command": {"type": "string"}},
                "additionalProperties": False,
            },
            required_permissions=["robot.move"],
            handler=_physical_movement_disabled,
            read_write_classification="external_write",
            risk_level="critical",
            confirmation_policy="dangerous",
            availability_status="disabled",
            provider="nova-robot-policy",
            idempotency_behavior="non_idempotent",
            metadata={
                "physical_movement_enabled": False,
                "simulation_available": True,
            },
        )
    )
    return registry


_DEFAULT_REGISTRY: NovaToolRegistry | None = None
_DEFAULT_LOCK = RLock()


def get_default_tool_registry() -> NovaToolRegistry:
    global _DEFAULT_REGISTRY
    with _DEFAULT_LOCK:
        if _DEFAULT_REGISTRY is None:
            _DEFAULT_REGISTRY = create_default_tool_registry()
        return _DEFAULT_REGISTRY


__all__ = [
    "NOVA_TOOL_REGISTRY_VERSION",
    "TOOL_SCHEMA_VERSION",
    "NovaRegisteredTool",
    "NovaToolRegistry",
    "ToolAuditRecord",
    "create_default_tool_registry",
    "get_default_tool_registry",
]
