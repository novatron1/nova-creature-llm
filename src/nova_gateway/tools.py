"""Universal Nova tool metadata, schema, permission, and timeout registry."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable

from .errors import PermissionDeniedError, RequestTimeoutError, ToolValidationError
from .structured import validate_json_schema


TOOL_SCHEMA_VERSION = "1.0"
TOOL_CATEGORIES = (
    "web_search", "file_search", "memory", "calendar", "email", "image_generation",
    "video_generation", "speech", "music", "code_execution", "robot_control",
    "game_control", "smart_home_control",
)


@dataclass
class NovaRegisteredTool:
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    required_permissions: list[str]
    handler: Callable[[dict[str, Any]], Any]
    output_schema: dict[str, Any] | None = None
    local_or_remote: str = "local"
    risk_level: str = "safe"
    confirmation_policy: str = "never"
    timeout: int = 30
    health_status: str = "healthy"
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = TOOL_SCHEMA_VERSION
    read_write_classification: str = "read"
    retry_policy: dict[str, Any] = field(
        default_factory=lambda: {"max_retries": 0, "retry_on": []}
    )
    idempotency_behavior: str = "idempotent"
    availability_status: str = "available"
    provider: str = "nova-local"
    audit_log_policy: str = "metadata_only"

    def public_dict(self) -> dict[str, Any]:
        # Build the public view explicitly. ``dataclasses.asdict`` deep-copies
        # every field before callers can remove ``handler``; bound handlers can
        # own locks, sockets, model runtimes, or other intentionally unpicklable
        # state. None of that executable state belongs in API metadata.
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "required_permissions": list(self.required_permissions),
            "output_schema": dict(self.output_schema) if self.output_schema is not None else None,
            "local_or_remote": self.local_or_remote,
            "risk_level": self.risk_level,
            "confirmation_policy": self.confirmation_policy,
            "timeout": self.timeout,
            "health_status": self.health_status,
            "metadata": dict(self.metadata),
            "schema_version": self.schema_version,
            "read_write_classification": self.read_write_classification,
            "retry_policy": dict(self.retry_policy),
            "idempotency_behavior": self.idempotency_behavior,
            "availability_status": self.availability_status,
            "provider": self.provider,
            "audit_log_policy": self.audit_log_policy,
        }


class NovaToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, NovaRegisteredTool] = {}
        self._lock = RLock()

    def register(self, tool: NovaRegisteredTool) -> None:
        if not tool.name or not callable(tool.handler):
            raise ValueError("A registered tool requires a name and callable handler.")
        with self._lock:
            self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        with self._lock:
            self._tools.pop(name, None)

    def get(self, name: str) -> NovaRegisteredTool:
        with self._lock:
            tool = self._tools.get(name)
        if tool is None:
            raise ToolValidationError(f"Unknown registered Nova tool: {name}.")
        return tool

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [tool.public_dict() for tool in self._tools.values()]

    def validate_arguments(self, name: str, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ToolValidationError("Tool arguments must be a JSON object.")
        errors = validate_json_schema(arguments, self.get(name).input_schema)
        if errors:
            raise ToolValidationError(" ".join(errors))

    def check_permissions(self, name: str, scopes: set[str] | frozenset[str], *, confirmed: bool = False) -> None:
        tool = self.get(name)
        missing = set(tool.required_permissions) - set(scopes)
        if missing:
            raise PermissionDeniedError(f"Tool {name!r} requires scopes: {', '.join(sorted(missing))}.")
        if tool.confirmation_policy in {"always", "dangerous"} and not confirmed:
            raise PermissionDeniedError(f"Tool {name!r} requires explicit user confirmation.")

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        scopes: set[str] | frozenset[str],
        *,
        confirmed: bool = False,
    ) -> Any:
        tool = self.get(name)
        if tool.availability_status != "available":
            raise ToolValidationError(
                f"Tool {name!r} is {tool.availability_status}; it cannot be executed."
            )
        self.validate_arguments(name, arguments)
        self.check_permissions(name, scopes, confirmed=confirmed)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"nova-tool-{name}")
        future = executor.submit(tool.handler, dict(arguments))
        try:
            result = future.result(timeout=max(1, int(tool.timeout)))
        except FutureTimeout as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise RequestTimeoutError(f"Tool {name!r} exceeded its {tool.timeout}-second timeout.") from exc
        else:
            executor.shutdown(wait=True)
        if tool.output_schema:
            errors = validate_json_schema(result, tool.output_schema)
            if errors:
                raise ToolValidationError(f"Tool {name!r} returned invalid output: {' '.join(errors)}")
        return result

    def health_check(self) -> dict[str, Any]:
        tools = self.list()
        healthy_states = {"healthy", "dynamic"}
        return {
            "ok": all(item["health_status"] in healthy_states for item in tools),
            "registered": len(tools),
            "dynamic": sum(1 for item in tools if item["health_status"] == "dynamic"),
        }


def registry_from_existing_tools() -> NovaToolRegistry:
    """Wrap the current safe agent tools without changing their handlers."""
    registry = NovaToolRegistry()
    try:
        from nova_tools import get_tool_registry

        permission_map = {
            "read_project_file": ["files.read"],
            "list_project_files": ["files.read"],
            "search_project_text": ["files.read"],
            "write_project_file": ["files.write", "tools.execute"],
            "run_project_tests": ["system.execute", "tools.execute"],
            "run_shell_command": ["system.execute", "tools.execute"],
            "web_search": ["tools.execute"],
        }
        for current in get_tool_registry().values():
            registry.register(
                NovaRegisteredTool(
                    name=current.name,
                    version="1.0",
                    description=current.description,
                    input_schema=dict(current.input_schema or {"type": "object"}),
                    required_permissions=permission_map.get(current.name, ["tools.execute"]),
                    handler=current.callable,
                    risk_level=current.risk_level,
                    confirmation_policy="always" if current.requires_approval else "never",
                    metadata={"wrapped_existing_tool": True},
                    read_write_classification=(
                        "write"
                        if current.name in {"write_project_file", "run_project_tests", "run_shell_command"}
                        else "read"
                    ),
                    idempotency_behavior=(
                        "non_idempotent"
                        if current.name in {"write_project_file", "run_shell_command"}
                        else "idempotent"
                    ),
                    provider="nova-existing-tools",
                )
            )
    except Exception:
        pass
    return registry
