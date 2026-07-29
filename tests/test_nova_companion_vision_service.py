from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import nova_enhanced_server as server  # noqa: E402


class _VisionRequest:
    def __init__(self, *, pairing_required=False):
        self.pairing_required = pairing_required

    def _pairing_required_for_client(self):
        return self.pairing_required

    def _handle_companion_vision_post(self, _path):
        return True

    def _read_json_body(self):
        return {}

    def _send_json(self, _payload, status=200):
        return status


class _VisionRequestWithoutAuthorization:
    _handle_companion_vision_post = _VisionRequest._handle_companion_vision_post
    _read_json_body = _VisionRequest._read_json_body
    _send_json = _VisionRequest._send_json


def test_companion_projects_existing_local_vision_service_without_claiming_model_image_input(
    monkeypatch,
):
    monkeypatch.setattr(
        server, "_vision_response_from_upload", lambda _body: ({}, 200), raising=False
    )
    service = server._companion_vision_service_status(_VisionRequest())

    assert service["available"] is True
    assert service["tool_name"] == "vision.observe"
    assert service["endpoint"] == "/api/vision"
    assert service["availability_status"] == "requires_live_input"
    assert service["image_input"] is False


def test_companion_vision_readiness_covers_dispatch_and_current_authorization(monkeypatch):
    monkeypatch.setattr(
        server, "_vision_response_from_upload", lambda _body: ({}, 200), raising=False
    )
    ready = server._companion_vision_route_readiness(_VisionRequest())
    unpaired = server._companion_vision_route_readiness(
        _VisionRequest(pairing_required=True)
    )
    monkeypatch.setattr(server, "_vision_response_from_upload", None)
    missing_dispatch = server._companion_vision_route_readiness(_VisionRequest())

    assert ready["available"] is True
    assert unpaired["available"] is False
    assert "pair" in unpaired["reason"].lower()
    assert missing_dispatch["available"] is False
    assert "unavailable" in missing_dispatch["reason"].lower()


def test_companion_vision_health_is_unknown_without_a_current_request():
    service = server._companion_vision_service_status()

    assert service["available"] is False
    assert service["health"] == "unknown"


def test_companion_vision_health_is_unknown_without_an_authorization_predicate():
    service = server._companion_vision_service_status(
        _VisionRequestWithoutAuthorization()
    )

    assert service["available"] is False
    assert service["health"] == "unknown"


def test_vision_post_dispatch_uses_the_same_readiness_predicate(monkeypatch):
    responses = []
    handler = object.__new__(server.NovaHandler)
    handler._send_json = lambda payload, status=200: responses.append((payload, status))
    handler._read_json_body = lambda: (_ for _ in ()).throw(
        AssertionError("an unavailable route must not read image content")
    )
    monkeypatch.setattr(
        server,
        "_companion_vision_route_readiness",
        lambda _handler: {
            "available": False,
            "reason": "The local /api/vision service is unavailable.",
        },
    )

    handled = handler._handle_companion_vision_post("/api/vision")

    assert handled is True
    assert responses == [
        (
            {
                "ok": False,
                "error": "The local /api/vision service is unavailable.",
                "code": "vision_unavailable",
            },
            503,
        )
    ]
