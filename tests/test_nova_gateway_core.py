from __future__ import annotations

from pathlib import Path
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway import (  # noqa: E402
    ExistingNovaProvider,
    GatewayConfig,
    MockProvider,
    NovaModelRegistry,
    NovaProviderRegistry,
    NovaTaskRouter,
    OllamaProvider,
    PROVIDER_INTERFACE_VERSION,
)
from nova_gateway.errors import (  # noqa: E402
    ModelUnavailableError,
    PermissionDeniedError,
    ProviderUnavailableError,
)
from nova_gateway.core import NovaGatewayCore  # noqa: E402
from nova_gateway.version import NOVA_VERSION  # noqa: E402
from nova_protocol import NovaAttachment, NovaGenerationOptions, NovaMessage, NovaRequest  # noqa: E402


def make_request(**overrides) -> NovaRequest:
    values = {
        "request_id": "req_test",
        "conversation_id": "conv_test",
        "messages": [NovaMessage(role="user", content="Hello Nova")],
        "generation_options": NovaGenerationOptions(model="nova"),
    }
    values.update(overrides)
    return NovaRequest(**values)


def test_gateway_version_has_one_shared_source_of_truth() -> None:
    from nova_gateway.core import NOVA_VERSION as core_version
    from nova_gateway.portability import NovaPortableManifest

    assert core_version == NOVA_VERSION
    assert NovaPortableManifest().nova_version == NOVA_VERSION
    assert NovaPortableManifest().provider_interface_version == PROVIDER_INTERFACE_VERSION


def test_existing_nova_provider_wraps_real_turn_contract_without_flattening_request() -> None:
    observed = {}

    def runner(text, context):
        observed["text"] = text
        observed["context"] = context
        return "Nova core answer", {"route": "cognitive_os"}

    provider = ExistingNovaProvider(runner)
    request = make_request(
        messages=[
            NovaMessage(role="system", content="Client preference"),
            NovaMessage(role="developer", content="Use concise formatting"),
            NovaMessage(role="user", content="Hello Nova"),
        ],
        metadata={"client_scopes": ["chat.generate", "memory.read"]},
    )

    response = provider.generate(request)

    assert response.content == "Nova core answer"
    assert response.provider == "existing-nova"
    assert response.metadata["identity_preserved"] is True
    assert observed["text"] == "Hello Nova"
    assert [item["role"] for item in observed["context"]["nova_request"]["messages"]] == [
        "system",
        "developer",
        "user",
    ]
    assert observed["context"]["client_scopes"] == ["chat.generate", "memory.read"]


def test_gateway_core_updates_world_model_and_attaches_safe_summary() -> None:
    observed = {}

    def runner(text, context):
        observed["world_model"] = context["world_model"]
        observed["dream_lab"] = context["dream_lab"]
        return "Use this exact wording with her.", {
            "source": "relationship_coaching",
            "final_answer_source": "relationship_coaching",
        }

    core = NovaGatewayCore(runner, config=GatewayConfig(), register_ollama=False)
    request = make_request(
        client_id="world_phone",
        conversation_id="world_conv",
        messages=[NovaMessage(role="user", content="What should I say to my girlfriend?")],
    )

    response = core.generate(request)

    assert observed["world_model"]["status"] == "working"
    assert observed["world_model"]["current_topic"] == "relationship"
    assert observed["dream_lab"]["selected_strategy"] == "direct_nova_core"
    assert observed["dream_lab"]["prompt_content_stored"] is False
    assert response.metadata["world_model"]["status"] == "idle"
    assert response.metadata["dream_lab"]["executed_actions"] is False
    assert response.metadata["world_model"]["goal_status"] == "completed"
    assert response.metadata["trace"]["world_model"]["route_state"]["answer_source"] == "relationship_coaching"
    assert core.health()["world_model"]["private_chain_of_thought_stored"] is False


def test_gateway_core_stream_completes_world_model_without_buffer_duplication() -> None:
    def runner(text, context):
        assert context["world_model"]["status"] == "working"
        context["stream_callback"]("Nova ")
        context["stream_callback"]("remembers the thread.")
        return "Nova remembers the thread.", {
            "source": "qwen_contextual_synthesis",
            "native_streaming": True,
        }

    core = NovaGatewayCore(runner, config=GatewayConfig(), register_ollama=False)
    request = make_request(
        client_id="stream_phone",
        conversation_id="stream_world_conv",
        messages=[NovaMessage(role="user", content="Can you follow what we are talking about?")],
        generation_options=NovaGenerationOptions(model="nova", stream=True),
    )

    events = list(core.stream(request))

    assert "".join(event.delta for event in events) == "Nova remembers the thread."
    assert events[-1].done is True
    assert events[-1].metadata["world_model"]["status"] == "idle"
    assert events[-1].metadata["world_model"]["route_state"]["answer_source"] == "qwen_contextual_synthesis"
    state = core.world_model.view("stream_phone", "stream_world_conv")["data"]
    assert state["turn_count"] == 1
    assert state["goal_status"] == "completed"


