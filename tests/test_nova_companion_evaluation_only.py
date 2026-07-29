from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import threading

import pytest

import nova_enhanced_server as server
import nova_evaluation_policy as evaluation_policy
from nova_gateway.adapters import openai_chat_to_nova, openai_response_to_nova
from nova_gateway.auth import AuthContext, LOCAL_SAFE_SCOPES
from nova_gateway.config import GatewayConfig
from nova_gateway.core import NovaGatewayCore
from nova_gateway.dream_lab import NovaDreamLab
from nova_gateway.errors import InvalidRequestError, PermissionDeniedError
from nova_gateway.http import NovaGatewayHttpController
from nova_gateway.providers import MockProvider
from nova_gateway.router import RoutingDecision
from nova_gateway.world_model import NovaWorldModel
from nova_protocol import NovaStreamEvent


LEGACY_MUTATING_COMMAND_ALIASES = (
    "allow mic",
    "enable mic",
    "deny mic",
    "disable mic",
    "allow camera",
    "enable camera",
    "deny camera",
    "disable camera",
    "allow speaker",
    "enable speaker",
    "deny speaker",
    "disable speaker",
    "private mode",
    "toggle private",
    "stop all",
    "emergency stop",
    "can u train yourself",
    "can you train yourself",
    "do a full training",
    "do all training",
    "full training",
    "run full training",
    "train yourself",
    "train urself",
    "train everything",
    "train all",
    "train nova",
    "make it smarter",
    "make nova smarter",
    "run training center",
    "training center",
    "deep learn",
    "deep learn now",
    "train transformers",
    "train now",
    "train all roles",
    "learn this: persist me",
    "remember this: persist me",
    "save this: persist me",
    "forget long-term memory: persist me",
    "edit long-term memory: old -> new",
    "my name is Eval Person",
    "my girlfriend's name is Eval Person",
    "my dog's name is Eval Pet",
    "mock voice learn this: persist me",
    "mock camera known person",
    "run command dir",
    "write file evaluation.txt",
    "open application calculator",
    "generate image of a test",
)


def _controller(core, config):
    return NovaGatewayHttpController(core, authenticator=None, config=config)


def _auth():
    return AuthContext(
        client_id="acceptance-test-client",
        scopes=LOCAL_SAFE_SCOPES,
        local=True,
        authenticated=False,
    )


