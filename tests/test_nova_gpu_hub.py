from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

import pytest

from src.nova_gpu_hub import (
    ComputeMode,
    GpuHubController,
    GpuHubError,
    GpuHubStateStore,
    VastAIClient,
    detect_local_gpu,
)
from src.nova_model_provider import build_gpu_hub_provider_settings


def test_compute_modes_and_controller_reject_invalid_mode(tmp_path):
    controller = GpuHubController(tmp_path)
    assert controller.set_mode(ComputeMode.CPU)["mode"] == "cpu"
    assert controller.status()["mode"] == "cpu"
    with pytest.raises(ValueError):
        controller.set_mode("remote")


def test_missing_or_corrupt_state_recovers_to_auto(tmp_path):
    state_path = tmp_path / "state.json"
    store = GpuHubStateStore(state_path)
    assert store.load()["mode"] == "auto"
    state_path.write_text("not json", encoding="utf-8")
    assert store.load()["mode"] == "auto"


def test_state_save_redacts_secrets_and_is_reloadable(tmp_path):
    path = tmp_path / "state.json"
    store = GpuHubStateStore(path)
    saved = store.save({"mode": "vast_gpu", "selected_instance_id": "i-1", "endpoint": {"url": "http://10.0.0.2:8000", "api_key": "SECRET"}, "ignored": "x"})
    assert saved["mode"] == "vast_gpu"
    raw = path.read_text(encoding="utf-8")
    assert "SECRET" not in raw
    assert "ignored" not in raw
    assert store.load()["endpoint"]["url"] == "http://10.0.0.2:8000"


def test_state_persists_only_safe_verified_endpoint_metadata(tmp_path):
    path = tmp_path / "state.json"
    store = GpuHubStateStore(path)

    saved = store.save(
        {
            "mode": "vast_gpu",
            "selected_instance_id": "instance-7",
            "verified": True,
            "verified_backend": "vast_gpu",
            "verified_at": "2026-08-17T12:00:00+00:00",
            "endpoint": {
                "url": "https://worker.example/v1?token=SECRET",
                "model": "qwen3",
                "provider": "vllm",
                "api_key": "SECRET",
            },
        }
    )

    assert saved["verified"] is True
    assert saved["verified_backend"] == "vast_gpu"
    assert saved["verified_at"] == "2026-08-17T12:00:00+00:00"
    assert saved["selected_instance_id"] == "instance-7"
    assert saved["endpoint"] == {
        "url": "https://worker.example/v1",
        "model": "qwen3",
        "provider": "vllm",
    }
    assert "SECRET" not in path.read_text(encoding="utf-8")


def test_detect_local_gpu_parses_nvidia_smi_csv():
    def runner(_args):
        return "NVIDIA RTX 4090, 24576, 535.1\n"

    result = detect_local_gpu(runner=runner)
    assert result["available"] is True
    assert result["usable"] is True
    assert result["gpu_names"] == ["NVIDIA RTX 4090"]
    assert result["memory_mb"] == 24576
    assert result["driver"] == "535.1"
    assert result["backend"] == "nvidia"


def test_no_gpu_is_truthful_and_cpu_can_be_selected(monkeypatch, tmp_path):
    result = detect_local_gpu(runner=lambda _args: (_ for _ in ()).throw(FileNotFoundError()))
    assert result["available"] is False
    assert result["usable"] is False
    controller = GpuHubController(tmp_path, env={})
    controller.set_mode("local_gpu")
    assert controller.local_status()["usable"] is False
    assert controller.status()["mode"] == "local_gpu"


