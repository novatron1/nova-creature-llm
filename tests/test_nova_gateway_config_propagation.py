from __future__ import annotations

import nova_enhanced_server as server


def test_gateway_environment_imports_comfyui_workflow_from_runtime_config(monkeypatch):
    monkeypatch.delenv("NOVA_COMFYUI_IMAGE_WORKFLOW", raising=False)
    monkeypatch.setattr(
        server,
        "_runtime_config_values",
        lambda: {
            "NOVA_COMFYUI_IMAGE_WORKFLOW": (
                "config/comfyui_dreamshaper8_text_to_image_workflow.local.json"
            )
        },
    )

    gateway_env = server._gateway_environment()

    assert gateway_env["NOVA_COMFYUI_IMAGE_WORKFLOW"] == (
        "config/comfyui_dreamshaper8_text_to_image_workflow.local.json"
    )
