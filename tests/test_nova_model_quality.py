from contextlib import nullcontext
import base64
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_model_memory
import nova_model_quality


def test_builtin_vision_probe_is_a_real_png():
    decoded = base64.b64decode(nova_model_quality._RED_SQUARE_PNG_BASE64)

    assert decoded.startswith(b"\x89PNG\r\n\x1a\n")
    assert int.from_bytes(decoded[16:20], "big") == 64
    assert int.from_bytes(decoded[20:24], "big") == 64


def test_repeated_failures_quarantine_without_storing_content(tmp_path):
    now = [1_800_000_000.0]
    registry = nova_model_quality.NovaModelQualityRegistry(
        tmp_path / "quality.json",
        failure_threshold=2,
        quarantine_seconds=600,
        clock=lambda: now[0],
    )

    first = registry.record_failure(
        "ollama",
        "bad-model",
        reason="low_quality_vision_response",
        latency_ms=50,
        source="runtime",
    )
    second = registry.record_failure(
        "ollama",
        "bad-model",
        reason="low_quality_vision_response",
        latency_ms=70,
        source="runtime",
    )

    assert first["quarantined"] is False
    assert second["quarantined"] is True
    assert registry.is_quarantined("ollama", "bad-model") is True
    persisted = (tmp_path / "quality.json").read_text(encoding="utf-8")
    assert "low_quality_vision_response" in persisted
    assert "prompt" not in persisted.lower()
    assert "response_text" not in persisted.lower()
    assert "authorization" not in persisted.lower()


def test_verified_success_clears_quarantine_and_failure_streak(tmp_path):
    registry = nova_model_quality.NovaModelQualityRegistry(
        tmp_path / "quality.json",
        failure_threshold=2,
    )
    for _ in range(2):
        registry.record_failure(
            "ollama",
            "recoverable-model",
            reason="benchmark_output_mismatch",
            source="benchmark",
        )

    recovered = registry.record_success(
        "ollama",
        "recoverable-model",
        latency_ms=25,
        source="benchmark",
        verified=True,
    )

    assert recovered["quarantined"] is False
    assert recovered["status"] == "healthy"
    assert recovered["consecutive_failures"] == 0


def test_quarantine_expires_into_probation(tmp_path):
    now = [1_800_000_000.0]
    registry = nova_model_quality.NovaModelQualityRegistry(
        tmp_path / "quality.json",
        failure_threshold=2,
        quarantine_seconds=60,
        clock=lambda: now[0],
    )
    for _ in range(2):
        registry.record_failure(
            "ollama",
            "temporary-model",
            reason="timeout",
        )
    assert registry.is_quarantined("ollama", "temporary-model") is True

    now[0] += 61

    status = registry.model_status("ollama", "temporary-model")
    assert status["quarantined"] is False
    assert status["status"] == "probation"


def test_unknown_failure_reason_is_reduced_to_safe_category(tmp_path):
    registry = nova_model_quality.NovaModelQualityRegistry(
        tmp_path / "quality.json",
    )

    status = registry.record_failure(
        "ollama",
        "model",
        reason="private user prompt accidentally supplied here",
    )

    assert status["last_failure_reason"] == "provider_error"
    assert "private user prompt" not in (tmp_path / "quality.json").read_text(
        encoding="utf-8"
    )


def test_loaded_model_benchmark_passes_text_fails_vision_and_skips_raw(
    monkeypatch,
    tmp_path,
):
    registry = nova_model_quality.NovaModelQualityRegistry(
        tmp_path / "quality.json",
        failure_threshold=2,
    )
    registry.record_failure(
        "ollama",
        "moondream",
        reason="low_quality_vision_response",
    )
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [
            {"name": "qwen2.5:1.5b", "size_bytes": 1_200_000_000},
            {"name": "moondream:latest", "size_bytes": 1_300_000_000},
            {"name": "nova-dolphin3-lora", "size_bytes": 4_000_000_000},
        ],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "configured_ollama_model_role",
        lambda name: (
            "raw"
            if "dolphin" in name
            else "vision"
            if "moondream" in name
            else "primary"
        ),
    )
    monkeypatch.setattr(
        nova_model_memory,
        "nova_managed_ollama_models",
        lambda: {"qwen2.5:1.5b", "moondream", "nova-dolphin3-lora"},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **_kwargs: nullcontext(
            {"allowed": True, "content_logged": False}
        ),
    )
    monkeypatch.setattr(
        nova_model_memory,
        "_ollama_base_url",
        lambda: "http://127.0.0.1:11434",
    )

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        payload = json.loads(request.data.decode("utf-8"))
        if "moondream" in payload["model"]:
            return FakeResponse({"response": "xtalk"})
        return FakeResponse({"response": "NOVA_OK_731"})

    monkeypatch.setattr(
        nova_model_quality.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    result = nova_model_quality.benchmark_loaded_ollama_models(
        registry=registry,
        maximum_models=3,
        timeout_seconds=10,
    )

    by_role = {item["role"]: item for item in result["results"]}
    assert by_role["primary"]["status"] == "passed"
    assert by_role["vision"]["status"] == "failed"
    assert by_role["vision"]["quarantined"] is True
    assert by_role["raw"]["status"] == "skipped_raw_user_model"
    assert result["raw_adapter_modes_excluded"] is True
    assert result["content_logged"] is False


def test_loaded_model_benchmark_does_not_touch_or_extend_unmanaged_models(
    monkeypatch,
    tmp_path,
):
    registry = nova_model_quality.NovaModelQualityRegistry(tmp_path / "quality.json")
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [{"name": "user-qwen:14b", "size_bytes": 9_000_000_000}],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "configured_ollama_model_role",
        lambda _name: "managed",
    )
    monkeypatch.setattr(
        nova_model_memory,
        "nova_managed_ollama_models",
        lambda: {"qwen2.5:1.5b", "moondream"},
    )
    monkeypatch.setattr(
        nova_model_quality.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unmanaged resident models must not be benchmarked")
        ),
    )

    result = nova_model_quality.benchmark_loaded_ollama_models(
        registry=registry,
        maximum_models=1,
        timeout_seconds=10,
    )

    assert result["checked"] == 0
    assert result["results"][0]["status"] == "skipped_unmanaged_model"


def test_vision_transport_pass_does_not_clear_active_quality_quarantine(
    monkeypatch,
    tmp_path,
):
    registry = nova_model_quality.NovaModelQualityRegistry(
        tmp_path / "quality.json",
        failure_threshold=2,
    )
    for _ in range(2):
        registry.record_failure(
            "ollama",
            "moondream",
            reason="low_quality_vision_response",
        )
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [{"name": "moondream:latest", "size_bytes": 1_300_000_000}],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "configured_ollama_model_role",
        lambda _name: "vision",
    )
    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **_kwargs: nullcontext(
            {"allowed": True, "content_logged": False}
        ),
    )
    monkeypatch.setattr(
        nova_model_memory,
        "_ollama_base_url",
        lambda: "http://127.0.0.1:11434",
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {"response": "", "done": True, "done_reason": "stop"}
            ).encode("utf-8")

    monkeypatch.setattr(
        nova_model_quality.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    result = nova_model_quality.benchmark_loaded_ollama_models(
        registry=registry,
        maximum_models=1,
        timeout_seconds=10,
    )

    assert result["results"][0]["status"] == "passed"
    assert result["results"][0]["reason"] == "passed_transport"
    assert registry.is_quarantined("ollama", "moondream") is True
