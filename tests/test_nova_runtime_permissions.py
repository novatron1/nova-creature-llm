from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.tools import NovaRegisteredTool, NovaToolRegistry  # noqa: E402
from nova_runtime.adapters import (  # noqa: E402
    browser_resource,
    filesystem_resource,
    github_resource,
    research_resource,
    terminal_resource,
    wrap_existing_tool_registry,
)
from nova_runtime.interfaces import ResourceDescriptor, ToolDescriptor  # noqa: E402


def test_tool_descriptor_maps_to_mcp_like_shape():
    descriptor = ToolDescriptor(
        tool_id="filesystem.read",
        name="Read File",
        category="filesystem",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        required_scopes=("files.read",),
        risk_level="safe",
        read_write_classification="read",
        confirmation_policy="never",
        timeout_seconds=30,
        supports_rollback=False,
        supports_dry_run=True,
        provider="nova-local",
        resource_dependencies=("filesystem://workspace",),
    )

    public = descriptor.to_public_dict()

    assert public["tool_id"] == "filesystem.read"
    assert public["name"] == "Read File"
    assert public["required_scopes"] == ["files.read"]
    assert public["resource_dependencies"] == ["filesystem://workspace"]


def test_resource_helpers_build_expected_resources(tmp_path: Path):
    workspace_file = tmp_path / "hello.txt"
    workspace_file.write_text("hello", encoding="utf-8")

    file_resource = filesystem_resource(workspace_file, owner_id="local-user")
    terminal = terminal_resource("session-1", owner_id="local-user")
    browser = browser_resource("http://127.0.0.1:3000/", owner_id="local-user")
    github = github_resource("nova-labs/nova-creature", owner_id="local-user")
    research = research_resource("agent runtime", owner_id="local-user")

    assert isinstance(file_resource, ResourceDescriptor)
    assert file_resource.resource_type == "filesystem"
    assert file_resource.owner_id == "local-user"
    assert file_resource.metadata["path"] == str(workspace_file)
    assert terminal.resource_type == "terminal"
    assert browser.resource_type == "browser"
    assert github.resource_type == "github"
    assert research.resource_type == "research"


def test_wrap_existing_tool_registry_converts_public_metadata():
    registry = NovaToolRegistry()
    registry.register(
        NovaRegisteredTool(
            name="filesystem.read",
            version="1.0",
            description="Read a file",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            required_permissions=["files.read"],
            handler=lambda args: {"path": args["path"]},
            output_schema={"type": "object"},
            local_or_remote="local",
            risk_level="safe",
            confirmation_policy="never",
            timeout=10,
            metadata={"category": "filesystem", "resource_dependencies": ["filesystem://workspace"]},
        )
    )

    wrapped = wrap_existing_tool_registry(registry)

    assert "filesystem.read" in wrapped
    assert wrapped["filesystem.read"].tool_id == "filesystem.read"
    assert wrapped["filesystem.read"].required_scopes == ("files.read",)
    assert wrapped["filesystem.read"].resource_dependencies == ("filesystem://workspace",)

