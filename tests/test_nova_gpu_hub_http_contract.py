"""Contract tests for the small GPU Hub HTTP controller boundary."""

from pathlib import Path
import sys
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import nova_enhanced_server as server
from nova_gpu_hub import GpuHubError
from nova_model_provider import build_gpu_hub_provider_settings


class FakeGpuHub:
    def __init__(self):
        self.mode = "auto"
        self.calls = []

    def status(self):
        return {
            "mode": self.mode,
            "effective_mode": "cpu",
            "available": True,
            "reason": "CPU-only mode selected.",
            "verified": False,
            "verified_backend": None,
            "verified_at": None,
            "verification_expired": False,
            "selected_instance_id": "instance-1",
            "endpoint": {
                "url": "https://worker.example/v1",
                "model": "nova-qwen",
            },
        }

    def local_status(self):
        return {"available": False, "usable": False, "reason": "none"}

    def vast_status(self):
        return {"available": True, "reason": "configured"}

    def set_mode(self, mode):
        if mode not in {"auto", "cpu", "local_gpu", "vast_gpu"}:
            raise ValueError("invalid compute mode: " + str(mode))
        self.mode = mode
        return self.status()

    def vast_instances(self):
        self.calls.append(("instances",))
        return [{"id": "instance-1"}]

    def vast_search(self, filters):
        self.calls.append(("search", filters))
        return [{"id": "offer-1"}]

    def vast_create(self, offer_id, payload, *, confirmed=False):
        self.calls.append(("create", offer_id, payload, confirmed))
        if not confirmed:
            raise GpuHubError("confirmation_required", "confirmation required")
        return {"id": "instance-2"}

    def vast_set_state(self, instance_id, state, *, confirmed=False):
        self.calls.append(("state", instance_id, state, confirmed))
        if not confirmed:
            raise GpuHubError("confirmation_required", "confirmation required")
        return {"id": instance_id, "state": state}

    def vast_destroy(self, instance_id, *, confirmed=False):
        self.calls.append(("destroy", instance_id, confirmed))
        if not confirmed:
            raise GpuHubError("confirmation_required", "confirmation required")
        return {"id": instance_id, "destroyed": True}

    def verify_remote_model(self, endpoint, model, *, provider, backend=None, selected_instance_id=None):
        self.calls.append(("verify_remote_model", endpoint, model, provider, backend, selected_instance_id))
        return {
            "mode": self.mode,
            "verified": True,
            "endpoint": {"url": endpoint, "model": model, "provider": provider},
            "selected_instance_id": selected_instance_id,
        }


@pytest.fixture
def controller():
    hub = FakeGpuHub()
    calls = []

    def probe(endpoint, model, api_key):
        calls.append((endpoint, model, api_key))
        return {"ok": True, "endpoint": endpoint, "model": model, "method": "v1_models"}

    return server.GpuHubHttpController(
        hub,
        enabled=lambda: True,
        remote_actions_enabled=lambda: True,
        remote_model_probe=probe,
        remote_model_allowlist={"worker.example"},
    ), hub, calls


def _get(controller, path):
    handled, status, payload = controller.handle_get(path)
    assert handled is True
    return status, payload


def _post(controller, path, body):
    handled, status, payload = controller.handle_post(path, body)
    assert handled is True
    return status, payload


def test_status_contract_is_secret_free_and_has_required_fields(controller):
    route, _hub, _calls = controller
    status, payload = _get(route, "/api/gpu-hub/status")

    assert status == 200
    assert set(payload) == {
        "ok", "enabled", "mode", "effective_mode", "effective_backend",
        "available", "reason", "verified", "verified_backend", "verified_at",
        "verification_expired", "local", "vast", "selected_instance", "endpoint",
    }
    assert payload["ok"] is True
    assert payload["effective_backend"] == "cpu"
    assert "SECRET" not in repr(payload)
    assert "api_key" not in payload["endpoint"]


def test_disabled_status_keeps_the_documented_shape(controller):
    _route, hub, _calls = controller
    disabled = server.GpuHubHttpController(hub, enabled=lambda: False)
    status, payload = _get(disabled, "/api/gpu-hub/status")

    assert status == 200
    assert set(payload) == {
        "ok", "enabled", "mode", "effective_mode", "effective_backend",
        "available", "reason", "verified", "verified_backend", "verified_at",
        "verification_expired", "local", "vast", "selected_instance", "endpoint",
    }
    assert payload["enabled"] is False