def test_existing_nova_provider_stream_uses_cognitive_callback_and_reconstructs() -> None:
    observed = {}

    def runner(text, context):
        observed["text"] = text
        observed["context"] = context
        assert context["stream_callback"]("Nova ") is True
        assert context["stream_callback"]("streams safely.") is True
        return "Nova streams safely.", {"route": "cognitive_os", "native_streaming": True}

    provider = ExistingNovaProvider(runner)
    request = make_request(generation_options=NovaGenerationOptions(model="nova", stream=True))

    events = list(provider.stream(request))

    assert "".join(event.delta for event in events) == "Nova streams safely."
    assert [event.sequence for event in events] == [0, 1, 2]
    assert events[-1].done is True
    assert events[-1].event_type == "response.completed"
    assert events[-1].metadata["trace"]["route"] == "cognitive_os"
    assert events[-1].metadata["request_id"] == "req_test"
    assert events[-1].metadata["conversation_id"] == "conv_test"
    assert observed["text"] == "Hello Nova"
    assert observed["context"]["native_streaming"] is True
    assert callable(observed["context"]["stream_cancelled"])


def test_existing_nova_provider_emits_heartbeat_while_slow_raw_turn_loads() -> None:
    def slow_runner(text, context):
        time.sleep(0.06)
        return "Raw adapter answer.", {"source": "raw_adapter_only"}

    provider = ExistingNovaProvider(slow_runner)
    provider._stream_heartbeat_seconds = 0.01
    request = make_request(generation_options=NovaGenerationOptions(model="nova", stream=True))

    events = list(provider.stream(request))

    heartbeats = [event for event in events if event.event_type == "response.heartbeat"]
    assert heartbeats
    assert all(event.delta == "" and event.done is False for event in heartbeats)
    assert "".join(event.delta for event in events) == "Raw adapter answer."
    assert events[-1].event_type == "response.completed"
    assert [event.sequence for event in events] == list(range(len(events)))


def test_existing_nova_provider_streams_content_free_named_progress() -> None:
    def runner(text, context):
        assert context["progress_callback"](
            "larger_local_review",
            "A larger free local model is loading or reviewing the answer.",
            58,
        ) is True
        return "Reviewed answer.", {"source": "answer_candidate_selector"}

    provider = ExistingNovaProvider(runner)
    events = list(
        provider.stream(
            make_request(generation_options=NovaGenerationOptions(model="nova", stream=True))
        )
    )

    progress = next(event for event in events if event.event_type == "response.progress")
    assert progress.metadata["stage"] == "larger_local_review"
    assert progress.metadata["percent"] == 58
    assert progress.metadata["content_logged"] is False
    assert progress.delta == ""
    assert "".join(event.delta for event in events) == "Reviewed answer."
    assert [event.sequence for event in events] == list(range(len(events)))


def test_existing_nova_provider_passes_only_allowlisted_desktop_context() -> None:
    observed = {}

    def runner(text, context):
        observed.update(context)
        return "Ready.", {"route": "desktop_context"}

    provider = ExistingNovaProvider(runner)
    request = make_request(
        metadata={
            "desktop_context": {
                "trained_adapter_only": True,
                "lora_adapter_id": "nova-test",
                "sensor_snapshot": {"enabled": True},
                "conversation_summary": {"schema_version": "1.0", "revision": 3},
                "conversation_summary_write_allowed": True,
                "lora_adapter_path": "C:/must-not-pass",
            }
        }
    )

    provider.generate(request)

    assert observed["trained_adapter_only"] is True
    assert observed["lora_adapter_id"] == "nova-test"
    assert observed["sensor_snapshot"] == {"enabled": True}
    assert observed["conversation_summary"]["revision"] == 3
    assert observed["conversation_summary_write_allowed"] is True
    assert "lora_adapter_path" not in observed


