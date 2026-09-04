from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.dream_lab import NovaDreamLab  # noqa: E402
from nova_protocol import NovaGenerationOptions, NovaMessage, NovaRequest  # noqa: E402


def request_for(text: str, **overrides) -> NovaRequest:
    values = {
        "request_id": "req_dream",
        "client_id": "phone_one",
        "conversation_id": "dream_conversation",
        "messages": [NovaMessage(role="user", content=text)],
        "generation_options": NovaGenerationOptions(model="nova"),
        "metadata": {
            "client_scopes": ["chat.generate", "memory.read"],
            "memory_read_allowed": True,
        },
    }
    values.update(overrides)
    return NovaRequest(**values)


def test_dream_lab_selects_bounded_local_review_without_storing_prompt_content():
    secret = "PRIVATE-DREAM-PROMPT-123"
    lab = NovaDreamLab()
    request = request_for(
        f"Ultra think and compare the tradeoffs in this future-proof architecture. {secret}"
    )

    decision = lab.simulate(
        request,
        {
            "selected_provider": "existing-nova",
            "selected_model": "nova-core",
            "remains_local": True,
        },
    )
    viewed = lab.view("phone_one", "dream_conversation")
    serialized = json.dumps(viewed)

    assert decision["task_type"] == "complex_reasoning"
    assert decision["selected_strategy"] == "local_counterfactual_review"
    assert len(decision["alternatives"]) == 6
    assert all(item["strategy"] != "remote_specialist" or not item["accepted"] for item in decision["alternatives"])
    assert decision["executed_actions"] is False
    assert secret not in serialized
    assert viewed["privacy"]["private_reasoning_stored"] is False
    assert lab.view("other_client", "dream_conversation")["data"] is None


def test_dream_lab_raw_adapter_lane_is_advisory_passthrough_only():
    lab = NovaDreamLab()
    request = request_for(
        "Give me the raw answer",
        metadata={
            "client_scopes": ["chat.generate"],
            "memory_read_allowed": False,
            "desktop_context": {
                "adapter_only_mode": True,
                "dolphin_adapter_only": True,
            },
        },
    )

    decision = lab.simulate(
        request,
        {
            "selected_provider": "existing-nova",
            "selected_model": "nova-core",
            "remains_local": True,
        },
    )

    assert decision["selected_strategy"] == "raw_adapter_passthrough"
    assert decision["selection_reason"].startswith("Raw adapter output remains unintercepted")
    assert decision["alternatives"][0]["predicted_outcome"].endswith("unchanged.")
    assert decision["executed_actions"] is False