def test_status_contract_preserves_expired_controller_readiness(controller):
    route, hub, _calls = controller
    hub.status = lambda: {
        "mode": "local_gpu",
        "effective_mode": "local_gpu",
        "available": False,
        "reason": "Local GPU endpoint verification expired.",
        "verified": False,
        "verified_backend": "local_gpu",
        "verified_at": "2026-08-17T12:00:00+00:00",
        "verification_expired": True,
        "selected_instance_id": None,
        "endpoint": {"url": "http://127.0.0.1:8000", "model": "qwen", "provider": "vllm"},
    }
    hub.local_status = lambda: {
        "available": True,
        "usable": True,
        "reason": "CUDA GPU detected.",
    }

    status, payload = _get(route, "/api/gpu-hub/status")

    assert status == 200
    assert payload["mode"] == "local_gpu"
    assert payload["effective_mode"] == "local_gpu"
    assert payload["effective_backend"] == "local_gpu"
    assert payload["available"] is False
    assert payload["reason"] == "Local GPU endpoint verification expired."
    assert payload["verified"] is False
    assert payload["verification_expired"] is True


def test_status_contract_reports_auto_using_verified_vast(controller):
    route, hub, _calls = controller
    hub.status = lambda: {
        "mode": "auto",
        "effective_mode": "vast_gpu",
        "available": True,
        "reason": "Verified GPU endpoint selected automatically.",
        "verified": True,
        "verified_backend": "vast_gpu",
        "verified_at": "2026-08-17T12:00:00+00:00",
        "verification_expired": False,
        "selected_instance_id": "instance-1",
        "endpoint": {"url": "https://worker.example", "model": "qwen", "provider": "vllm"},
    }

    status, payload = _get(route, "/api/gpu-hub/status")

    assert status == 200
    assert payload["mode"] == "auto"
    assert payload["effective_mode"] == "vast_gpu"
    assert payload["effective_backend"] == "vast_gpu"
    assert payload["available"] is True
    assert payload["verified"] is True
    assert payload["verification_expired"] is False


def test_mode_route_accepts_only_the_four_documented_modes(controller):
    route, hub, _calls = controller
    status, payload = _post(route, "/api/gpu-hub/mode", {"mode": "local_gpu"})
    assert status == 200
    assert payload["mode"] == "local_gpu"
    assert hub.mode == "local_gpu"

    status, payload = _post(route, "/api/gpu-hub/mode", {"mode": "remote"})
    assert status == 400
    assert payload["code"] == "invalid_mode"


def test_vast_routes_cover_test_list_search_and_confirmed_lifecycle(controller):
    route, hub, _calls = controller
    status, payload = _post(route, "/api/gpu-hub/vast/test", {})
    assert status == 200
    assert payload["ok"] is True

    status, payload = _get(route, "/api/gpu-hub/vast/instances")
    assert status == 200
    assert payload["instances"] == [{"id": "instance-1"}]

    status, payload = _post(route, "/api/gpu-hub/vast/search", {"filters": {"gpu_name": "RTX"}})
    assert status == 200
    assert payload["offers"] == [{"id": "offer-1"}]
    assert ("search", {"gpu_name": "RTX"}) in hub.calls

    for path, body in (
        ("/api/gpu-hub/vast/create", {"offer_id": "offer-1", "payload": {}}),
        ("/api/gpu-hub/vast/state", {"instance_id": "instance-1", "state": "stopped"}),
        ("/api/gpu-hub/vast/destroy", {"instance_id": "instance-1"}),
    ):
        status, payload = _post(route, path, body)
        assert status == 400
        assert payload["code"] == "confirmation_required"

    status, payload = _post(route, "/api/gpu-hub/vast/create", {"offer_id": "offer-1", "payload": {"image": "nova"}, "confirmed": True})
    assert status == 200
    assert payload["instance"]["id"] == "instance-2"
    status, payload = _post(route, "/api/gpu-hub/vast/state", {"instance_id": "instance-1", "state": "stopped", "confirmed": True})
    assert status == 200
    assert payload["instance"]["state"] == "stopped"
    status, payload = _post(route, "/api/gpu-hub/vast/destroy", {"instance_id": "instance-1", "confirmed": True})
    assert status == 200
    assert payload["instance"]["destroyed"] is True