def test_existing_nova_provider_cancellation_stops_active_stream() -> None:
    def runner(text, context):
        context["stream_callback"]("Starting ")
        deadline = time.monotonic() + 2
        while not context["stream_cancelled"]() and time.monotonic() < deadline:
            time.sleep(0.001)
        return "Starting ", {"native_streaming": True}

    provider = ExistingNovaProvider(runner)
    request = make_request(
        request_id="req_cancel_stream",
        generation_options=NovaGenerationOptions(model="nova", stream=True),
    )
    stream = provider.stream(request)

    first = next(stream)
    assert first.delta == "Starting "
    assert provider.cancel(request.request_id) is True
    remaining = list(stream)

    assert remaining[-1].event_type == "response.cancelled"
    assert remaining[-1].done is True


def test_mock_provider_stream_is_incremental_ordered_and_reconstructs_full_answer() -> None:
    provider = MockProvider(response_text="Nova ready", chunks=["Nova", " ", "ready"])
    request = make_request(generation_options=NovaGenerationOptions(model="nova", stream=True))

    events = list(provider.stream(request))

    assert [event.sequence for event in events] == [0, 1, 2, 3]
    assert "".join(event.delta for event in events) == "Nova ready"
    assert events[-1].done is True
    assert events[-1].event_type == "response.completed"


def test_active_stream_cancellation_is_isolated_to_its_client_owner() -> None:
    provider = MockProvider(response_text="Owned stream", chunks=["Owned ", "stream"])
    core = NovaGatewayCore(
        lambda text, context: ("existing", {}),
        config=GatewayConfig(),
        register_ollama=False,
    )
    core.register_provider(provider, aliases={"nova-owned-stream": "mock-text"})
    request = make_request(
        request_id="req_owned_stream",
        client_id="phone-one",
        generation_options=NovaGenerationOptions(model="nova-owned-stream", stream=True),
    )
    stream = core.stream(request)

    assert next(stream).delta == "Owned "
    assert core.cancel(request.request_id, client_id="phone-two") is False
    assert request.request_id not in provider.cancelled
    assert core.cancel(request.request_id, client_id="phone-one") is True
    assert request.request_id in provider.cancelled
    stream.close()


def test_ollama_provider_honors_bounded_per_request_timeout_override() -> None:
    observed = {}

    class FakeConnector:
        config = type(
            "Config",
            (),
            {
                "url": "http://127.0.0.1:11434",
                "model": "local-test-model",
                "timeout": 8,
            },
        )()

        def _call_ollama(self, prompt, **kwargs):
            observed["prompt"] = prompt
            observed.update(kwargs)
            return type(
                "Result",
                (),
                {
                    "local_llm_used": True,
                    "error": "",
                    "fallback_reason": "",
                    "model": "local-test-model",
                    "raw_output": "Local answer.",
                    "response_time_ms": 12.0,
                    "finish_reason": "length",
                },
            )()

    provider = OllamaProvider(FakeConnector())
    response = provider.generate(make_request(metadata={"provider_timeout_seconds": 99}))

    assert observed["timeout_override"] == 60
    assert response.metadata["timeout_seconds"] == 60

    internal_response = provider.generate(
        make_request(
            generation_options=NovaGenerationOptions(model="nova", seed=0, stop=["END"]),
            metadata={
                "provider_timeout_seconds": 180,
                "provider_context_window": 99999,
                "internal_nova_managed": True,
                "candidate_retry": True,
            }
        )
    )

    assert observed["timeout_override"] == 180
    assert observed["options_override"]["num_ctx"] == 32768
    assert observed["options_override"]["seed"] == 0
    assert observed["options_override"]["stop"] == ["END"]
    assert observed["keep_alive_override"] == "30m"
    assert internal_response.metadata["timeout_seconds"] == 180
    assert internal_response.finish_reason == "length"
    assert internal_response.metadata["provider_done_reason"] == "length"


def test_ollama_provider_warms_installed_model_without_generating_text(monkeypatch) -> None:
    requests = []

    class FakeConnector:
        config = type(
            "Config",
            (),
            {
                "url": "http://127.0.0.1:11434",
                "model": "small-local",
                "timeout": 8,
                "ollama_keep_alive": "30m",
            },
        )()

    provider = OllamaProvider(FakeConnector())
    monkeypatch.setattr(
        provider,
        "list_models",
        lambda: [type("Capability", (), {"model_id": "large-local"})()],
    )

    def fake_json_request(path, *, payload=None, timeout=None):
        requests.append((path, payload, timeout))
        return {"done": True}

    monkeypatch.setattr(provider, "_json_request", fake_json_request)

    result = provider.warm_up_model("large-local", keep_alive="60m", timeout=45)

    assert result["ok"] is True
    assert result["state"] == "ready"
    assert requests == [
        (
            "/api/generate",
            {
                "model": "large-local",
                "prompt": "",
                "stream": False,
                "keep_alive": "60m",
                "options": {"num_predict": 0},
            },
            45,
        )
    ]
