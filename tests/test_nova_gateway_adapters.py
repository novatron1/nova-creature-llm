from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.adapters import (  # noqa: E402
    nova_to_openai_chat,
    nova_to_openai_response,
    openai_chat_stream_chunks,
    openai_chat_to_nova,
    openai_response_to_nova,
)
from nova_gateway.auth import AuthContext  # noqa: E402
from nova_gateway.config import GatewayConfig  # noqa: E402
from nova_gateway.core import NovaGatewayCore  # noqa: E402
from nova_gateway.errors import PermissionDeniedError, ProviderUnavailableError, UnsupportedFeatureError  # noqa: E402
from nova_gateway.providers import MockProvider  # noqa: E402
from nova_protocol import NovaGenerationOptions, NovaMessage, NovaRequest  # noqa: E402


AUTH = AuthContext(
    client_id="phone",
    scopes=frozenset({"chat.generate", "chat.stream", "memory.read", "memory.write", "tools.list"}),
    local=False,
    authenticated=True,
)


def test_chat_adapter_preserves_all_roles_tools_and_supported_generation_fields() -> None:
    payload = {
        "model": "nova",
        "messages": [
            {"role": "system", "content": "Client context"},
            {"role": "developer", "content": "Be concise"},
            {"role": "user", "content": "Run a lookup"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1"}]},
            {"role": "tool", "content": '{"found":true}', "tool_call_id": "call_1"},
        ],
        "temperature": 0.2,
        "top_p": 0.8,
        "max_completion_tokens": 200,
        "stop": ["END"],
        "seed": 7,
        "frequency_penalty": 0.1,
        "presence_penalty": -0.1,
        "tools": [{
            "type": "function",
            "function": {
                "name": "lookup", "description": "Look up a value",
                "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}},
            },
        }],
        "tool_choice": "auto",
        "metadata": {"conversation_id": "conv_phone", "privacy_mode": "local_only"},
        "user": "owner",
    }

    request = openai_chat_to_nova(payload, AUTH)

    assert [item.role for item in request.messages] == ["system", "developer", "user", "assistant", "tool"]
    assert request.messages[3].metadata["tool_calls"][0]["id"] == "call_1"
    assert request.tools[0].name == "lookup"
    assert request.generation_options.max_tokens == 200
    assert request.conversation_id == "conv_phone"
    assert request.privacy_mode == "local_only"
    assert request.user_id == "owner"


def test_chat_adapter_rejects_important_unsupported_fields() -> None:
    with pytest.raises(UnsupportedFeatureError, match="logprobs"):
        openai_chat_to_nova(
            {"model": "nova", "messages": [{"role": "user", "content": "Hi"}], "logprobs": True},
            AUTH,
        )


def test_gateway_chat_enters_real_nova_wrapper_and_returns_openai_shape() -> None:
    observed = {}

    def runner(text, context):
        observed["text"] = text
        observed["context"] = context
        return "Nova is ready.", {"route": "nova_cognitive_os", "identity": "nova"}

    gateway = NovaGatewayCore(runner, config=GatewayConfig(), register_ollama=False)
    request = openai_chat_to_nova(
        {
            "model": "nova",
            "messages": [{"role": "system", "content": "Stay useful"}, {"role": "user", "content": "Hello"}],
            "metadata": {"conversation_id": "conv_stable"},
        },
        AUTH,
    )
    response = gateway.generate(request)
    payload = nova_to_openai_chat(response)

    assert observed["text"] == "Hello"
    assert observed["context"]["nova_gateway"] is True
    assert observed["context"]["memory_read_allowed"] is True
    assert response.metadata["nova_core"] is True
    assert payload["object"] == "chat.completion"
    assert payload["model"] == "nova"
    assert payload["choices"][0]["message"] == {"role": "assistant", "content": "Nova is ready."}
    assert payload["nova_metadata"]["conversation_id"] == "conv_stable"
    assert "usage" not in payload  # No fabricated token counts.


def test_gateway_memory_scopes_and_mode_are_enforced_before_core() -> None:
    gateway = NovaGatewayCore(lambda text, context: ("should not run", {}), config=GatewayConfig(), register_ollama=False)
    no_memory_auth = AuthContext("limited", frozenset({"chat.generate"}), False, True)
    read_request = openai_chat_to_nova(
        {"model": "nova", "messages": [{"role": "user", "content": "What do you remember about me?"}]},
        no_memory_auth,
    )
    with pytest.raises(PermissionDeniedError, match="read Nova memory"):
        gateway.generate(read_request)

    read_only = NovaGatewayCore(
        lambda text, context: ("should not run", {}),
        config=GatewayConfig(memory_mode="read_only"),
        register_ollama=False,
    )
    write_request = openai_chat_to_nova(
        {"model": "nova", "messages": [{"role": "user", "content": "Remember this: my color is blue"}]},
        AUTH,
    )
    with pytest.raises(PermissionDeniedError, match="read_only"):
        read_only.generate(write_request)


def test_true_stream_chunks_are_ordered_and_reconstruct_without_duplication() -> None:
    gateway = NovaGatewayCore(lambda text, context: ("core", {}), config=GatewayConfig(), register_ollama=False)
    mock = MockProvider(chunks=["Nova", " ", "streams"])
    gateway.register_provider(mock, aliases={"nova-stream": "mock-text"})
    request = openai_chat_to_nova(
        {"model": "nova-stream", "messages": [{"role": "user", "content": "Go"}], "stream": True},
        AUTH,
    )

    chunks = list(openai_chat_stream_chunks(request, gateway.stream(request)))

    assert "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks) == "Nova streams"
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert len({chunk["id"] for chunk in chunks}) == 1


def test_structured_output_is_validated_after_nova_core() -> None:
    gateway = NovaGatewayCore(
        lambda text, context: ('```json\n{"answer":"ready",}\n```', {"route": "structured"}),
        config=GatewayConfig(),
        register_ollama=False,
    )
    request = openai_chat_to_nova(
        {
            "model": "nova", "messages": [{"role": "user", "content": "Return JSON"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}},
            },
        },
        AUTH,
    )
    response = gateway.generate(request)
    assert response.content == '{"answer":"ready"}'
    assert response.metadata["structured_output_validated"] is True