def test_vast_client_builds_bearer_request_and_normalizes_responses(monkeypatch):
    captured = {}

    class Response:
        status = 200

        def read(self):
            return json.dumps({"instances": [{"id": 3}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("src.nova_gpu_hub.urllib.request.urlopen", opener)
    monkeypatch.setattr("src.nova_gpu_hub.open_without_redirects", opener, raising=False)
    client = VastAIClient("SECRET", base_url="https://console.vast.ai/api/v0/")
    result = client.list_instances()
    assert result == [{"id": 3}]
    assert captured["url"] == "https://console.vast.ai/api/v0/instances/"
    assert captured["headers"]["Authorization"] == "Bearer SECRET"
    assert captured["timeout"] == 15


def test_vast_search_and_create_use_official_rest_shapes(monkeypatch):
    captured = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def opener(request, timeout):
        captured.append(
            {
                "method": request.get_method(),
                "url": request.full_url,
                "body": json.loads(request.data.decode()) if request.data else None,
                "timeout": timeout,
            }
        )
        payload = {"offers": [{"id": 41}]} if request.full_url.endswith("/bundles/") else {"new_contract": 73}
        return Response(payload)

    monkeypatch.setattr("src.nova_gpu_hub.urllib.request.urlopen", opener)
    monkeypatch.setattr("src.nova_gpu_hub.open_without_redirects", opener, raising=False)
    client = VastAIClient("SECRET", base_url="https://console.vast.ai/api/v0")

    assert client.search_offers({"gpu_name": {"eq": "RTX 4090"}}) == [{"id": 41}]
    assert client.create_instance(41, {"image": "vllm/vllm-openai"}, confirmed=True) == {
        "new_contract": 73
    }
    assert captured == [
        {
            "method": "POST",
            "url": "https://console.vast.ai/api/v0/bundles/",
            "body": {"gpu_name": {"eq": "RTX 4090"}},
            "timeout": 15,
        },
        {
            "method": "PUT",
            "url": "https://console.vast.ai/api/v0/asks/41/",
            "body": {"image": "vllm/vllm-openai"},
            "timeout": 15,
        },
    ]


def test_vast_errors_redact_api_key(monkeypatch):
    def opener(_request, timeout):
        raise OSError("failed SECRET")

    monkeypatch.setattr("src.nova_gpu_hub.urllib.request.urlopen", opener)
    monkeypatch.setattr("src.nova_gpu_hub.open_without_redirects", opener, raising=False)
    with pytest.raises(GpuHubError) as exc:
        VastAIClient("SECRET").list_instances()
    assert "SECRET" not in str(exc.value)
    assert "SECRET" not in repr(exc.value)


def test_vast_transport_never_forwards_bearer_across_redirect(monkeypatch):
    source_authorization = []
    target_authorization = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            target_authorization.append(self.headers.get("Authorization"))
            payload = json.dumps({"instances": [{"id": "redirect-target"}]}).encode()
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
    base_url = f"http://127.0.0.1:{source.server_port}/api/v0"
    monkeypatch.setattr(
        VastAIClient,
        "OFFICIAL_API_BASE_URLS",
        frozenset({base_url}),
        raising=False,
    )
    try:
        with pytest.raises(GpuHubError) as exc:
            VastAIClient("DUMMY-REDIRECT-TOKEN", base_url=base_url).list_instances()

        assert exc.value.code == "vast_redirect_rejected"
        assert source_authorization == ["Bearer DUMMY-REDIRECT-TOKEN"]
        assert target_authorization == []
    finally:
        source.shutdown()
        target.shutdown()
        source.server_close()
        target.server_close()
        for thread in threads:
            thread.join(timeout=2)


def test_controller_rejects_arbitrary_vast_api_base_before_network(monkeypatch, tmp_path):
    calls = []

    class Response:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "src.nova_gpu_hub.urllib.request.urlopen",
        lambda *_args, **_kwargs: calls.append(True) or Response(),
    )
    monkeypatch.setattr(
        "src.nova_gpu_hub.open_without_redirects",
        lambda *_args, **_kwargs: calls.append(True) or Response(),
        raising=False,
    )
    controller = GpuHubController(
        tmp_path,
        env={
            "NOVA_VAST_API_KEY": "DUMMY-KEY",
            "NOVA_VAST_API_BASE_URL": "https://attacker.example/api/v0",
        },
    )

    with pytest.raises(GpuHubError) as exc:
        controller.vast_instances()

    assert exc.value.code == "vast_api_base_not_approved"
    assert calls == []


def test_vast_paid_operations_require_confirmation(monkeypatch):
    client = VastAIClient("SECRET")
    with pytest.raises(GpuHubError) as start_exc:
        client.create_instance(7, {})
    with pytest.raises(GpuHubError) as destroy_exc:
        client.destroy_instance("i-1")
    assert start_exc.value.code == "confirmation_required"
    assert destroy_exc.value.code == "confirmation_required"
    assert "SECRET" not in str(start_exc.value) + str(destroy_exc.value)


def test_controller_reads_api_key_only_from_environment_and_never_returns_it(monkeypatch, tmp_path):
    monkeypatch.setattr("src.nova_gpu_hub.VastAIClient.list_instances", lambda self: [{"id": "i-1"}])
    controller = GpuHubController(tmp_path, env={"NOVA_VAST_API_KEY": "SECRET"})
    assert controller.vast_instances() == [{"id": "i-1"}]
    assert "SECRET" not in json.dumps(controller.status())


def test_status_resolves_auto_to_cpu_when_no_local_or_vast(monkeypatch, tmp_path):
    monkeypatch.setattr("src.nova_gpu_hub.detect_local_gpu", lambda: {"available": False, "usable": False, "reason": "none"})
    status = GpuHubController(tmp_path, env={}).status()
    assert status["mode"] == "auto"
    assert status["effective_mode"] == "cpu"
    assert status["available"] is True


def test_vast_key_alone_is_not_reported_as_available(monkeypatch, tmp_path):
    monkeypatch.setattr("src.nova_gpu_hub.detect_local_gpu", lambda: {"available": False, "usable": False, "reason": "none"})
    controller = GpuHubController(tmp_path, env={"NOVA_VAST_API_KEY": "SECRET"})
    status = controller.set_mode("vast_gpu")

    assert status["effective_mode"] == "vast_gpu"
    assert status["available"] is False
    assert status["verified"] is False
    assert controller.vast_status()["available"] is False


def test_verified_endpoint_makes_vast_mode_available(monkeypatch, tmp_path):
    monkeypatch.setattr("src.nova_gpu_hub.detect_local_gpu", lambda: {"available": False, "usable": False, "reason": "none"})
    controller = GpuHubController(tmp_path, env={"NOVA_VAST_API_KEY": "SECRET"})
    controller.set_mode("vast_gpu")
    controller.verify_remote_model(
        "https://worker.example",
        "qwen3",
        provider="vllm",
        backend="vast_gpu",
        selected_instance_id="instance-7",
    )

    status = controller.status()
    assert status["available"] is True
    assert status["verified"] is True
    assert status["effective_mode"] == "vast_gpu"
    assert controller.vast_status()["available"] is True


def test_verified_vast_endpoint_cannot_make_explicit_local_mode_available(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.nova_gpu_hub.detect_local_gpu",
        lambda: {"available": True, "usable": True, "reason": "local CUDA ready"},
    )
    controller = GpuHubController(tmp_path, env={})
    controller.set_mode("vast_gpu")
    controller.verify_remote_model(
        "https://worker.example",
        "qwen3",
        provider="vllm",
        backend="vast_gpu",
        selected_instance_id="instance-7",
    )

    status = controller.set_mode("local_gpu")

    assert status["effective_mode"] == "local_gpu"
    assert status["available"] is False
    assert status["verified"] is False
    assert status["verified_backend"] == "vast_gpu"


def test_local_backend_verification_rejects_non_loopback_endpoint(tmp_path):
    controller = GpuHubController(tmp_path, env={})
    controller.set_mode("local_gpu")

    with pytest.raises(GpuHubError) as exc:
        controller.verify_remote_model(
            "http://10.0.0.8:8000",
            "qwen3",
            provider="vllm",
            backend="local_gpu",
        )

    assert exc.value.code == "invalid_local_endpoint"


def test_ipv6_loopback_endpoint_round_trips_through_status_and_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.nova_gpu_hub.detect_local_gpu",
        lambda: {"available": True, "usable": True, "reason": "local CUDA ready"},
    )
    controller = GpuHubController(tmp_path, env={})
    controller.set_mode("local_gpu")

    saved = controller.verify_remote_model(
        "http://[::1]:8000/v1?token=SECRET",
        "qwen3",
        provider="vllm",
        backend="local_gpu",
    )

    assert saved["endpoint"]["url"] == "http://[::1]:8000/v1"
    status = controller.status()
    assert status["available"] is True
    assert status["verified"] is True
    assert status["endpoint"]["url"] == "http://[::1]:8000/v1"
    settings = build_gpu_hub_provider_settings(status, {"NOVA_MODEL_PROVIDER": "existing"})
    assert settings["NOVA_MODEL_PROVIDER_BASE_URL"] == "http://[::1]:8000/v1"
    assert settings["NOVA_ALLOW_REMOTE_MODEL_PROVIDER"] is False
    assert "SECRET" not in controller.store.path.read_text(encoding="utf-8")


def test_verified_availability_expires_after_bounded_ttl(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.nova_gpu_hub.detect_local_gpu",
        lambda: {"available": False, "usable": False, "reason": "none"},
    )
    controller = GpuHubController(
        tmp_path,
        env={"NOVA_GPU_HUB_VERIFICATION_TTL_SECONDS": "60"},
    )
    controller.store.save(
        {
            "mode": "vast_gpu",
            "verified": True,
            "verified_backend": "vast_gpu",
            "verified_at": (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat(),
            "endpoint": {
                "url": "https://worker.example",
                "model": "qwen3",
                "provider": "vllm",
            },
        }
    )

    status = controller.status()

    assert status["available"] is False
    assert status["verified"] is False
    assert status["verification_expired"] is True
    assert controller.vast_status()["available"] is False


def test_expired_private_vast_worker_renews_verified_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.nova_gpu_hub.detect_local_gpu",
        lambda: {"available": False, "usable": False, "reason": "none"},
    )
    controller = GpuHubController(
        tmp_path,
        env={"NOVA_GPU_HUB_VERIFICATION_TTL_SECONDS": "60"},
    )
    controller.store.save(
        {
            "mode": "vast_gpu",
            "verified": True,
            "verified_backend": "vast_gpu",
            "verified_at": (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat(),
            "endpoint": {
                "url": "http://127.0.0.1:8000",
                "model": "qwen3",
                "provider": "vllm",
            },
        }
    )

    class Response:
        def read(self):
            return json.dumps({"data": [{"id": "qwen3"}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("src.nova_gpu_hub.open_without_redirects", opener)

    status = controller.status()

    assert status["available"] is True
    assert status["verified"] is True
    assert status["verification_expired"] is False
    assert captured == {"url": "http://127.0.0.1:8000/v1/models", "timeout": 3}


def test_auto_selects_a_healthy_verified_vast_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.nova_gpu_hub.detect_local_gpu",
        lambda: {"available": False, "usable": False, "reason": "none"},
    )
    controller = GpuHubController(tmp_path, env={})
    controller.set_mode("vast_gpu")
    controller.verify_remote_model(
        "https://worker.example",
        "qwen3",
        provider="vllm",
        backend="vast_gpu",
    )

    status = controller.set_mode("auto")

    assert status["mode"] == "auto"
    assert status["effective_mode"] == "vast_gpu"
    assert status["available"] is True
    assert status["verified"] is True
    assert status["verification_expired"] is False
    assert "automatically" in status["reason"].lower()


def test_explicit_unavailable_mode_is_not_silently_changed(monkeypatch, tmp_path):
    monkeypatch.setattr("src.nova_gpu_hub.detect_local_gpu", lambda: {"available": False, "usable": False, "reason": "none"})
    status = GpuHubController(tmp_path, env={}).set_mode("local_gpu")
    assert status["mode"] == "local_gpu"
    assert status["effective_mode"] == "local_gpu"
    assert status["available"] is False


def test_missing_vast_key_fails_before_network(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr("src.nova_gpu_hub.urllib.request.urlopen", lambda *_args, **_kwargs: called.append(True))
    monkeypatch.setattr(
        "src.nova_gpu_hub.open_without_redirects",
        lambda *_args, **_kwargs: called.append(True),
        raising=False,
    )
    with pytest.raises(GpuHubError) as exc:
        GpuHubController(tmp_path, env={}).vast_instances()
    assert exc.value.code == "vast_unavailable"
    assert not called


def test_state_sanitizes_credentials_embedded_in_endpoint_url(tmp_path):
    path = tmp_path / "state.json"
    store = GpuHubStateStore(path)
    saved = store.save({"mode": "vast_gpu", "endpoint": {"url": "https://user:SECRET@example.test:8000/api?token=SECRET", "model": "qwen"}})
    assert saved["endpoint"]["url"] == "https://example.test:8000/api"
    assert "SECRET" not in path.read_text(encoding="utf-8")


def test_set_instance_state_requires_confirmation():
    with pytest.raises(GpuHubError) as exc:
        VastAIClient("SECRET").set_instance_state("i-1", "stopped")
    assert exc.value.code == "confirmation_required"


def test_state_redacts_secret_looking_scalar_metadata(tmp_path):
    path = tmp_path / "state.json"
    store = GpuHubStateStore(path)
    saved = store.save({"mode": "vast_gpu", "endpoint": {"model": "SECRET", "provider": "vllm", "region": "us-east"}})
    assert "model" not in saved["endpoint"]
    assert saved["endpoint"]["provider"] == "vllm"
    assert "region" not in saved["endpoint"]
    assert "SECRET" not in path.read_text(encoding="utf-8")
    controller = GpuHubController(tmp_path, env={})
    controller.store = store
    assert "SECRET" not in json.dumps(controller.status())
