"""Universal runtime tool and resource descriptors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    tool_id: str
    name: str
    category: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    required_scopes: tuple[str, ...]
    risk_level: str
    read_write_classification: str
    confirmation_policy: str
    timeout_seconds: int
    supports_rollback: bool
    supports_dry_run: bool
    provider: str
    resource_dependencies: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_scopes"] = list(self.required_scopes)
        data["resource_dependencies"] = list(self.resource_dependencies)
        return data

    @classmethod
    def from_registered_tool(cls, tool: dict[str, Any]) -> "ToolDescriptor":
        return cls(
            tool_id=str(tool["name"]),
            name=str(tool.get("description") or tool["name"]),
            category=str(tool.get("metadata", {}).get("category") or "general"),
            input_schema=dict(tool.get("input_schema") or {"type": "object"}),
            output_schema=dict(tool["output_schema"]) if tool.get("output_schema") else None,
            required_scopes=tuple(tool.get("required_permissions") or ()),
            risk_level=str(tool.get("risk_level") or "safe"),
            read_write_classification=str(tool.get("read_write_classification") or "read"),
            confirmation_policy=str(tool.get("confirmation_policy") or "never"),
            timeout_seconds=int(tool.get("timeout") or 30),
            supports_rollback=bool(tool.get("metadata", {}).get("supports_rollback", False)),
            supports_dry_run=bool(tool.get("metadata", {}).get("supports_dry_run", True)),
            provider=str(tool.get("provider") or "nova-local"),
            resource_dependencies=tuple(tool.get("metadata", {}).get("resource_dependencies") or ()),
            metadata=dict(tool.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class ResourceDescriptor:
    resource_id: str
    uri: str
    resource_type: str
    owner_id: str
    scope: str
    content_classification: str
    read_only: bool
    hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_filesystem_path(cls, path, *, owner_id: str) -> "ResourceDescriptor":
        from pathlib import Path

        path = Path(path)
        return cls(
            resource_id=f"filesystem://{path.as_posix()}",
            uri=path.as_uri(),
            resource_type="filesystem",
            owner_id=owner_id,
            scope="workspace",
            content_classification="project",
            read_only=False,
            hash="",
            metadata={"path": str(path)},
        )

    @classmethod
    def from_terminal_session(cls, session_id: str, *, owner_id: str) -> "ResourceDescriptor":
        return cls(
            resource_id=f"terminal://{session_id}",
            uri=f"terminal://{session_id}",
            resource_type="terminal",
            owner_id=owner_id,
            scope="session",
            content_classification="operational",
            read_only=False,
            hash="",
            metadata={"session_id": session_id},
        )

    @classmethod
    def from_browser_url(cls, url: str, *, owner_id: str) -> "ResourceDescriptor":
        return cls(
            resource_id=f"browser://{url}",
            uri=url,
            resource_type="browser",
            owner_id=owner_id,
            scope="page",
            content_classification="external",
            read_only=True,
            hash="",
            metadata={"url": url},
        )

    @classmethod
    def from_github_repo(cls, repo: str, *, owner_id: str) -> "ResourceDescriptor":
        return cls(
            resource_id=f"github://{repo}",
            uri=f"https://github.com/{repo}",
            resource_type="github",
            owner_id=owner_id,
            scope="repository",
            content_classification="code",
            read_only=False,
            hash="",
            metadata={"repo": repo},
        )

    @classmethod
    def from_research_topic(cls, topic: str, *, owner_id: str) -> "ResourceDescriptor":
        return cls(
            resource_id=f"research://{topic}",
            uri=f"research://{topic}",
            resource_type="research",
            owner_id=owner_id,
            scope="corpus",
            content_classification="reference",
            read_only=True,
            hash="",
            metadata={"topic": topic},
        )