def _remote_auth():
    return AuthContext(
        client_id="remote-evaluation-spoof",
        scopes=frozenset({"chat.generate"}),
        local=False,
        authenticated=True,
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
    assert simple.privacy_mode == "local_only"
    assert full.privacy_mode == "local_only"
    assert ordinary.metadata.get("evaluation_only") is None


def test_openai_adapters_strip_reserved_evaluation_metadata():
    chat = openai_chat_to_nova(
        {
            "model": "nova",
            "messages": [{"role": "user", "content": "ordinary OpenAI chat"}],
            "metadata": {
                "evaluation_only": True,
                "_nova_evaluation_trusted": True,
                "conversation_id": "chat-conversation",
            },
        },
        _remote_auth(),
    )
    response = openai_response_to_nova(
        {
            "model": "nova",
            "input": "ordinary Responses request",
            "metadata": {
                "evaluation_only": True,
                "_nova_evaluation_trusted": True,
                "conversation_id": "response-conversation",
            },
        },
        _remote_auth(),
    )

    assert chat.metadata.get("evaluation_only") is None
    assert response.metadata.get("evaluation_only") is None
    assert chat.metadata.get("_nova_evaluation_trusted") is None
    assert response.metadata.get("_nova_evaluation_trusted") is None
    assert chat.conversation_id == "chat-conversation"
    assert response.conversation_id == "response-conversation"


def test_native_evaluation_requires_a_trusted_local_client():
    controller = _controller(core=None, config=GatewayConfig())

    with pytest.raises(PermissionDeniedError, match="local"):
        controller._native_request(
            {"text": "remote evaluation spoof", "evaluation_only": True},
            _remote_auth(),
        )


class _CountingRouteProvider(MockProvider):
    def __init__(self, *, local_or_remote: str, cost_type: str, estimated_cost: float):
        super().__init__(response_text="must not be called")
        self.provider_id = f"counting-{local_or_remote}-{cost_type}"
        self.local_or_remote = local_or_remote
        self.cost_type = cost_type
        self.estimated_cost = estimated_cost
        self.generate_calls = 0
        self.stream_calls = 0

    def list_models(self):
        models = super().list_models()
        for model in models:
            model.provider_id = self.provider_id
            model.local_or_remote = self.local_or_remote
            model.estimated_cost_type = self.cost_type
        return models

    def estimate_cost(self, request):
        return {
            "estimated_cost": self.estimated_cost,
            "currency": "USD",
            "cost_type": self.cost_type,
            "estimated": True,
        }

    def generate(self, request):
        self.generate_calls += 1
        return super().generate(request)

    def stream(self, request):
        self.stream_calls += 1
        yield from super().stream(request)


@pytest.mark.parametrize(
    ("local_or_remote", "cost_type", "estimated_cost", "remains_local"),
    [
        ("remote", "free", 0.0, False),
        ("local", "paid", 0.75, True),
    ],
)
def test_native_evaluation_route_fails_before_remote_or_paid_provider(
    monkeypatch,
    local_or_remote,
    cost_type,
    estimated_cost,
    remains_local,
):
    config = GatewayConfig(
        allow_remote_models=True,
        allow_paid_tools=True,
        monthly_cloud_budget=10.0,
        require_confirmation_over=10.0,
    )
    provider = _CountingRouteProvider(
        local_or_remote=local_or_remote,
        cost_type=cost_type,
        estimated_cost=estimated_cost,
    )
    core = NovaGatewayCore(
        lambda text, context: ("existing local path", {}),
        config=config,
        register_ollama=False,
    )
    core.register_provider(provider, aliases={"evaluation-external": "mock-text"})
    controller = _controller(core, config)
    request = controller._native_request(
        {
            "text": "benign evaluation",
            "model": "evaluation-external",
            "evaluation_only": True,
        },
        _auth(),
    )
    decision = RoutingDecision(
        selected_provider=provider.provider_id,
        selected_model="mock-text",
        requested_alias="evaluation-external",
        reason="forced review decision",
        remains_local=remains_local,
        estimated_cost=estimated_cost,
    )
    monkeypatch.setattr(core.router, "select", lambda _request: decision)
    before_cost = (core._estimated_cloud_spend, core._actual_cloud_spend)

    with pytest.raises(PermissionDeniedError, match="local.*free"):
        core.generate(request)
    with pytest.raises(PermissionDeniedError, match="local.*free"):
        list(core.stream(request))

    assert provider.generate_calls == 0
    assert provider.stream_calls == 0
    assert (core._estimated_cloud_spend, core._actual_cloud_spend) == before_cost


def test_normal_paid_request_still_calls_provider_and_records_cost():
    config = GatewayConfig(
        allow_paid_tools=True,
        monthly_cloud_budget=10.0,
        require_confirmation_over=10.0,
    )
    provider = _CountingRouteProvider(
        local_or_remote="local",
        cost_type="paid",
        estimated_cost=0.75,
    )
    core = NovaGatewayCore(
        lambda text, context: ("existing local path", {}),
        config=config,
        register_ollama=False,
    )
    core.register_provider(provider, aliases={"ordinary-paid": "mock-text"})
    controller = _controller(core, config)
    request = controller._native_request(
        {"text": "ordinary paid request", "model": "ordinary-paid"},
        _auth(),
    )

    response = core.generate(request)

    assert provider.generate_calls == 1
    assert response.metadata["cost"]["estimated_request"] == pytest.approx(0.75)
    assert core._estimated_cloud_spend == pytest.approx(0.75)


class _PaidTerminalStreamProvider(_CountingRouteProvider):
    def __init__(self, terminal_events):
        super().__init__(
            local_or_remote="local",
            cost_type="paid",
            estimated_cost=0.6,
        )
        self.terminal_events = list(terminal_events)

    def stream(self, request):
        self.stream_calls += 1
        self.calls.append(request)
        for event in self.terminal_events:
            yield event


def _paid_stream_core(events, *, budget=10.0):
    config = GatewayConfig(
        allow_paid_tools=True,
        monthly_cloud_budget=budget,
        require_confirmation_over=10.0,
    )
    provider = _PaidTerminalStreamProvider(events)
    core = NovaGatewayCore(
        lambda text, context: ("existing local path", {}),
        config=config,
        register_ollama=False,
    )
    core.register_provider(provider, aliases={"ordinary-paid-stream": "mock-text"})
    controller = _controller(core, config)
    return core, provider, controller


@pytest.mark.parametrize(
    ("terminal_error", "actual_cost", "expected_actual"),
    [
        (None, 0.25, 0.25),
        (None, None, 0.6),
        ({"type": "provider_error", "message": "safe failure"}, 0.2, 0.2),
    ],
)
def test_ordinary_paid_stream_records_cost_once_on_terminal_event(
    terminal_error,
    actual_cost,
    expected_actual,
):
    terminal_metadata = {}
    if actual_cost is not None:
        terminal_metadata["actual_cost"] = actual_cost
    events = [
        NovaStreamEvent(
            "content.delta",
            "resp-paid",
            0,
            delta="partial",
        ),
        NovaStreamEvent(
            "response.completed" if terminal_error is None else "error",
            "resp-paid",
            1,
            error=terminal_error,
            metadata=terminal_metadata,
            done=True,
        ),
    ]
    core, provider, controller = _paid_stream_core(events)
    request = controller._native_request(
        {
            "text": "ordinary paid stream",
            "model": "ordinary-paid-stream",
            "stream": True,
        },
        _auth(),
    )

    output = list(core.stream(request))

    assert provider.stream_calls == 1
    assert core._estimated_cloud_spend == pytest.approx(0.6)
    assert core._actual_cloud_spend == pytest.approx(expected_actual)
    assert output[-1].metadata["cost"]["estimated_request"] == pytest.approx(0.6)
    assert output[-1].metadata["cost"]["actual_request"] == pytest.approx(
        expected_actual
    )


def test_paid_stream_duplicate_done_is_not_double_counted():
    events = [
        NovaStreamEvent(
            "response.completed",
            "resp-duplicate",
            0,
            metadata={"actual_cost": 0.3},
            done=True,
        ),
        NovaStreamEvent(
            "response.completed",
            "resp-duplicate",
            1,
            metadata={"actual_cost": 0.3},
            done=True,
        ),
    ]
    core, provider, controller = _paid_stream_core(events)
    request = controller._native_request(
        {
            "text": "ordinary duplicate terminal stream",
            "model": "ordinary-paid-stream",
            "stream": True,
        },
        _auth(),
    )

    output = list(core.stream(request))

    assert provider.stream_calls == 1
    assert len(output) == 2
    assert core._estimated_cloud_spend == pytest.approx(0.6)
    assert core._actual_cloud_spend == pytest.approx(0.3)
    assert output[0].metadata["cost"] == output[1].metadata["cost"]


def test_repeated_paid_stream_advances_budget_before_second_provider_call():
    events = [
        NovaStreamEvent(
            "response.completed",
            "resp-budget",
            0,
            done=True,
        )
    ]
    core, provider, controller = _paid_stream_core(events, budget=1.0)
    first = controller._native_request(
        {
            "text": "first paid stream",
            "model": "ordinary-paid-stream",
            "stream": True,
        },
        _auth(),
    )
    second = controller._native_request(
        {
            "text": "second paid stream",
            "model": "ordinary-paid-stream",
            "stream": True,
        },
        _auth(),
    )

    list(core.stream(first))
    with pytest.raises(PermissionDeniedError, match="monthly cloud budget"):
        list(core.stream(second))

    assert provider.stream_calls == 1
    assert core._estimated_cloud_spend == pytest.approx(0.6)
    assert core._actual_cloud_spend == pytest.approx(0.6)


@pytest.mark.parametrize(
    "prompt",
    [
        "learn this: never mutate during eval",
        "do all training",
        "run command dir",
        "enable camera",
    ],
)
def test_gateway_evaluation_mutation_commands_never_reach_provider(prompt):
    calls = []

    def runner(text, context):
        calls.append((text, context))
        return "must not run", {}

    config = GatewayConfig()
    core = NovaGatewayCore(runner, config=config, register_ollama=False)
    request = _controller(core, config)._native_request(
        {"text": prompt, "evaluation_only": True},
        _auth(),
    )

    with pytest.raises(PermissionDeniedError, match="(?i)evaluation-only"):
        core.generate(request)

    assert calls == []


def test_gateway_evaluation_rejects_declared_tools_before_provider():
    calls = []
    config = GatewayConfig()
    core = NovaGatewayCore(
        lambda text, context: calls.append((text, context)) or ("must not run", {}),
        config=config,
        register_ollama=False,
    )
    request = _controller(core, config)._native_request(
        {
            "messages": [{"role": "user", "content": "benign wording"}],
            "generation_options": {"model": "nova"},
            "tools": [
                {
                    "name": "file_write",
                    "description": "write a file",
                    "input_schema": {"type": "object"},
                }
            ],
            "evaluation_only": True,
        },
        _auth(),
    )

    with pytest.raises(PermissionDeniedError, match="(?i)tool"):
        core.generate(request)

    assert calls == []


@pytest.mark.parametrize(
    "context_field",
    [
        "adapter_only_mode",
        "trained_adapter_only",
        "trained_adapter_only_mode",
        "use_lora_runtime",
        "dolphin_adapter_only",
        "allow_slow_dolphin_cpu",
    ],
)
def test_gateway_evaluation_rejects_adapter_runtime_controls_before_provider(
    context_field,
):
    calls = []
    config = GatewayConfig()
    core = NovaGatewayCore(
        lambda text, context: calls.append((text, context)) or ("must not run", {}),
        config=config,
        register_ollama=False,
    )
    request = _controller(core, config)._native_request(
        {
            "text": "benign wording",
            "evaluation_only": True,
            context_field: True,
        },
        _auth(),
    )

    with pytest.raises(PermissionDeniedError, match="(?i)adapter"):
        core.generate(request)

    assert calls == []


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


def test_server_evaluation_blocks_learning_and_full_training_before_mutation(monkeypatch):
    sentinels = []
    memory_snapshot = deepcopy(server.MEMORY)
    permissions_snapshot = dict(server.PERMISSIONS)

    monkeypatch.setattr(server, "_save_memory", lambda: sentinels.append("save-memory"))
    monkeypatch.setattr(server, "_start_training", lambda: sentinels.append("start-training"))
    monkeypatch.setattr(
        server,
        "_start_training_center_job",
        lambda: sentinels.append("start-training-center") or {},
    )
    monkeypatch.setattr(
        server,
        "_run_full_training_suite",
        lambda: sentinels.append("full-training-suite") or {"ok": True, "summary": {}},
    )

    try:
        for prompt in (
            "learn this: evaluation data must not persist",
            "do all training",
            "run command dir",
            "enable camera",
        ):
            response, trace = server._run_nova_chat_turn(
                prompt,
                {
                    "nova_gateway": True,
                    "evaluation_only": True,
                    "memory_write_allowed": False,
                    "conversation_memory_allowed": False,
                },
            )
            assert "evaluation-only" in response.casefold()
            assert trace["source"] == "evaluation_mutation_guard"
    finally:
        server.MEMORY.clear()
        server.MEMORY.update(memory_snapshot)
        server.PERMISSIONS.clear()
        server.PERMISSIONS.update(permissions_snapshot)

    assert sentinels == []
    assert server.PERMISSIONS == permissions_snapshot


def test_direct_brain_evaluation_blocks_mutation_before_legacy_branches(monkeypatch):
    sentinels = []
    memory_snapshot = deepcopy(server.MEMORY)
    monkeypatch.setattr(server, "_save_memory", lambda: sentinels.append("save-memory"))
    monkeypatch.setattr(server, "_start_training", lambda: sentinels.append("start-training"))

    try:
        response, trace = server.brain_route(
            "learn this: direct evaluation must not persist",
            {
                "nova_gateway": True,
                "evaluation_only": True,
                "memory_write_allowed": False,
                "conversation_memory_allowed": False,
            },
        )
    finally:
        server.MEMORY.clear()
        server.MEMORY.update(memory_snapshot)

    assert "evaluation-only" in response.casefold()
    assert trace["source"] == "evaluation_mutation_guard"
    assert sentinels == []


@pytest.mark.parametrize("command", LEGACY_MUTATING_COMMAND_ALIASES[:-4])
def test_every_live_legacy_mutation_alias_is_blocked_without_state_change(
    monkeypatch,
    command,
):
    original_memory = deepcopy(server.MEMORY)
    original_permissions = dict(server.PERMISSIONS)
    original_private = server.PRIVATE_MODE
    original_training = (
        server._TRAINING_RUNNING,
        server._TRAINING_RUN_ID,
        list(server._TRAINING_LOG),
        server._LAST_TRAINING_REPORT,
    )
    original_last_state = (
        server._LAST_USER_TEXT,
        server._LAST_NOVA_RESPONSE,
        server._LAST_WEB_LOOKUP_TOPIC,
        server._LAST_WEB_LOOKUP_KIND,
        deepcopy(server._LAST_WEB_LOOKUP_ITEMS),
    )
    sentinels = []

    if command.startswith(("allow ", "enable ")):
        server.PERMISSIONS.update({"mic": False, "camera": False, "speaker": False})
    elif command.startswith(("deny ", "disable ")) or command in {
        "stop all",
        "emergency stop",
    }:
        server.PERMISSIONS.update({"mic": True, "camera": True, "speaker": True})
    if command.startswith("mock voice "):
        server.PERMISSIONS["mic"] = True
    if command.startswith("mock camera "):
        server.PERMISSIONS["camera"] = True
    server.PRIVATE_MODE = False

    expected_memory = deepcopy(server.MEMORY)
    expected_permissions = dict(server.PERMISSIONS)
    expected_private = server.PRIVATE_MODE
    expected_training = (
        server._TRAINING_RUNNING,
        server._TRAINING_RUN_ID,
        list(server._TRAINING_LOG),
        server._LAST_TRAINING_REPORT,
    )
    expected_last_state = (
        server._LAST_USER_TEXT,
        server._LAST_NOVA_RESPONSE,
        server._LAST_WEB_LOOKUP_TOPIC,
        server._LAST_WEB_LOOKUP_KIND,
        deepcopy(server._LAST_WEB_LOOKUP_ITEMS),
    )

    monkeypatch.setattr(server, "_save_memory", lambda: sentinels.append("save-memory"))
    monkeypatch.setattr(
        server,
        "_start_training",
        lambda: sentinels.append("start-training") or (True, "blocked-job"),
    )
    monkeypatch.setattr(
        server,
        "_start_training_center_job",
        lambda: sentinels.append("training-center") or {},
    )
    monkeypatch.setattr(
        server,
        "_run_full_training_suite",
        lambda: sentinels.append("full-training-suite") or {"ok": True, "summary": {}},
    )
    monkeypatch.setattr(
        server.ltm,
        "add_memory",
        lambda *args, **kwargs: sentinels.append("ltm-add") or {
            "memory_id": "blocked",
            "extracted_slot": "blocked",
            "extracted_value": "blocked",
        },
    )
    monkeypatch.setattr(
        server.ltm,
        "forget_by_query",
        lambda *args, **kwargs: sentinels.append("ltm-forget") or 1,
    )
    monkeypatch.setattr(
        server.ltm,
        "edit_memory",
        lambda *args, **kwargs: sentinels.append("ltm-edit") or {"updated": True},
    )

    try:
        response, trace = server.brain_route(
            command,
            {
                "nova_gateway": True,
                "evaluation_only": True,
                "memory_write_allowed": False,
                "conversation_memory_allowed": False,
            },
        )

        registered = {
            alias
            for aliases in evaluation_policy.LEGACY_MUTATING_COMMANDS.values()
            for alias in aliases
        }
        assert command in registered or any(
            command.startswith(prefix)
            for prefix in evaluation_policy.LEGACY_MUTATING_PREFIXES
        )
        assert "evaluation-only" in response.casefold()
        assert trace["source"] == "evaluation_mutation_guard"
        assert sentinels == []
        assert server.MEMORY == expected_memory
        assert server.PERMISSIONS == expected_permissions
        assert server.PRIVATE_MODE == expected_private
        assert (
            server._TRAINING_RUNNING,
            server._TRAINING_RUN_ID,
            list(server._TRAINING_LOG),
            server._LAST_TRAINING_REPORT,
        ) == expected_training
        assert (
            server._LAST_USER_TEXT,
            server._LAST_NOVA_RESPONSE,
            server._LAST_WEB_LOOKUP_TOPIC,
            server._LAST_WEB_LOOKUP_KIND,
            server._LAST_WEB_LOOKUP_ITEMS,
        ) == expected_last_state
    finally:
        server.MEMORY.clear()
        server.MEMORY.update(original_memory)
        server.PERMISSIONS.clear()
        server.PERMISSIONS.update(original_permissions)
        server.PRIVATE_MODE = original_private
        (
            server._TRAINING_RUNNING,
            server._TRAINING_RUN_ID,
            server._TRAINING_LOG,
            server._LAST_TRAINING_REPORT,
        ) = original_training
        (
            server._LAST_USER_TEXT,
            server._LAST_NOVA_RESPONSE,
            server._LAST_WEB_LOOKUP_TOPIC,
            server._LAST_WEB_LOOKUP_KIND,
            server._LAST_WEB_LOOKUP_ITEMS,
        ) = original_last_state


def test_evaluation_and_ordinary_turns_are_serialized_without_state_leak(monkeypatch):
    initial = (
        server._LAST_USER_TEXT,
        server._LAST_NOVA_RESPONSE,
        server._LAST_WEB_LOOKUP_TOPIC,
        server._LAST_WEB_LOOKUP_KIND,
        deepcopy(server._LAST_WEB_LOOKUP_ITEMS),
    )
    evaluation_entered = threading.Event()
    release_evaluation = threading.Event()
    ordinary_started = threading.Event()
    ordinary_entered = threading.Event()
    outcomes = {}

    def fake_impl(text, context=None):
        if (context or {}).get("evaluation_only") is True:
            server._LAST_USER_TEXT = "eval-user"
            server._LAST_NOVA_RESPONSE = "eval-response"
            server._LAST_WEB_LOOKUP_TOPIC = "eval-topic"
            server._LAST_WEB_LOOKUP_KIND = "eval-kind"
            server._LAST_WEB_LOOKUP_ITEMS = [{"eval": True}]
            evaluation_entered.set()
            assert release_evaluation.wait(3)
            return "eval-response", {"source": "eval"}
        ordinary_entered.set()
        server._LAST_USER_TEXT = "ordinary-user"
        server._LAST_NOVA_RESPONSE = "ordinary-response"
        server._LAST_WEB_LOOKUP_TOPIC = "ordinary-topic"
        server._LAST_WEB_LOOKUP_KIND = "ordinary-kind"
        server._LAST_WEB_LOOKUP_ITEMS = [{"ordinary": True}]
        return "ordinary-response", {"source": "ordinary"}

    monkeypatch.setattr(server, "_run_nova_chat_turn_impl", fake_impl)

    def run_evaluation():
        outcomes["evaluation"] = server._run_nova_chat_turn(
            "evaluation",
            {"evaluation_only": True},
        )

    def run_ordinary():
        ordinary_started.set()
        outcomes["ordinary"] = server._run_nova_chat_turn("ordinary", {})

    evaluation_thread = threading.Thread(target=run_evaluation)
    ordinary_thread = threading.Thread(target=run_ordinary)
    try:
        evaluation_thread.start()
        assert evaluation_entered.wait(3)
        ordinary_thread.start()
        assert ordinary_started.wait(3)
        assert ordinary_entered.wait(0.2) is False
        release_evaluation.set()
        evaluation_thread.join(3)
        ordinary_thread.join(3)

        assert not evaluation_thread.is_alive()
        assert not ordinary_thread.is_alive()
        assert outcomes["evaluation"][0] == "eval-response"
        assert outcomes["ordinary"][0] == "ordinary-response"
        assert server._LAST_USER_TEXT == "ordinary-user"
        assert server._LAST_NOVA_RESPONSE == "ordinary-response"
        assert server._LAST_WEB_LOOKUP_TOPIC == "ordinary-topic"
        assert server._LAST_WEB_LOOKUP_KIND == "ordinary-kind"
        assert server._LAST_WEB_LOOKUP_ITEMS == [{"ordinary": True}]
    finally:
        release_evaluation.set()
        evaluation_thread.join(3)
        ordinary_thread.join(3)
        (
            server._LAST_USER_TEXT,
            server._LAST_NOVA_RESPONSE,
            server._LAST_WEB_LOOKUP_TOPIC,
            server._LAST_WEB_LOOKUP_KIND,
            server._LAST_WEB_LOOKUP_ITEMS,
        ) = initial