def test_provider_and_model_registries_resolve_public_aliases() -> None:
    provider = MockProvider()
    providers = NovaProviderRegistry(default_provider="mock")
    providers.register_provider(provider, aliases=["test"])
    models = NovaModelRegistry()
    for capability in provider.list_models():
        models.register_model(capability)
    models.register_alias("nova", "mock", "mock-text")

    assert providers.get_provider("test") is provider
    assert models.resolve_alias("nova").streaming is True
    assert models.find_by_capability("embeddings", "streaming")[0].model_id == "mock-text"
    assert providers.provider_health()["mock"]["ok"] is True

    providers.unregister_provider("mock")
    with pytest.raises(ProviderUnavailableError):
        providers.get_provider("mock")


def test_router_enforces_capabilities_and_local_only_policy() -> None:
    provider = MockProvider()
    providers = NovaProviderRegistry(default_provider="mock")
    providers.register_provider(provider)
    models = NovaModelRegistry()
    capability = provider.list_models()[0]
    capability.local_or_remote = "remote"
    provider.local_or_remote = "remote"
    models.register_model(capability)
    models.register_alias("nova", "mock", "mock-text")
    config = GatewayConfig(allow_remote_models=True)
    router = NovaTaskRouter(providers, models, config)

    with pytest.raises(PermissionDeniedError, match="local_only"):
        router.select(make_request(privacy_mode="local_only"))

    request = make_request(privacy_mode="remote_allowed")
    decision = router.select(request)
    assert decision.selected_provider == "mock"
    assert decision.remains_local is False


def test_router_rejects_unknown_or_incapable_model() -> None:
    provider = MockProvider()
    providers = NovaProviderRegistry(default_provider="mock")
    providers.register_provider(provider)
    models = NovaModelRegistry()
    capability = provider.list_models()[0]
    capability.image_output = False
    models.register_model(capability)
    models.register_alias("nova", "mock", "mock-text")
    router = NovaTaskRouter(providers, models, GatewayConfig())

    with pytest.raises(ModelUnavailableError, match="not available"):
        router.select(make_request(generation_options=NovaGenerationOptions(model="missing")))
    with pytest.raises(ModelUnavailableError, match="image_output"):
        router.select(make_request(requested_modalities=["image"]))


def test_gateway_config_environment_overrides_are_bounded_and_public_view_has_no_keys(tmp_path: Path) -> None:
    config = GatewayConfig.from_env(
        {
            "NOVA_API_ENABLED": "true",
            "NOVA_API_HOST": "0.0.0.0",
            "NOVA_API_PORT": "9001",
            "NOVA_ENABLE_REMOTE_ACCESS": "false",
            "NOVA_TRUST_TAILSCALE_SERVE": "true",
            "NOVA_RATE_LIMIT_PER_MINUTE": "200",
            "NOVA_MAX_REQUEST_SIZE": "4096",
            "NOVA_ALLOWED_ORIGINS": "http://phone.local, http://desktop.local",
            "NOVA_API_KEYS": "must-not-appear",
            "NOVA_WORLD_MODEL_PERSISTENCE": "checkpoint",
            "NOVA_WORLD_MODEL_PATH": "private/world-state.json",
            "NOVA_WORLD_MODEL_MAX_AGE_DAYS": "45",
            "NOVA_DREAM_LAB_ENABLED": "false",
            "NOVA_COMFYUI_ENABLED": "true",
            "NOVA_COMFYUI_BASE_URL": "http://127.0.0.1:8188",
            "NOVA_COMFYUI_IMAGE_WORKFLOW": "private/image-workflow.json",
            "NOVA_COMFYUI_VIDEO_WORKFLOW": "private/video-workflow.json",
            "NOVA_COMFYUI_JOB_STORE": "private/jobs.json",
            "NOVA_COMFYUI_TIMEOUT": "22",
        },
        root=tmp_path,
    )

    assert config.port == 9001
    assert config.trust_tailscale_serve is True
    assert config.rate_limit_per_minute == 200
    assert config.allowed_origins == ("http://phone.local", "http://desktop.local")
    assert config.client_registry_path == tmp_path / "data" / "nova_gateway_clients.json"
    assert config.world_model_persistence == "checkpoint"
    assert config.world_model_checkpoint_path == tmp_path / "private" / "world-state.json"
    assert config.world_model_max_age_days == 45
    assert config.dream_lab_enabled is False
    assert config.comfyui_enabled is True
    assert config.comfyui_image_workflow_path == tmp_path / "private" / "image-workflow.json"
    assert config.comfyui_video_workflow_path == tmp_path / "private" / "video-workflow.json"
    assert config.comfyui_job_store_path == tmp_path / "private" / "jobs.json"
    assert config.comfyui_timeout_seconds == 22
    assert "world-state.json" not in str(config.public_dict())
    assert "image-workflow.json" not in str(config.public_dict())
    assert "video-workflow.json" not in str(config.public_dict())
    assert "jobs.json" not in str(config.public_dict())
    assert "127.0.0.1" not in str(config.public_dict())
    assert "key" not in str(config.public_dict()).lower()
    assert config.public_dict()["trust_tailscale_serve"] is True


