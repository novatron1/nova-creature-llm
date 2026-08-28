"""Adapters between existing Nova registries and the canonical runtime interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nova_gateway.tools import NovaToolRegistry

from .interfaces import ResourceDescriptor, ToolDescriptor


def build_mcp_tool_spec(descriptor: ToolDescriptor) -> dict[str, Any]:
    return {
        "name": descriptor.tool_id,
        "description": descriptor.name,
        "inputSchema": descriptor.input_schema,
        "outputSchema": descriptor.output_schema,
    }


def filesystem_resource(path: Path, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_filesystem_path(path.resolve(), owner_id=owner_id)


def terminal_resource(session_id: str, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_terminal_session(session_id, owner_id=owner_id)


def browser_resource(url: str, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_browser_url(url, owner_id=owner_id)


def github_resource(repo: str, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_github_repo(repo, owner_id=owner_id)


def research_resource(topic: str, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_research_topic(topic, owner_id=owner_id)


def wrap_existing_tool_registry(registry: NovaToolRegistry) -> dict[str, ToolDescriptor]:
    return {
        item["name"]: ToolDescriptor.from_registered_tool(item)
        for item in registry.list()
    }