def test_vast_lifecycle_is_disabled_without_remote_permission(controller):
    _route, hub, _calls = controller
    disabled = server.GpuHubHttpController(
        hub, enabled=lambda: True, remote_actions_enabled=lambda: False
    )
    status, payload = _post(disabled, "/api/gpu-hub/vast/create", {"offer_id": "offer-1", "confirmed": True})
    assert status == 503
    assert payload["code"] == "vast_unavailable"


def test_remote_model_test_persists_safe_metadata_but_not_the_supplied_key(controller):
    route, hub, calls = controller
    status, payload = _post(
        route,
        "/api/gpu-hub/remote-model/test",
        {
            "endpoint": "https://worker.example",
            "model": "qwen",
            "provider": "vllm",
            "backend": "vast_gpu",
            "selected_instance_id": "instance-1",
            "api_key": "SECRET",
        },
    )
    assert status == 200
    assert payload["ok"] is True
    assert calls == [("https://worker.example", "qwen", "SECRET")]
    assert (
        "verify_remote_model",
        "https://worker.example",
        "qwen",
        "vllm",
        "vast_gpu",
        "instance-1",
    ) in hub.calls
    assert "SECRET" not in repr(payload)


def test_remote_model_probe_rejects_a_missing_requested_model(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Opener:
        def open(self, _request, timeout):
            return Response(json.dumps({"data": [{"id": "other-model"}]}).encode("utf-8"))

    monkeypatch.setattr(server.urllib.request, "build_opener", lambda *_handlers: Opener())

    route = server.GpuHubHttpController(
        FakeGpuHub(),
        remote_model_allowlist={"worker.example"},
    )
    with pytest.raises(GpuHubError) as exc:
        route._probe_remote_model("https://worker.example", "qwen", "SECRET")
    assert exc.value.code == "model_unavailable"
    assert "SECRET" not in str(exc.value)


def test_failed_remote_model_test_does_not_persist_verification():
    hub = FakeGpuHub()

    def failed_probe(_endpoint, _model, _api_key):
        raise GpuHubError("remote_model_unavailable", "Endpoint could not be verified.")

    route = server.GpuHubHttpController(
        hub,
        enabled=lambda: True,
        remote_actions_enabled=lambda: True,
        remote_model_probe=failed_probe,
        remote_model_allowlist={"worker.example"},
    )

    status, payload = _post(
        route,
        "/api/gpu-hub/remote-model/test",
        {"endpoint": "https://worker.example", "model": "qwen", "api_key": "SECRET"},
    )

    assert status == 502
    assert payload["ok"] is False
    assert not any(call[0] == "verify_remote_model" for call in hub.calls)
    assert "SECRET" not in repr(payload)


def test_remote_model_test_rejects_public_host_before_network_probe(monkeypatch):
    hub = FakeGpuHub()
    calls = []
    monkeypatch.setattr(
        server.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(server.socket.AF_INET, server.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    route = server.GpuHubHttpController(
        hub,
        enabled=lambda: True,
        remote_model_probe=lambda *args: calls.append(args) or {"ok": True},
        remote_model_allowlist=set(),
    )

    status, payload = _post(
        route,
        "/api/gpu-hub/remote-model/test",
        {"endpoint": "https://example.com", "model": "qwen", "api_key": "SECRET"},
    )

    assert status == 400
    assert payload["code"] == "remote_endpoint_not_approved"
    assert calls == []
    assert not any(call[0] == "verify_remote_model" for call in hub.calls)
    assert "SECRET" not in repr(payload)


def test_remote_model_probe_never_follows_redirects():
    hits = []

    class RedirectingHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path == "/v1/models":
                self.send_response(302)
                self.send_header(
                    "Location",
                    f"http://127.0.0.1:{self.server.server_port}/redirect-target",
                )
                self.end_headers()
                return
            payload = json.dumps({"data": [{"id": "qwen"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), RedirectingHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        route = server.GpuHubHttpController(FakeGpuHub(), remote_model_allowlist=set())
        with pytest.raises(GpuHubError) as exc:
            route._probe_remote_model(
                f"http://127.0.0.1:{httpd.server_port}",
                "qwen",
                "SECRET",
            )
        assert exc.value.code == "remote_model_unavailable"
        assert hits == ["/v1/models"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("endpoint", ["http://127.0.0.1:8000", "http://100.64.10.20:8000"])
def test_remote_model_test_allows_local_and_tailscale_hosts(endpoint):
    hub = FakeGpuHub()
    calls = []

    def probe(probed_endpoint, model, api_key):
        calls.append((probed_endpoint, model, api_key))
        return {"ok": True, "endpoint": probed_endpoint, "model": model}

    route = server.GpuHubHttpController(
        hub,
        enabled=lambda: True,
        remote_model_probe=probe,
        remote_model_allowlist=set(),
    )
    status, payload = _post(
        route,
        "/api/gpu-hub/remote-model/test",
        {
            "endpoint": endpoint,
            "model": "qwen",
            "backend": "vast_gpu" if "100.64." in endpoint else "local_gpu",
            "api_key": "SECRET",
        },
    )

    assert status == 200
    assert payload["ok"] is True
    assert calls == [(endpoint, "qwen", "SECRET")]
    assert "SECRET" not in repr(payload)


def test_remote_model_test_never_returns_echoed_request_key():
    hub = FakeGpuHub()
    route = server.GpuHubHttpController(
        hub,
        enabled=lambda: True,
        remote_model_probe=lambda endpoint, model, api_key: {
            "ok": True,
            "endpoint": endpoint,
            "model": model,
            "diagnostic": api_key,
        },
        remote_model_allowlist=set(),
    )

    status, payload = _post(
        route,
        "/api/gpu-hub/remote-model/test",
        {
            "endpoint": "http://127.0.0.1:8000",
            "model": "qwen",
            "backend": "local_gpu",
            "api_key": "REQUEST-ONLY-KEY",
        },
    )

    assert status == 200
    assert "REQUEST-ONLY-KEY" not in repr(payload)


def test_gpu_hub_errors_are_safe_and_route_unknown_is_not_handled(controller):
    route, hub, _calls = controller
    hub.vast_instances = lambda: (_ for _ in ()).throw(GpuHubError("vast_request_failed", "bad SECRET"))
    status, payload = _get(route, "/api/gpu-hub/vast/instances")
    assert status == 502
    assert payload["code"] == "vast_request_failed"
    assert "SECRET" not in repr(payload)
    assert route.handle_get("/api/not-gpu") == (False, 404, None)


def test_handler_boundary_dispatches_gpu_hub_before_ordinary_404(monkeypatch, controller):
    route, _hub, _calls = controller
    monkeypatch.setattr(server, "GPU_HUB_HTTP", route)
    sent = []
    handler = SimpleNamespace(
        _send_json=lambda payload, status=200: sent.append((status, payload)),
        _read_json_body=lambda: {"mode": "cpu"},
    )

    assert server.NovaHandler._handle_gpu_hub_get(
        handler, SimpleNamespace(path="/api/gpu-hub/status")
    ) is True
    assert sent[-1][0] == 200
    assert server.NovaHandler._handle_gpu_hub_post(
        handler, SimpleNamespace(path="/api/gpu-hub/mode")
    ) is True
    assert sent[-1][1]["mode"] == "cpu"


def test_provider_bridge_only_overrides_for_a_verified_selected_gpu():
    ordinary = {"NOVA_MODEL_PROVIDER": "existing"}
    assert build_gpu_hub_provider_settings({"mode": "cpu", "verified": True}, ordinary) == ordinary
    assert build_gpu_hub_provider_settings({"mode": "auto", "verified": False}, ordinary) == ordinary

    settings = build_gpu_hub_provider_settings(
        {
            "mode": "vast_gpu",
            "effective_mode": "vast_gpu",
            "available": True,
            "verified": True,
            "verified_backend": "vast_gpu",
            "endpoint": {"url": "https://worker.example/v1", "model": "qwen3", "provider": "vllm"},
        },
        ordinary,
    )
    assert settings["NOVA_MODEL_PROVIDER"] == "vllm"
    assert settings["NOVA_MODEL_PROVIDER_BASE_URL"] == "https://worker.example/v1"
    assert settings["NOVA_MODEL_PROVIDER_MODEL"] == "qwen3"
    assert settings["NOVA_ALLOW_REMOTE_MODEL_PROVIDER"] is True

    auto_settings = build_gpu_hub_provider_settings(
        {
            "mode": "auto",
            "effective_mode": "local_gpu",
            "available": True,
            "verified": True,
            "verified_backend": "local_gpu",
            "endpoint": {"url": "http://127.0.0.1:8000", "model": "qwen3", "provider": "vllm"},
        },
        ordinary,
    )
    assert auto_settings["NOVA_MODEL_PROVIDER"] == "vllm"
    assert auto_settings["NOVA_ALLOW_REMOTE_MODEL_PROVIDER"] is False
