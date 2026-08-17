import json
from pathlib import Path

import pytest

from src.nova_gpu_hub import (
    ComputeMode,
    GpuHubController,
    GpuHubError,
    GpuHubStateStore,
    VastAIClient,
    detect_local_gpu,
)


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
    client = VastAIClient("SECRET", base_url="https://example.test/api/v0/")
    result = client.list_instances()
    assert result == [{"id": 3}]
    assert captured["url"] == "https://example.test/api/v0/instances/"
    assert captured["headers"]["Authorization"] == "Bearer SECRET"
    assert captured["timeout"] == 15


def test_vast_errors_redact_api_key(monkeypatch):
    def opener(_request, timeout):
        raise OSError("failed SECRET")

    monkeypatch.setattr("src.nova_gpu_hub.urllib.request.urlopen", opener)
    with pytest.raises(GpuHubError) as exc:
        VastAIClient("SECRET").list_instances()
    assert "SECRET" not in str(exc.value)
    assert "SECRET" not in repr(exc.value)


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


def test_explicit_unavailable_mode_is_not_silently_changed(monkeypatch, tmp_path):
    monkeypatch.setattr("src.nova_gpu_hub.detect_local_gpu", lambda: {"available": False, "usable": False, "reason": "none"})
    status = GpuHubController(tmp_path, env={}).set_mode("local_gpu")
    assert status["mode"] == "local_gpu"
    assert status["effective_mode"] == "local_gpu"
    assert status["available"] is False


def test_missing_vast_key_fails_before_network(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr("src.nova_gpu_hub.urllib.request.urlopen", lambda *_args, **_kwargs: called.append(True))
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
