"""Explicit MCP extension boundary; runtime support is not claimed."""

from __future__ import annotations

from typing import Any

from .errors import UnsupportedFeatureError


MCP_COMPATIBILITY = {
    "client": "NOT IMPLEMENTED",
    "server": "NOT IMPLEMENTED",
    "permission_model": "NovaToolRegistry and Nova client scopes",
    "planned_tools": [
        "nova_chat", "nova_memory_search", "nova_project_context", "nova_list_tools",
        "nova_generate_image", "nova_generate_video", "nova_transcribe_audio", "nova_robot_status", "nova_game_status",
    ],
}


class NovaMcpExtensionBoundary:
    """A deliberate non-operational boundary until an MCP runtime is selected."""

    def connect_server(self, configuration: dict[str, Any]) -> None:
        raise UnsupportedFeatureError("Nova MCP client support is not implemented in this build.")

    def serve(self, configuration: dict[str, Any]) -> None:
        raise UnsupportedFeatureError("Nova MCP server support is not implemented in this build.")

    def status(self) -> dict[str, Any]:
        return dict(MCP_COMPATIBILITY)