def test_basic_responses_adapter_and_flat_function_tools() -> None:
    request = openai_response_to_nova(
        {
            "model": "nova",
            "instructions": "Keep Nova's identity",
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello"}]}],
            "tools": [{"type": "function", "name": "lookup", "parameters": {"type": "object"}}],
            "previous_response_id": "resp_previous",
            "metadata": {"conversation_id": "conv_responses"},
        },
        AUTH,
    )
    assert request.messages[0].role == "developer"
    assert request.last_user_text() == "Hello"
    assert request.tools[0].name == "lookup"
    assert request.metadata["previous_response_id"] == "resp_previous"

    gateway = NovaGatewayCore(lambda text, context: ("Response answer", {"route": "core"}), config=GatewayConfig(), register_ollama=False)
    output = nova_to_openai_response(gateway.generate(request))
    assert output["object"] == "response"
    assert output["status"] == "completed"
    assert output["output_text"] == "Response answer"


def test_embedding_route_uses_only_capable_registered_provider() -> None:
    gateway = NovaGatewayCore(lambda text, context: ("core", {}), config=GatewayConfig(), register_ollama=False)
    mock = MockProvider()
    gateway.register_provider(mock, aliases={"nova-embed": "mock-text"})

    vectors, capability = gateway.embed(["Nova", "Creature"], "nova-embed")
    assert len(vectors) == 2
    assert vectors[0][0] == 4.0
    assert capability.embeddings is True


class FailingMockProvider(MockProvider):
    provider_id = "failing"

    def generate(self, request):
        raise ProviderUnavailableError("primary unavailable")


def test_provider_failure_uses_policy_compliant_local_fallback() -> None:
    gateway = NovaGatewayCore(lambda text, context: ("Fallback Nova core", {"route": "fallback"}), config=GatewayConfig(), register_ollama=False)
    failing = FailingMockProvider()
    gateway.register_provider(failing, aliases={"nova-failing": "mock-text"})
    request = NovaRequest(
        messages=[NovaMessage(role="user", content="Hello")],
        generation_options=NovaGenerationOptions(model="nova-failing"),
        metadata={"client_scopes": ["chat.generate"]},
    )

    response = gateway.generate(request)

    assert response.content == "Fallback Nova core"
    assert response.metadata["routing"]["selected_provider"] == "existing-nova"
    assert response.metadata["routing"]["fallback_path"] == ["failing", "existing-nova"]


def test_existing_agent_actions_are_blocked_before_brain_without_scopes() -> None:
    gateway = NovaGatewayCore(lambda text, context: ("must not execute", {}), config=GatewayConfig(), register_ollama=False)
    request = NovaRequest(
        messages=[NovaMessage(role="user", content="Run shell command to list everything")],
        generation_options=NovaGenerationOptions(model="nova"),
        metadata={"client_scopes": ["chat.generate"]},
    )
    with pytest.raises(PermissionDeniedError, match="system.execute"):
        gateway.generate(request)
