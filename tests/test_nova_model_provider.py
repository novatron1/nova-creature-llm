from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import json
import socket
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_model_provider import (
    ExistingConnectorProvider,
    MockModelProvider,
    ModelGenerationRequest,
    NovaModelProviderRegistry,
    OpenAICompatibleLocalProvider,
    provider_registry_from_environment,
)


def test_mock_provider_implements_full_provider_contract():
    provider = MockModelProvider("deterministic")
    request = ModelGenerationRequest(
        prompt="test",
        reasoning_enabled=True,
        reasoning_mode="verify",
    )
    result = provider.generate(request)

    assert result.text == "deterministic"
    assert result.reasoning_used is True
    assert provider.supports_reasoning() is True
    assert provider.supports_tools() is True
    assert provider.supports_structured_output() is True
    assert provider.supports_vision() is False
    assert provider.get_context_limit() == 32768
    assert provider.count_tokens("abcd") >= 1


def test_provider_registry_switches_without_changing_request_contract():
    first = MockModelProvider("first", "model-a")
    second = MockModelProvider("second", "model-b")
    registry = NovaModelProviderRegistry()
    registry.register(first, default=True)
    assert registry.get().generate(ModelGenerationRequest("x")).text == "first"

    registry.register(second)
    assert registry.get().generate(ModelGenerationRequest("x")).text == "second"


def test_openai_compatible_provider_rejects_remote_endpoint_by_default():
    import pytest

    with pytest.raises(ValueError, match="Remote model providers are disabled"):
        OpenAICompatibleLocalProvider(
            base_url="https://provider.example",
            model_id="model",
        )


def test_openai_compatible_local_provider_generates_and_strips_reasoning(monkeypatch):
    import io
    import json
    import urllib.request

    observed = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=None):
        observed["payload"] = json.loads(request.data.decode("utf-8"))
        observed["timeout"] = timeout
        return Response(
            json.dumps(
                {
                    "model": "local",
                    "choices": [
                        {
                            "message": {
                                "content": "<think>private</think>Visible answer."
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "nova_model_provider.open_without_redirects",
        fake_urlopen,
        raising=False,
    )
    provider = OpenAICompatibleLocalProvider(
        base_url="http://127.0.0.1:8000",
        model_id="qwen3-local",
    )
    result = provider.generate(
        ModelGenerationRequest(
            prompt="Explain it.",
            reasoning_enabled=True,
            reasoning_mode="deep",
        )
    )

    assert observed["payload"]["messages"][0]["content"].startswith("/think")
    assert result.text == "Visible answer."
    assert result.metadata["reasoning_content_stored"] is False


def test_openai_compatible_provider_never_forwards_bearer_across_redirect():
    source_authorization = []
    target_authorization = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            target_authorization.append(self.headers.get("Authorization"))
            payload = json.dumps({"data": [{"id": "redirected-model"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            source_authorization.append(self.headers.get("Authorization"))
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{target.server_port}/stolen",
            )
            self.end_headers()

        def log_message(self, *_args):
            pass

    source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    threads = [
        threading.Thread(target=target.serve_forever, daemon=True),
        threading.Thread(target=source.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        provider = OpenAICompatibleLocalProvider(
            base_url=f"http://127.0.0.1:{source.server_port}",
            model_id="fallback-model",
            api_key="DUMMY-REDIRECT-TOKEN",
        )

        assert provider.list_models() == ["fallback-model"]
        assert source_authorization == ["Bearer DUMMY-REDIRECT-TOKEN"]
        assert target_authorization == []
    finally:
        source.shutdown()
        target.shutdown()
        source.server_close()
        target.server_close()
        for thread in threads:
            thread.join(timeout=2)


def test_verified_public_provider_requires_current_exact_host_allowlist(monkeypatch):
    monkeypatch.delenv("NOVA_GPU_HUB_REMOTE_MODEL_ALLOWLIST", raising=False)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )

    import pytest

    with pytest.raises(ValueError, match="approved"):
        provider_registry_from_environment(
            settings={"NOVA_MODEL_PROVIDER": "existing"},
            gpu_hub_state={
                "mode": "vast_gpu",
                "effective_mode": "vast_gpu",
                "available": True,
                "verified": True,
                "verified_backend": "vast_gpu",
                "endpoint": {
                    "url": "https://worker.example",
                    "model": "qwen3",
                    "provider": "vllm",
                },
            },
        )


def test_runtime_gpu_mode_selects_verified_openai_compatible_provider(monkeypatch):
    monkeypatch.setenv("NOVA_GPU_HUB_REMOTE_MODEL_ALLOWLIST", "worker.example")
    registry = provider_registry_from_environment(
        settings={"NOVA_MODEL_PROVIDER": "existing"},
        gpu_hub_state={
            "mode": "vast_gpu",
            "effective_mode": "vast_gpu",
            "available": True,
            "verified": True,
            "verified_backend": "vast_gpu",
            "endpoint": {
                "url": "https://worker.example",
                "model": "qwen3",
                "provider": "vllm",
            },
        },
    )

    provider = registry.get()
    assert isinstance(provider, OpenAICompatibleLocalProvider)
    assert provider.base_url == "https://worker.example"
    assert provider.model_id == "qwen3"


def test_explicit_local_gpu_cannot_route_to_verified_vast_endpoint():
    import pytest

    with pytest.raises(RuntimeError, match="unavailable"):
        provider_registry_from_environment(
            settings={"NOVA_MODEL_PROVIDER": "existing"},
            gpu_hub_state={
                "mode": "local_gpu",
                "effective_mode": "local_gpu",
                "available": False,
                "verified": False,
                "verified_backend": "vast_gpu",
                "reason": "Verified endpoint belongs to vast_gpu.",
                "endpoint": {
                    "url": "https://worker.example",
                    "model": "qwen3",
                    "provider": "vllm",
                },
            },
        )


def test_provider_overlay_requires_backend_to_match_effective_status():
    from nova_model_provider import build_gpu_hub_provider_settings

    ordinary = {"NOVA_MODEL_PROVIDER": "existing"}
    settings = build_gpu_hub_provider_settings(
        {
            "mode": "local_gpu",
            "effective_mode": "local_gpu",
            "available": True,
            "verified": True,
            "verified_backend": "vast_gpu",
            "endpoint": {
                "url": "https://worker.example",
                "model": "qwen3",
                "provider": "vllm",
            },
        },
        ordinary,
    )

    assert settings == ordinary


def test_runtime_cpu_mode_keeps_connector_and_forces_cpu_options():
    class Config:
        fast_model = "fast"
        deep_model = "deep"
        model = "normal"
        context_window = 4096
        provider = "ollama"

    class Connector:
        config = Config()

    provider = provider_registry_from_environment(
        connector=Connector(),
        settings={"NOVA_MODEL_PROVIDER": "existing"},
        gpu_hub_state={
            "mode": "cpu",
            "effective_mode": "cpu",
            "available": True,
            "verified": False,
        },
    ).get()

    assert isinstance(provider, ExistingConnectorProvider)
    context = provider._context(ModelGenerationRequest(prompt="hello"))
    assert context["ollama_options"]["num_gpu"] == 0


def test_explicit_unavailable_gpu_mode_does_not_fall_back_to_connector():
    import pytest

    with pytest.raises(RuntimeError, match="unavailable"):
        provider_registry_from_environment(
            settings={"NOVA_MODEL_PROVIDER": "existing"},
            gpu_hub_state={
                "mode": "local_gpu",
                "effective_mode": "local_gpu",
                "available": False,
                "verified": False,
                "reason": "No verified local GPU endpoint.",
            },
        )