def test_gateway_config_discovers_machine_local_comfyui_image_workflow(tmp_path: Path) -> None:
    workflow = tmp_path / "config" / "comfyui_text_to_image_workflow.local.json"
    workflow.parent.mkdir(parents=True)
    workflow.write_text('{"1": {"class_type": "Mock"}}', encoding="utf-8")

    discovered = GatewayConfig.from_env({"UNRELATED": "1"}, root=tmp_path)
    explicit = GatewayConfig.from_env(
        {"NOVA_COMFYUI_IMAGE_WORKFLOW": "private/explicit.json"},
        root=tmp_path,
    )

    assert discovered.comfyui_image_workflow_path == workflow
    assert explicit.comfyui_image_workflow_path == tmp_path / "private" / "explicit.json"


class PaidRemoteMock(MockProvider):
    provider_id = "paid-remote"
    local_or_remote = "remote"
    cost_type = "paid"

    def list_models(self):
        models = super().list_models()
        for model in models:
            model.provider_id = self.provider_id
            model.local_or_remote = "remote"
            model.estimated_cost_type = "paid"
        return models

    def estimate_cost(self, request):
        return {"estimated_cost": 0.6, "currency": "USD", "cost_type": "paid", "estimated": True}


def test_remote_private_file_confirmation_and_monthly_budget_policies() -> None:
    provider = PaidRemoteMock("remote answer")
    providers = NovaProviderRegistry(default_provider="paid-remote")
    providers.register_provider(provider)
    models = NovaModelRegistry()
    models.register_model(provider.list_models()[0])
    models.register_alias("remote", "paid-remote", "mock-text")
    config = GatewayConfig(
        allow_remote_models=True,
        allow_paid_tools=True,
        allow_private_files_remote=False,
        monthly_cloud_budget=1.0,
        require_confirmation_over=10.0,
    )
    router = NovaTaskRouter(providers, models, config)
    with pytest.raises(PermissionDeniedError, match="private files"):
        router.select(
            make_request(
                generation_options=NovaGenerationOptions(model="remote"),
                privacy_mode="remote_allowed",
                attachments=[NovaAttachment(media_type="text/plain", source_type="local", local_path="private.txt")],
            )
        )

    confirmed_config = GatewayConfig(
        allow_remote_models=True,
        allow_paid_tools=True,
        allow_private_files_remote=True,
        monthly_cloud_budget=1.0,
        require_confirmation_over=0.5,
    )
    confirmed_router = NovaTaskRouter(providers, models, confirmed_config)
    with pytest.raises(PermissionDeniedError, match="confirmation"):
        confirmed_router.select(
            make_request(
                generation_options=NovaGenerationOptions(model="remote"),
                privacy_mode="remote_allowed",
            )
        )


def test_monthly_budget_is_checked_before_second_paid_request() -> None:
    config = GatewayConfig(
        allow_remote_models=True,
        allow_paid_tools=True,
        monthly_cloud_budget=1.0,
        require_confirmation_over=10.0,
    )
    gateway = NovaGatewayCore(lambda text, context: ("local", {}), config=config, register_ollama=False)
    gateway.register_provider(PaidRemoteMock("paid"), aliases={"remote": "mock-text"})

    def paid_request(request_id):
        return NovaRequest(
            request_id=request_id,
            messages=[NovaMessage(role="user", content="remote work")],
            generation_options=NovaGenerationOptions(model="remote"),
            privacy_mode="remote_allowed",
            metadata={"client_scopes": ["chat.generate"]},
        )

    first = gateway.generate(paid_request("req_paid_1"))
    assert first.metadata["cost"]["estimated_month_total"] == pytest.approx(0.6)
    with pytest.raises(PermissionDeniedError, match="monthly cloud budget"):
        gateway.generate(paid_request("req_paid_2"))
