from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import nova_enhanced_server as server
from nova_gateway.auth import AuthContext, LOCAL_SAFE_SCOPES
from nova_gateway.config import GatewayConfig
from nova_gateway.core import NovaGatewayCore
from nova_gateway.dream_lab import NovaDreamLab
from nova_gateway.errors import InvalidRequestError
from nova_gateway.http import NovaGatewayHttpController
from nova_gateway.world_model import NovaWorldModel


def _controller(core, config):
    return NovaGatewayHttpController(core, authenticator=None, config=config)


def _auth():
    return AuthContext(
        client_id="acceptance-test-client",
        scopes=LOCAL_SAFE_SCOPES,
        local=True,
        authenticated=False,
    )


@pytest.mark.parametrize("invalid", ["true", "false", 1, 0, None, [], {}])
def test_native_evaluation_only_accepts_boolean_values_only(invalid):
    controller = _controller(core=None, config=GatewayConfig())

    with pytest.raises(InvalidRequestError) as caught:
        controller._native_request(
            {"text": "evaluation turn", "evaluation_only": invalid},
            _auth(),
        )

    assert caught.value.param == "evaluation_only"


def test_native_full_and_simple_requests_carry_only_validated_evaluation_metadata():
    controller = _controller(core=None, config=GatewayConfig())

    simple = controller._native_request(
        {"text": "simple evaluation", "evaluation_only": True},
        _auth(),
    )
    full = controller._native_request(
        {
            "messages": [{"role": "user", "content": "full evaluation"}],
            "generation_options": {"model": "nova"},
            "metadata": {"evaluation_only": "untrusted nested value"},
            "evaluation_only": True,
        },
        _auth(),
    )
    ordinary = controller._native_request({"text": "ordinary turn"}, _auth())

    assert simple.metadata["evaluation_only"] is True
    assert full.metadata["evaluation_only"] is True
    assert ordinary.metadata.get("evaluation_only") is None


def test_evaluation_turn_reaches_provider_without_retained_gateway_state(tmp_path):
    checkpoint = tmp_path / "world-model.json"
    training = tmp_path / "conversation_training_data.jsonl"
    training.write_text('{"stable":true}\n', encoding="utf-8")
    before_training = hashlib.sha256(training.read_bytes()).hexdigest()
    observed = []

    def turn_runner(text, context):
        observed.append(dict(context))
        return "Nova evaluation answer.", {
            "route": "evaluation-test",
            "conversation_summary": {
                "schema_version": "1.0",
                "revision": 1,
                "topics": ["must not persist"],
            },
        }

    config = GatewayConfig(
        world_model_persistence="checkpoint",
        world_model_checkpoint_path=checkpoint,
        dream_lab_enabled=True,
    )
    world = NovaWorldModel(
        persistence="checkpoint",
        checkpoint_path=checkpoint,
    )
    dream = NovaDreamLab(enabled=True)
    core = NovaGatewayCore(
        turn_runner,
        config=config,
        world_model=world,
        dream_lab=dream,
        register_ollama=False,
    )
    controller = _controller(core, config)

    baseline = controller._native_request(
        {
            "text": "ordinary baseline",
            "conversation_id": "ordinary-conversation",
        },
        _auth(),
    )
    core.generate(baseline)
    before_world = world.view(_auth().client_id)
    before_dream = dream.health_check()
    before_checkpoint = checkpoint.read_bytes()
    before_cost = (core._estimated_cloud_spend, core._actual_cloud_spend)

    evaluation = controller._native_request(
        {
            "text": "evaluation turn",
            "conversation_id": "evaluation-conversation",
            "evaluation_only": True,
            "conversation_summary_write_allowed": True,
        },
        _auth(),
    )
    response = core.generate(evaluation)

    streaming = controller._native_request(
        {
            "text": "streamed evaluation turn",
            "conversation_id": "stream-evaluation-conversation",
            "evaluation_only": True,
            "stream": True,
        },
        _auth(),
    )
    stream_events = list(core.stream(streaming))

    assert response.content == "Nova evaluation answer."
    assert stream_events[-1].done is True
    assert evaluation.metadata["memory_write_allowed"] is False
    assert evaluation.metadata["conversation_memory_allowed"] is False
    assert streaming.metadata["memory_write_allowed"] is False
    assert streaming.metadata["conversation_memory_allowed"] is False
    assert all(context["evaluation_only"] is True for context in observed[-2:])
    assert all(context["memory_write_allowed"] is False for context in observed[-2:])
    assert all(context["conversation_memory_allowed"] is False for context in observed[-2:])
    assert response.metadata["evaluation_only"] is True
    assert response.metadata["retained_operational_state"] is False
    assert world.view(_auth().client_id) == before_world
    assert world.view(_auth().client_id, "evaluation-conversation")["data"] is None
    assert world.view(_auth().client_id, "stream-evaluation-conversation")["data"] is None
    assert dream.health_check() == before_dream
    assert dream.view(_auth().client_id, "evaluation-conversation")["data"] is None
    assert dream.view(_auth().client_id, "stream-evaluation-conversation")["data"] is None
    assert checkpoint.read_bytes() == before_checkpoint
    assert (core._estimated_cloud_spend, core._actual_cloud_spend) == before_cost
    assert hashlib.sha256(training.read_bytes()).hexdigest() == before_training


def test_evaluation_wrapper_passes_flag_to_brain_route_and_restores_legacy_state(monkeypatch):
    captured = {}
    previous_user = server._LAST_USER_TEXT
    previous_response = server._LAST_NOVA_RESPONSE
    before_log = list(server.SESSION_LOG)

    def fake_brain(text, context=None):
        captured.update(context or {})
        server._LAST_USER_TEXT = text
        server._LAST_NOVA_RESPONSE = "Evaluation output."
        return "Evaluation output.", {
            "source": "raw_adapter_only",
            "roles": ["raw_qwen_adapter"],
        }

    monkeypatch.setattr(server, "brain_route", fake_brain)
    response, trace = server._run_nova_chat_turn(
        "evaluation wrapper",
        {
            "nova_gateway": True,
            "adapter_only_mode": True,
            "evaluation_only": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "conversation_summary_write_allowed": True,
        },
    )

    assert response == "Evaluation output."
    assert captured["evaluation_only"] is True
    assert trace.get("conversation_summary") is None
    assert server._LAST_USER_TEXT == previous_user
    assert server._LAST_NOVA_RESPONSE == previous_response
    assert server.SESSION_LOG == before_log
