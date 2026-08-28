from __future__ import annotations

from http.server import HTTPServer
import json
from pathlib import Path
from socketserver import ThreadingMixIn
import sys
from threading import Thread
import time
import urllib.error
import urllib.request

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import nova_enhanced_server as server  # noqa: E402
from nova_gateway.auth import NovaAuthenticator, NovaClientRegistry  # noqa: E402
from nova_gateway.config import GatewayConfig  # noqa: E402
from nova_gateway.comfyui import ComfyUIEngine  # noqa: E402
from nova_gateway.core import NovaGatewayCore  # noqa: E402
from nova_gateway.http import NovaGatewayHttpController  # noqa: E402
from nova_gateway.providers import MockProvider  # noqa: E402


def test_media_range_parser_supports_full_and_suffix_ranges() -> None:
    parser = NovaGatewayHttpController._parse_range_header
    assert parser("bytes=10-19", 100) == (10, 19)
    assert parser("bytes=-10", 100) == (90, 99)
    assert parser("bytes=90-", 100) == (90, 99)
    assert parser("bytes=100-110", 100) is None
    assert parser("bytes=1-2,4-5", 100) is None


def test_conversation_archive_http_round_trip_and_owner_isolation(tmp_path, monkeypatch) -> None:
    config = GatewayConfig(
        rate_limit_enabled=False,
        conversation_store_path=tmp_path / "conversations.json",
    )
    _core, controller = isolated_controller(config=config)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, saved = request_json(
            base_url,
            "POST",
            "/nova/v1/conversations",
            {
                "conversation_id": "conv-http",
                "title": "Phone chat",
                "messages": [
                    {"role": "user", "content": "Remember this chat"},
                    {"role": "assistant", "content": "Saved."},
                    {"role": "system", "content": "not persisted"},
                ],
            },
        )
        assert status == 201
        assert saved["data"]["message_count"] == 2

        status, _headers, listed = request_json(
            base_url,
            "GET",
            "/nova/v1/conversations?query=remember",
        )
        assert status == 200
        assert [row["conversation_id"] for row in listed["data"]] == ["conv-http"]
        assert listed["privacy"]["other_clients_returned"] is False

        status, _headers, action = request_json(
            base_url,
            "POST",
            "/nova/v1/conversations/conv-http/archive",
            {},
        )
        assert status == 200 and action["ok"] is True
        status, _headers, hidden = request_json(base_url, "GET", "/nova/v1/conversations")
        assert status == 200 and hidden["data"] == []
        status, _headers, restored = request_json(
            base_url,
            "POST",
            "/nova/v1/conversations/conv-http/restore",
            {},
        )
        assert status == 200 and restored["ok"] is True
    finally:
        httpd.shutdown()
        httpd.server_close()


class ThreadedTestServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def start_server():
    httpd = ThreadedTestServer(("127.0.0.1", 0), server.NovaHandler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


def request_json(base_url, method, path, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        base_url + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.loads(exc.read().decode("utf-8"))


def isolated_controller(
    *,
    config=None,
    runner=None,
    key=None,
    scopes=None,
    provider=None,
    comfy=None,
    video_lite=None,
):
    config = config or GatewayConfig(rate_limit_enabled=False)
    core = NovaGatewayCore(
        runner or (lambda text, context: ("Nova HTTP answer", {"route": "nova_core"})),
        config=config,
        comfyui=comfy,
        video_lite=video_lite,
        register_ollama=False,
    )
    if provider:
        core.register_provider(provider, aliases={"nova-stream": "mock-text", "nova-embed": "mock-text"})
    registry = NovaClientRegistry()
    if key:
        registry.add_client("phone", "Phone", key, set(scopes or {"chat.generate"}), persist=False)
    auth = NovaAuthenticator(config, registry, env={})
    return core, NovaGatewayHttpController(core, auth, config)


class FakeVideoLiteEngine:
    engine_id = "nova-video-lite"

    def __init__(self):
        self.last_prompt = ""
        self.last_options = {}

    def health_check(self):
        return {
            "ok": True,
            "status": "ready",
            "video_workflow_configured": True,
            "text_to_video": True,
        }

    def capabilities(self):
        return {
            "engine_id": self.engine_id,
            "available": True,
            "text_to_video": True,
            "render_mode": "generated_keyframe_motion",
        }

    def text_to_video(self, prompt, **options):
        self.last_prompt = prompt
        self.last_options = options
        return {
            "object": "nova.media_job",
            "job_id": "nvl_http_video",
            "engine_id": self.engine_id,
            "status": "queued",
        }

    def list_jobs(self, *, owner_id=None, limit=25):
        return {
            "object": "list",
            "engine_id": self.engine_id,
            "data": [],
            "privacy": {
                "prompt_content_returned": False,
                "other_clients_jobs_returned": False,
            },
        }


def test_models_endpoint_lists_only_resolvable_nova_aliases(monkeypatch) -> None:
    _core, controller = isolated_controller()
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, payload = request_json(base_url, "GET", "/v1/models")
        assert status == 200
        assert payload["object"] == "list"
        ids = {item["id"] for item in payload["data"]}
        assert {"nova", "nova-default", "nova-fast", "nova-deep", "nova-local", "nova-coder"} <= ids
        assert all(item["object"] == "model" and item["owned_by"] == "nova" for item in payload["data"])
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_runtime_contract_endpoint_exposes_frozen_runtime_snapshot(monkeypatch) -> None:
    _core, controller = isolated_controller()
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, payload = request_json(base_url, "GET", "/nova/v1/runtime/contract")
        assert status == 200
        assert payload["object"] == "nova.runtime_contract"
        assert "contract_hash" in payload["data"]
        assert payload["tools"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_cancel_route_cannot_cancel_another_authenticated_clients_active_stream(
    monkeypatch,
) -> None:
    config = GatewayConfig(
        allow_local_no_auth=False,
        rate_limit_enabled=False,
    )
    provider = MockProvider(response_text="Owned stream", chunks=["Owned ", "stream"])
    core = NovaGatewayCore(
        lambda text, context: ("existing", {}),
        config=config,
        register_ollama=False,
    )
    core.register_provider(provider, aliases={"nova-owned-stream": "mock-text"})
    registry = NovaClientRegistry()
    registry.add_client(
        "phone-one",
        "Phone one",
        "phone-one-secret",
        {"chat.generate", "chat.stream"},
        persist=False,
    )
    registry.add_client(
        "phone-two",
        "Phone two",
        "phone-two-secret",
        {"chat.generate", "chat.stream"},
        persist=False,
    )
    controller = NovaGatewayHttpController(
        core,
        NovaAuthenticator(config, registry, env={}),
        config,
    )
    request = server.NovaRequest(
        request_id="req_http_owned_stream",
        client_id="phone-one",
        conversation_id="conv_http_owned_stream",
        messages=[server.NovaMessage(role="user", content="Keep this open")],
        generation_options=server.NovaGenerationOptions(
            model="nova-owned-stream",
            stream=True,
        ),
    )
    stream = core.stream(request)
    assert next(stream).delta == "Owned "
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, rejected = request_json(
            base_url,
            "POST",
            f"/nova/v1/cancel/{request.request_id}",
            {},
            headers={"Authorization": "Bearer phone-two-secret"},
        )
        assert status == 200
        assert rejected["ok"] is False
        assert request.request_id not in provider.cancelled

        status, _headers, accepted = request_json(
            base_url,
            "POST",
            f"/nova/v1/cancel/{request.request_id}",
            {},
            headers={"Authorization": "Bearer phone-one-secret"},
        )
        assert status == 200
        assert accepted["ok"] is True
        assert request.request_id in provider.cancelled
    finally:
        stream.close()
        httpd.shutdown()
        httpd.server_close()


def test_chat_completions_enters_nova_core_and_preserves_roles(monkeypatch) -> None:
    observed = {}

    def runner(text, context):
        observed.update(text=text, context=context)
        return "Nova gateway works.", {"route": "cognitive_os", "identity": "nova"}

    _core, controller = isolated_controller(runner=runner)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, payload = request_json(
            base_url,
            "POST",
            "/v1/chat/completions",
            {
                "model": "nova",
                "messages": [
                    {"role": "system", "content": "External context"},
                    {"role": "developer", "content": "Be concise"},
                    {"role": "user", "content": "Hello"},
                ],
                "metadata": {"conversation_id": "conv_http"},
            },
        )
        assert status == 200
        assert payload["object"] == "chat.completion"
        assert payload["choices"][0]["message"]["content"] == "Nova gateway works."
        assert payload["nova_metadata"]["conversation_id"] == "conv_http"
        assert observed["text"] == "Hello"
        assert [item["role"] for item in observed["context"]["nova_request"]["messages"]] == ["system", "developer", "user"]
        assert observed["context"]["nova_gateway"] is True
        assert observed["context"]["dream_lab"]["selected_strategy"] == "direct_nova_core"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_dream_lab_and_comfyui_native_routes_are_scoped_and_honest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow = tmp_path / "image-api.json"
    workflow.write_text(
        json.dumps(
            {
                "1": {
                    "class_type": "NovaTestNode",
                    "inputs": {"text": "{{NOVA_PROMPT}}", "seed": "{{NOVA_SEED}}"},
                }
            }
        ),
        encoding="utf-8",
    )
    config = GatewayConfig(
        allow_local_no_auth=False,
        enable_remote_access=True,
        rate_limit_enabled=False,
        comfyui_enabled=True,
        comfyui_image_workflow_path=workflow,
        comfyui_job_store_path=tmp_path / "jobs.json",
    )
    comfy = ComfyUIEngine(
        enabled=True,
        image_workflow_path=workflow,
        job_store_path=tmp_path / "jobs.json",
    )

    def fake_comfy_request(method, path, payload=None):
        if path == "/system_stats":
            return {}
        if path == "/prompt":
            return {"prompt_id": "http-image-job"}
        if path == "/history/http-image-job":
            return {
                "http-image-job": {
                    "status": {"completed": True},
                    "outputs": {
                        "9": {
                            "images": [
                                {
                                    "filename": "http-image.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    },
                }
            }
        raise AssertionError((method, path, payload))

    monkeypatch.setattr(comfy, "_request", fake_comfy_request)

    class FakeMediaStream:
        headers = {}

        def __init__(self):
            self.remaining = b"PNGDATA"

        def read(self, _size=-1):
            value, self.remaining = self.remaining, b""
            return value

        def close(self):
            return None

    monkeypatch.setattr(
        comfy,
        "open_job_output",
        lambda job_id, output_index, owner_id=None: {
            "response": FakeMediaStream(),
            "content_type": "image/png",
            "content_length": 7,
            "filename": "http-image.png",
            "max_bytes": 1024,
        },
    )
    _core, controller = isolated_controller(
        config=config,
        comfy=comfy,
        key="nova-media-key",
        scopes={"chat.generate", "tools.list", "image.generate"},
    )
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    headers = {"Authorization": "Bearer nova-media-key"}
    try:
        status, _headers, chat = request_json(
            base_url,
            "POST",
            "/nova/v1/chat",
            {
                "model": "nova",
                "text": "Compare the safest architecture options",
                "conversation_id": "dream-http",
            },
            headers,
        )
        assert status == 200
        assert chat["metadata"]["dream_lab"]["selected_strategy"] == "local_counterfactual_review"

        status, _headers, dream = request_json(
            base_url,
            "GET",
            "/nova/v1/dream-lab?conversation_id=dream-http",
            headers=headers,
        )
        assert status == 200
        assert dream["data"]["prompt_content_stored"] is False

        status, _headers, engines = request_json(
            base_url,
            "GET",
            "/nova/v1/engines",
            headers=headers,
        )
        assert status == 200
        assert engines["data"][0]["engine_id"] == "comfyui-local"
        assert engines["data"][0]["health"]["status"] == "ready"

        status, _headers, access = request_json(
            base_url,
            "GET",
            "/nova/v1/media/access",
            headers=headers,
        )
        assert status == 200
        assert access["image_generate"] is True
        assert access["video_generate"] is False

        status, _headers, job = request_json(
            base_url,
            "POST",
            "/nova/v1/images/generations",
            {"prompt": "A local Nova creature", "seed": 9},
            headers,
        )
        assert status == 202
        assert job["job_id"] == "http-image-job"
        status, _headers, jobs = request_json(
            base_url,
            "GET",
            "/nova/v1/jobs?limit=10",
            headers=headers,
        )
        assert status == 200
        assert jobs["data"][0]["job_id"] == "http-image-job"
        assert jobs["privacy"]["other_clients_jobs_returned"] is False
        status, _headers, rejected = request_json(
            base_url,
            "POST",
            "/nova/v1/images/generations",
            {"prompt": "Invalid dimensions must not be clamped", "width": 32},
            headers,
        )
        assert status == 400
        assert rejected["error"]["param"] == "width"
        status, _headers, completed = request_json(
            base_url,
            "GET",
            "/nova/v1/jobs/http-image-job",
            headers=headers,
        )
        assert status == 200
        assert completed["status"] == "completed"
        assert completed["outputs"][0]["filename"] == "http-image.png"
        output_request = urllib.request.Request(
            base_url + "/nova/v1/jobs/http-image-job/outputs/0",
            headers=headers,
        )
        with urllib.request.urlopen(output_request, timeout=10) as response:
            assert response.headers.get_content_type() == "image/png"
            assert response.read() == b"PNGDATA"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_comfyui_generation_is_not_granted_by_local_chat_scope(monkeypatch) -> None:
    config = GatewayConfig(
        rate_limit_enabled=False,
        comfyui_enabled=True,
    )
    _core, controller = isolated_controller(config=config)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, payload = request_json(
            base_url,
            "POST",
            "/nova/v1/images/generations",
            {"prompt": "This should be permission checked first"},
        )
        assert status == 403
        assert payload["error"]["code"] == "insufficient_scope"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_local_media_scopes_can_be_explicitly_enabled_for_desktop(monkeypatch) -> None:
    """Desktop localhost can opt into Dream Studio media without widening remote auth."""
    config = GatewayConfig(
        rate_limit_enabled=False,
        comfyui_enabled=True,
        allow_local_media=True,
    )
    _core, controller = isolated_controller(config=config)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, access = request_json(
            base_url,
            "GET",
            "/nova/v1/media/access",
        )
        assert status == 200
        assert access["local_client"] is True
        assert access["authenticated"] is False
        assert access["image_generate"] is True
        assert access["video_generate"] is True
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_comfyui_launch_route_starts_local_engine(monkeypatch) -> None:
    config = GatewayConfig(
        rate_limit_enabled=False,
        comfyui_enabled=True,
    )
    _core, controller = isolated_controller(config=config)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    launched = {}

    def fake_launch():
        launched["called"] = True
        return {
            "ok": True,
            "started": True,
            "status": "launching",
            "process_id": 4321,
        }

    monkeypatch.setattr(controller.core.comfyui, "launch_local_server", fake_launch)
    httpd, base_url = start_server()
    try:
        status, _headers, payload = request_json(
            base_url,
            "POST",
            "/nova/v1/engines/comfyui-local/launch",
        )
        assert status == 202
        assert launched["called"] is True
        assert payload["started"] is True
        assert payload["process_id"] == 4321
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_video_lite_route_is_permission_scoped_and_accepts_bounded_motion(
    monkeypatch,
) -> None:
    config = GatewayConfig(
        allow_local_no_auth=False,
        enable_remote_access=True,
        rate_limit_enabled=False,
    )
    video_lite = FakeVideoLiteEngine()
    _core, controller = isolated_controller(
        config=config,
        video_lite=video_lite,
        key="nova-video-key",
        scopes={"chat.generate", "video.generate"},
    )
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    headers = {"Authorization": "Bearer nova-video-key"}
    try:
        status, _headers, job = request_json(
            base_url,
            "POST",
            "/nova/v1/videos/generations",
            {
                "prompt": "A local Nova creature in soft purple light",
                "frames": 48,
                "fps": 12,
                "motion": "pan_right",
            },
            headers,
        )
        assert status == 202
        assert job["job_id"] == "nvl_http_video"
        assert video_lite.last_options["owner_id"] == "phone"
        assert video_lite.last_options["motion"] == "pan_right"

        status, _headers, rejected = request_json(
            base_url,
            "POST",
            "/nova/v1/videos/generations",
            {"prompt": "Unsafe motion value", "motion": "arbitrary_command"},
            headers,
        )
        assert status == 400
        assert rejected["error"]["param"] == "motion"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_invalid_model_and_unsupported_field_return_openai_errors(monkeypatch) -> None:
    _core, controller = isolated_controller()
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, payload = request_json(
            base_url, "POST", "/v1/chat/completions",
            {"model": "not-a-model", "messages": [{"role": "user", "content": "Hi"}]},
        )
        assert status == 404
        assert payload["error"]["type"] == "model_unavailable"
        assert payload["error"]["code"] == "model_not_found"

        status, _headers, payload = request_json(
            base_url, "POST", "/v1/chat/completions",
            {"model": "nova", "messages": [{"role": "user", "content": "Hi"}], "logprobs": True},
        )
        assert status == 400
        assert payload["error"]["type"] == "unsupported_feature"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_api_key_and_scope_rules_apply_to_local_and_lan_style_clients(monkeypatch) -> None:
    config = GatewayConfig(allow_local_no_auth=False, enable_remote_access=True, rate_limit_enabled=False)
    _core, controller = isolated_controller(config=config, key="nova-phone-key", scopes={"chat.generate"})
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, payload = request_json(base_url, "GET", "/v1/models")
        assert status == 401
        assert payload["error"]["type"] == "authentication_error"

        headers = {"Authorization": "Bearer nova-phone-key"}
        status, _headers, _payload = request_json(base_url, "GET", "/v1/models", headers=headers)
        assert status == 200
        status, _headers, payload = request_json(base_url, "GET", "/nova/v1/tools", headers=headers)
        assert status == 403
        assert payload["error"]["code"] == "insufficient_scope"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_chat_stream_is_real_sse_ordered_and_done(monkeypatch) -> None:
    mock = MockProvider(chunks=["Nova", " ", "streams", "."])
    _core, controller = isolated_controller(provider=mock)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        request = urllib.request.Request(
            base_url + "/v1/chat/completions",
            data=json.dumps({
                "model": "nova-stream", "stream": True,
                "messages": [{"role": "user", "content": "Stream"}],
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.headers.get_content_type() == "text/event-stream"
            lines = [line.decode("utf-8").strip() for line in response if line.startswith(b"data: ")]
        assert lines[-1] == "data: [DONE]"
        chunks = [json.loads(line[6:]) for line in lines[:-1]]
        rebuilt = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)
        assert rebuilt == "Nova streams."
        assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
        assert len({chunk["id"] for chunk in chunks}) == 1
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_default_nova_stream_runs_through_existing_nova_core(monkeypatch) -> None:
    observed = {}

    def runner(text, context):
        observed.update(text=text, context=context)
        context["stream_callback"]("Nova ")
        context["stream_callback"]("core streams.")
        return "Nova core streams.", {"route": "cognitive_os", "native_streaming": True}

    _core, controller = isolated_controller(runner=runner)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        request = urllib.request.Request(
            base_url + "/v1/chat/completions",
            data=json.dumps(
                {"model": "nova", "stream": True, "messages": [{"role": "user", "content": "Stream"}]}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.headers.get_content_type() == "text/event-stream"
            lines = [line.decode("utf-8").strip() for line in response if line.startswith(b"data: ")]
        chunks = [json.loads(line[6:]) for line in lines[:-1]]
        rebuilt = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)
        assert rebuilt == "Nova core streams."
        assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
        assert observed["text"] == "Stream"
        assert observed["context"]["nova_gateway"] is True
        assert callable(observed["context"]["stream_callback"])
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_native_desktop_stream_returns_trace_and_preserves_safe_ui_context(monkeypatch) -> None:
    observed = {}

    def runner(text, context):
        observed.update(text=text, context=context)
        context["progress_callback"](
            "nova_core",
            "Nova is applying identity, memory, context, and local routing.",
            10,
        )
        context["stream_callback"]("Nova ")
        context["stream_callback"]("desktop streams.")
        return "Nova desktop streams.", {
            "route": "cognitive_os",
            "native_streaming": True,
            "permissions_snapshot": {"mic": True, "camera": False, "speaker": True},
        }

    _core, controller = isolated_controller(runner=runner)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        request = urllib.request.Request(
            base_url + "/nova/v1/chat",
            data=json.dumps(
                {
                    "model": "nova",
                    "stream": True,
                    "text": "Stream in the desktop",
                    "request_id": "req_web_test",
                    "conversation_id": "web_session_test",
                    "trained_adapter_only": True,
                    "dolphin_adapter_only": True,
                    "allow_slow_dolphin_cpu": True,
                    "lora_adapter_id": "nova-test",
                    "sensor_snapshot": {"enabled": True, "source": "browser_sensor_overlay"},
                    "conversation_summary": {
                        "schema_version": "1.0",
                        "revision": 2,
                        "topics": ["Earlier provider routing"],
                    },
                    "conversation_summary_write_allowed": True,
                    "lora_adapter_path": "C:/must-not-pass",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.headers.get_content_type() == "text/event-stream"
            lines = [line.decode("utf-8").strip() for line in response if line.startswith(b"data: ")]
        events = [json.loads(line[6:]) for line in lines[:-1]]
        assert "".join(event.get("delta", "") for event in events) == "Nova desktop streams."
        progress = next(event for event in events if event["event_type"] == "response.progress")
        assert progress["metadata"]["stage"] == "nova_core"
        assert progress["metadata"]["content_logged"] is False
        completed = events[-1]
        assert completed["event_type"] == "response.completed"
        assert completed["metadata"]["trace"]["route"] == "cognitive_os"
        assert completed["metadata"]["conversation_id"] == "web_session_test"
        assert completed["metadata"]["request_id"] == "req_web_test"
        assert completed["metadata"]["protocol_version"] == "1.1"
        assert observed["context"]["trained_adapter_only"] is True
        assert observed["context"]["dolphin_adapter_only"] is True
        assert observed["context"]["allow_slow_dolphin_cpu"] is True
        assert observed["context"]["lora_adapter_id"] == "nova-test"
        assert observed["context"]["sensor_snapshot"]["source"] == "browser_sensor_overlay"
        assert observed["context"]["conversation_summary"]["revision"] == 2
        assert observed["context"]["conversation_summary_write_allowed"] is True
        assert "lora_adapter_path" not in observed["context"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_native_raw_memory_stream_preserves_mode_and_bounded_summary_history(monkeypatch) -> None:
    observed = {}

    def runner(text, context):
        observed.update(text=text, context=context)
        context["stream_callback"]("Raw memory streams.")
        return "Raw memory streams.", {"route": "raw_memory"}

    _core, controller = isolated_controller(runner=runner)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        summary_history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"summary turn {index}"}
            for index in range(10)
        ]
        request = urllib.request.Request(
            base_url + "/nova/v1/chat",
            data=json.dumps(
                {
                    "model": "nova",
                    "stream": True,
                    "text": "Continue raw with memory",
                    "nova_model_mode": "raw_memory",
                    "conversation_summary_history": summary_history,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            lines = [line.decode("utf-8").strip() for line in response if line.startswith(b"data: ")]

        events = [json.loads(line[6:]) for line in lines[:-1]]
        assert "".join(event.get("delta", "") for event in events) == "Raw memory streams."
        assert observed["context"]["nova_model_mode"] == "raw_memory"
        assert observed["context"]["conversation_summary_history"] == summary_history[-8:]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_native_chat_rejects_malformed_or_oversized_conversation_summary(monkeypatch) -> None:
    _core, controller = isolated_controller()
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        for invalid_summary in (["not", "an", "object"], {"digest": ["x" * 12_001]}):
            status, _headers, payload = request_json(
                base_url,
                "POST",
                "/nova/v1/chat",
                {
                    "model": "nova",
                    "text": "Hello",
                    "conversation_summary": invalid_summary,
                },
            )
            assert status == 400
            assert payload["error"]["param"] == "conversation_summary"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_responses_embeddings_native_health_and_capabilities_routes(monkeypatch) -> None:
    mock = MockProvider(response_text="Mock response")
    _core, controller = isolated_controller(provider=mock)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, response_payload = request_json(
            base_url, "POST", "/v1/responses",
            {"model": "nova", "instructions": "Stay Nova", "input": "Hello"},
        )
        assert status == 200
        assert response_payload["object"] == "response"
        assert response_payload["output_text"] == "Nova HTTP answer"

        status, _headers, embed_payload = request_json(
            base_url, "POST", "/v1/embeddings", {"model": "nova-embed", "input": ["Nova", "Creature"]},
        )
        assert status == 200
        assert len(embed_payload["data"]) == 2
        assert embed_payload["usage"] is None

        status, _headers, native = request_json(
            base_url, "POST", "/nova/v1/chat", {"model": "nova", "text": "Hello", "conversation_id": "conv_native"},
        )
        assert status == 200
        assert native["conversation_id"] == "conv_native"
        assert native["provider"] == "existing-nova"
        assert native["metadata"]["world_model"]["conversation_id"] == "conv_native"

        status, _headers, world_model = request_json(
            base_url,
            "GET",
            "/nova/v1/world-model?conversation_id=conv_native",
        )
        assert status == 200
        assert world_model["object"] == "nova.world_model"
        assert world_model["persistence"]["restart_safe"] is False
        assert world_model["data"]["conversation_id"] == "conv_native"
        assert world_model["data"]["turn_count"] == 1
        assert world_model["data"]["route_state"]["answer_source"] == "nova_core"

        for path in ("/health", "/nova/v1/health", "/nova/v1/capabilities", "/nova/v1/providers", "/nova/v1/models", "/nova/v1/tools", "/nova/v1/world-model"):
            status, _headers, payload = request_json(base_url, "GET", path)
            assert status == 200, (path, payload)
        status, _headers, capabilities = request_json(base_url, "GET", "/nova/v1/capabilities")
        assert capabilities["streaming"]["status"] == "FULL"
        assert capabilities["mcp"]["server"] == "NOT IMPLEMENTED"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_structured_output_stream_is_rejected_before_sse_headers(monkeypatch) -> None:
    _core, controller = isolated_controller()
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        status, _headers, payload = request_json(
            base_url,
            "POST",
            "/v1/chat/completions",
            {
                "model": "nova",
                "stream": True,
                "messages": [{"role": "user", "content": "Return JSON"}],
                "response_format": {"type": "json_object"},
            },
        )
        assert status == 400
        assert payload["error"]["type"] == "unsupported_feature"
        assert payload["error"]["param"] == "response_format"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_stream_client_disconnect_does_not_crash_server(monkeypatch) -> None:
    mock = MockProvider(chunks=[str(index) for index in range(200)])
    _core, controller = isolated_controller(provider=mock)
    monkeypatch.setattr(server, "NOVA_GATEWAY_HTTP", controller)
    httpd, base_url = start_server()
    try:
        request = urllib.request.Request(
            base_url + "/v1/chat/completions",
            data=json.dumps({"model": "nova-stream", "stream": True, "messages": [{"role": "user", "content": "Go"}]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        response = urllib.request.urlopen(request, timeout=10)
        response.readline()
        response.close()
        time.sleep(0.05)
        status, _headers, payload = request_json(base_url, "GET", "/health")
        assert status == 200
        assert payload["ok"] is True
    finally:
        httpd.shutdown()
        httpd.server_close()
