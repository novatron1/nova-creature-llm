from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_protocol import (  # noqa: E402
    NovaGenerationOptions,
    NovaMessage,
    NovaRequest,
    NovaResponse,
    NovaStreamEvent,
    NovaToolCall,
    NovaToolDefinition,
    ProtocolValidationError,
)


def test_nova_request_round_trip_preserves_provider_neutral_fields() -> None:
    request = NovaRequest(
        request_id="req_test",
        user_id="owner",
        client_id="desktop",
        conversation_id="conv_test",
        session_id="sess_test",
        messages=[
            NovaMessage(role="system", content="Stay Nova."),
            NovaMessage(role="developer", content="Use the cognitive core."),
            NovaMessage(role="user", content="Hello"),
            NovaMessage(role="assistant", content="Hi"),
            NovaMessage(role="tool", content='{"ok":true}', tool_call_id="call_1"),
        ],
        tools=[
            NovaToolDefinition(
                name="memory_search",
                description="Search permitted memory.",
                input_schema={"type": "object", "required": ["query"]},
            )
        ],
        generation_options=NovaGenerationOptions(
            model="nova",
            temperature=0.2,
            max_tokens=256,
            stream=True,
            response_format={"type": "json_object"},
        ),
        requested_modalities=["text"],
        privacy_mode="local_only",
        metadata={"project": "gateway"},
        api_source="openai_chat_completions",
    )

    restored = NovaRequest.from_dict(json.loads(request.to_json()))

    assert restored.to_dict() == request.to_dict()
    assert [message.role for message in restored.messages] == [
        "system",
        "developer",
        "user",
        "assistant",
        "tool",
    ]
    assert restored.last_user_text() == "Hello"
    assert restored.generation_options.model == "nova"
    assert restored.tools[0].name == "memory_search"


def test_response_and_stream_event_round_trip() -> None:
    tool_call = NovaToolCall(
        tool_call_id="call_1",
        name="memory_search",
        arguments={"query": "Nova"},
        status="completed",
        result={"matches": []},
    )
    response = NovaResponse(
        response_id="resp_test",
        request_id="req_test",
        conversation_id="conv_test",
        model="nova",
        provider="existing-nova",
        content="Ready.",
        tool_calls=[tool_call],
        usage={"estimated": True},
    )
    event = NovaStreamEvent(
        event_type="content.delta",
        response_id=response.response_id,
        sequence=1,
        delta="Ready.",
        tool_call=tool_call,
        metadata={"trace": {"route": "cognitive_os"}, "conversation_id": "conv_test"},
    )

    assert NovaResponse.from_dict(json.loads(response.to_json())).to_dict() == response.to_dict()
    assert NovaStreamEvent.from_dict(json.loads(event.to_json())).to_dict() == event.to_dict()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: NovaMessage(role="root", content="no"), "role"),
        (
            lambda: NovaRequest(
                messages=[NovaMessage(role="user", content="hello")],
                privacy_mode="send_everything",
            ),
            "privacy mode",
        ),
        (lambda: NovaGenerationOptions(temperature=3), "temperature"),
        (lambda: NovaGenerationOptions(max_tokens=0), "max_tokens"),
    ],
)
def test_protocol_rejects_invalid_values(factory, message: str) -> None:
    with pytest.raises(ProtocolValidationError, match=message):
        factory()
