from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.config import GatewayConfig  # noqa: E402
from nova_gateway.core import NovaGatewayCore  # noqa: E402
from nova_gateway.errors import UnsupportedFeatureError  # noqa: E402
from nova_gateway.http import NovaGatewayHttpController  # noqa: E402
from nova_gateway.auth import NovaAuthenticator, NovaClientRegistry  # noqa: E402


class FakeMediaEngine:
    def __init__(self, engine_id: str, *, ready: bool = True) -> None:
        self.engine_id = engine_id
        self.ready = ready
        self.calls: list[tuple[str, dict]] = []

    def health_check(self):
        return {"ok": self.ready, "status": "ready" if self.ready else "disabled"}

    def capabilities(self):
        return {"engine_id": self.engine_id, "available": self.ready}

    def text_to_video(self, prompt: str, **options):
        self.calls.append((prompt, dict(options)))
        return {"object": "nova.media_job", "job_id": "test-job", "engine_id": self.engine_id}

    def list_jobs(self, *, owner_id: str, limit: int = 25):
        return {"object": "list", "engine_id": self.engine_id, "data": []}


def _core(*, video_lite: FakeMediaEngine, animatediff: FakeMediaEngine) -> NovaGatewayCore:
    config = GatewayConfig(rate_limit_enabled=False, comfyui_enabled=False)
    return NovaGatewayCore(
        lambda text, context: ("answer", {"route": "nova_core"}),
        config=config,
        register_ollama=False,
        video_lite=video_lite,
        animatediff_cpu=animatediff,
    )


def test_requested_video_engine_is_selected_instead_of_default_precedence() -> None:
    lite = FakeMediaEngine("nova-video-lite")
    animatediff = FakeMediaEngine("nova-animatediff-cpu")
    core = _core(video_lite=lite, animatediff=animatediff)

    result = core.generate_video(
        {"prompt": "a good-looking cat", "engine_id": "nova-video-lite"},
        client_id="local-client",
    )

    assert result["engine_id"] == "nova-video-lite"
    assert lite.calls and not animatediff.calls
    assert lite.calls[0][0] == "a good-looking cat"


def test_unavailable_requested_video_engine_does_not_silently_fallback() -> None:
    lite = FakeMediaEngine("nova-video-lite", ready=False)
    animatediff = FakeMediaEngine("nova-animatediff-cpu")
    core = _core(video_lite=lite, animatediff=animatediff)

    with pytest.raises(UnsupportedFeatureError, match="nova-video-lite"):
        core.generate_video(
            {"prompt": "a cat", "engine_id": "nova-video-lite"},
            client_id="local-client",
        )


def test_media_payload_allows_engine_id_for_video_requests() -> None:
    payload = NovaGatewayHttpController._media_payload(
        {"prompt": "a cat", "engine_id": "nova-video-lite"},
        video=True,
    )
    assert payload["engine_id"] == "nova-video-lite"
