from pathlib import Path
import json
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_model_memory


def test_model_activity_is_counted_and_released():
    assert nova_model_memory.model_activity_status() == {}
    with nova_model_memory.model_activity("dolphin"):
        assert nova_model_memory.model_activity_status() == {"dolphin": 1}
    assert nova_model_memory.model_activity_status() == {}


def test_ollama_status_and_unload_use_local_runtime_api(monkeypatch):
    requests = []

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
        requests.append(request)
        if request.full_url.endswith("/api/ps"):
            return FakeResponse(
                {"models": [{"name": "nova-dolphin3-lora:latest", "size": 123, "size_vram": 0}]}
            )
        return FakeResponse({"done": True})

    monkeypatch.setattr(nova_model_memory.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(nova_model_memory, "_ollama_base_url", lambda: "http://127.0.0.1:11434")

    models = nova_model_memory.list_ollama_loaded_models()
    result = nova_model_memory.unload_ollama_model("nova-dolphin3-lora:latest")

    assert models[0]["name"] == "nova-dolphin3-lora:latest"
    assert result["unloaded"] is True
    unload_payload = json.loads(requests[-1].data.decode("utf-8"))
    assert unload_payload == {"model": "nova-dolphin3-lora:latest", "keep_alive": 0}


def test_installed_ollama_model_size_uses_local_registry_metadata(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "models": [
                        {"name": "qwen2.5:1.5b", "size": 986_000_000},
                        {"name": "qwen2.5:3b", "size": 1_900_000_000},
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        nova_model_memory.urllib.request,
        "urlopen",
        lambda request, timeout=None: FakeResponse(),
    )
    monkeypatch.setattr(
        nova_model_memory,
        "_ollama_base_url",
        lambda: "http://127.0.0.1:11434",
    )

    assert (
        nova_model_memory.installed_ollama_model_size_bytes(
            "qwen2.5:1.5b:latest"
        )
        == 986_000_000
    )
    assert nova_model_memory.installed_ollama_model_size_bytes("missing") == 0


def test_unload_model_memory_releases_idle_backends(monkeypatch):
    fake_runtime = SimpleNamespace(
        unload_cached_lora_runtimes=lambda force=False, family=None: {
            "ok": True,
            "unloaded": [{"base_model": "Qwen", "adapter_name": "qwen-adapter"}],
            "skipped": [],
        }
    )
    monkeypatch.setitem(sys.modules, "nova_lora_runtime", fake_runtime)
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [{"name": "nova-dolphin3-lora:latest"}, {"name": "unrelated-user-model:latest"}],
    )
    monkeypatch.setattr(nova_model_memory, "nova_managed_ollama_models", lambda: {"nova-dolphin3-lora"})
    monkeypatch.setattr(
        nova_model_memory,
        "unload_ollama_model",
        lambda name: {"model": name, "unloaded": True},
    )
    monkeypatch.setattr(nova_model_memory, "model_memory_status", lambda: {"ok": True, "refreshed": True})

    result = nova_model_memory.unload_model_memory("idle")

    assert result["ok"] is True
    assert [item["provider"] for item in result["unloaded"]] == ["huggingface", "ollama"]
    assert result["unloaded"][1]["model"] == "nova-dolphin3-lora:latest"
    assert result["status"]["refreshed"] is True


def test_unload_model_memory_protects_busy_dolphin(monkeypatch):
    monkeypatch.setattr(nova_model_memory, "model_memory_status", lambda: {"ok": True})
    with nova_model_memory.model_activity("dolphin"):
        result = nova_model_memory.unload_model_memory("dolphin")

    assert result["ok"] is False
    assert result["unloaded"] == []
    assert result["skipped"][0]["reason"] == "generation_in_progress"


def test_unload_model_memory_releases_only_managed_reviewer(monkeypatch):
    unloaded = []
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [
            {"name": "qwen2.5-coder:7b"},
            {"name": "qwen2.5:1.5b"},
            {"name": "unrelated-user-model:latest"},
        ],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "nova_managed_ollama_models",
        lambda: {"qwen2.5-coder:7b", "qwen2.5:1.5b"},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "nova_reviewer_ollama_models",
        lambda: {"qwen2.5-coder:7b"},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "unload_ollama_model",
        lambda name: unloaded.append(name) or {"model": name, "unloaded": True},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "model_memory_status",
        lambda: {"ok": True},
    )

    result = nova_model_memory.unload_model_memory("reviewer")

    assert result["ok"] is True
    assert unloaded == ["qwen2.5-coder:7b"]


def test_model_memory_status_reports_reviewer_residency(monkeypatch):
    fake_runtime = SimpleNamespace(runtime_cache_status=lambda: [])
    monkeypatch.setitem(sys.modules, "nova_lora_runtime", fake_runtime)
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [{"name": "qwen2.5-coder:7b", "size_bytes": 1}],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "nova_reviewer_ollama_models",
        lambda: {"qwen2.5-coder:7b"},
    )

    status = nova_model_memory.model_memory_status()

    assert status["reviewer"]["loaded"] is True
    assert status["reviewer"]["models"] == ["qwen2.5-coder:7b"]


def test_reviewer_model_registry_includes_middle_and_deep_configured_models(monkeypatch):
    config = SimpleNamespace(
        model="qwen2.5:1.5b",
        middle_reviewer_model_preferences=lambda _task: ("qwen2.5:3b",),
        escalation_model_preferences=lambda _task: ("qwen2.5-coder:7b",),
    )
    module = SimpleNamespace(LocalLLMConfig=lambda: config)
    monkeypatch.setitem(sys.modules, "nova_local_llm_connector", module)

    names = nova_model_memory.nova_reviewer_ollama_models()

    assert names == {"qwen2.5:3b", "qwen2.5-coder:7b"}


def test_adaptive_residency_keeps_models_when_headroom_is_already_safe(monkeypatch):
    monkeypatch.setenv("NOVA_ADAPTIVE_MODEL_MEMORY", "true")
    monkeypatch.setenv("NOVA_MODEL_MEMORY_RESERVE_GB", "1.5")
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {"available_physical_gb": 8.0},
    )
    monkeypatch.setattr(nova_model_memory, "list_ollama_loaded_models", lambda: [])
    monkeypatch.setattr(
        nova_model_memory,
        "unload_ollama_model",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("safe headroom must not unload anything")
        ),
    )

    decision = nova_model_memory.prepare_model_residency(
        "qwen2.5:3b",
        target_family="middle",
        estimated_model_bytes=2_000_000_000,
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "headroom_available"
    assert decision["evicted"] == []
    assert decision["content_logged"] is False
    assert decision["never_deletes_model_files"] is True


def test_vision_residency_can_use_bounded_commit_headroom_without_evicting_user_model(
    monkeypatch,
):
    unloaded = []
    monkeypatch.setenv("NOVA_ADAPTIVE_MODEL_MEMORY", "true")
    monkeypatch.setenv("NOVA_MODEL_MEMORY_RESERVE_GB", "1.5")
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {
            "available_physical_gb": 1.0,
            "available_commit_gb": 4.5,
        },
    )
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [{"name": "user-text-model", "size_bytes": 9_000_000_000}],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "unload_ollama_model",
        lambda name, timeout=20: unloaded.append(name),
    )

    decision = nova_model_memory.prepare_model_residency(
        "moondream",
        target_family="vision",
        estimated_model_bytes=1_800_000_000,
        allow_commit_fallback=True,
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "commit_headroom_available"
    assert decision["commit_fallback_used"] is True
    assert decision["available_commit_before_gb"] == 4.5
    assert unloaded == []


def test_commit_headroom_fallback_never_runs_with_dangerously_low_physical_ram(
    monkeypatch,
):
    monkeypatch.setenv("NOVA_ADAPTIVE_MODEL_MEMORY", "true")
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {
            "available_physical_gb": 0.4,
            "available_commit_gb": 10.0,
        },
    )
    monkeypatch.setattr(nova_model_memory, "list_ollama_loaded_models", lambda: [])

    decision = nova_model_memory.prepare_model_residency(
        "moondream",
        target_family="vision",
        estimated_model_bytes=1_800_000_000,
        allow_commit_fallback=True,
    )

    assert decision["allowed"] is False
    assert decision["reason"] == "insufficient_safe_memory"


def test_explicit_vision_handoff_releases_large_idle_text_runtime_only(monkeypatch):
    unloaded = []
    monkeypatch.setenv("NOVA_ADAPTIVE_MODEL_MEMORY", "true")
    monkeypatch.setenv("NOVA_MODEL_MEMORY_RESERVE_GB", "1.5")
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {
            "available_physical_gb": 0.9,
            "available_commit_gb": 4.5,
        },
    )
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [
            {"name": "user-text-model:14b", "size_bytes": 9_000_000_000},
            {"name": "nova-dolphin3-lora", "size_bytes": 5_000_000_000},
        ],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "unload_ollama_model",
        lambda name, timeout=20: unloaded.append(name) or {"unloaded": True},
    )

    decision = nova_model_memory.prepare_model_residency(
        "moondream",
        target_family="vision",
        estimated_model_bytes=1_800_000_000,
        allow_unmanaged_idle_handoff=True,
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "safe_headroom_created"
    assert decision["unmanaged_idle_handoff_used"] is True
    assert unloaded == ["user-text-model:14b"]
    assert any(
        item["reason"] == "raw_user_model_protected"
        for item in decision["skipped"]
    )


def test_adaptive_residency_unloads_idle_models_in_target_specific_order(monkeypatch):
    unloaded = []
    monkeypatch.setenv("NOVA_ADAPTIVE_MODEL_MEMORY", "true")
    monkeypatch.setenv("NOVA_MODEL_MEMORY_RESERVE_GB", "1.5")
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {"available_physical_gb": 2.0},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [
            {"name": "qwen2.5:3b", "size_bytes": 2_300_000_000},
            {"name": "moondream", "size_bytes": 1_500_000_000},
            {"name": "qwen2.5:1.5b", "size_bytes": 1_300_000_000},
        ],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "_configured_ollama_model_roles",
        lambda: {
            "primary": {"qwen2.5:1.5b"},
            "middle": {"qwen2.5:3b"},
            "deep": {"qwen2.5-coder:7b"},
            "vision": {"moondream"},
            "raw": {"nova-dolphin3-lora"},
        },
    )
    monkeypatch.setattr(
        nova_model_memory,
        "nova_managed_ollama_models",
        lambda: {"qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5-coder:7b", "moondream"},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "unload_ollama_model",
        lambda name, timeout=20: unloaded.append(name) or {"model": name, "unloaded": True},
    )

    decision = nova_model_memory.prepare_model_residency(
        "qwen2.5-coder:7b",
        target_family="deep",
        estimated_model_bytes=3_500_000_000,
    )

    assert decision["allowed"] is True
    assert unloaded == ["qwen2.5:3b", "moondream"]
    assert [item["role"] for item in decision["evicted"]] == ["middle", "vision"]
    assert decision["reason"] == "safe_headroom_created"


def test_adaptive_residency_never_evicts_raw_unmanaged_or_busy_models(monkeypatch):
    unloaded = []
    monkeypatch.setenv("NOVA_ADAPTIVE_MODEL_MEMORY", "true")
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {"available_physical_gb": 0.5},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [
            {"name": "nova-dolphin3-lora", "size_bytes": 5_000_000_000},
            {"name": "qwen2.5:3b", "size_bytes": 2_300_000_000},
            {"name": "user-model", "size_bytes": 6_000_000_000},
        ],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "_configured_ollama_model_roles",
        lambda: {
            "primary": {"qwen2.5:1.5b"},
            "middle": {"qwen2.5:3b"},
            "deep": {"qwen2.5-coder:7b"},
            "vision": {"moondream"},
            "raw": {"nova-dolphin3-lora"},
        },
    )
    monkeypatch.setattr(
        nova_model_memory,
        "nova_managed_ollama_models",
        lambda: {"nova-dolphin3-lora", "qwen2.5:3b"},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "unload_ollama_model",
        lambda name, timeout=20: unloaded.append(name) or {"model": name, "unloaded": True},
    )

    with nova_model_memory.model_activity("reviewer"):
        decision = nova_model_memory.prepare_model_residency(
            "qwen2.5-coder:7b",
            target_family="deep",
            estimated_model_bytes=4_500_000_000,
        )

    assert decision["allowed"] is False
    assert unloaded == []
    assert {item["reason"] for item in decision["skipped"]} == {
        "raw_user_model_protected",
        "generation_in_progress",
        "unmanaged_model_protected",
    }


def test_managed_residency_marks_target_busy_before_other_transition(monkeypatch):
    unloaded = []
    monkeypatch.setenv("NOVA_ADAPTIVE_MODEL_MEMORY", "true")
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {"available_physical_gb": 0.5},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [{"name": "qwen2.5:3b", "size_bytes": 2_500_000_000}],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "_configured_ollama_model_roles",
        lambda: {
            "primary": {"qwen2.5:1.5b"},
            "middle": {"qwen2.5:3b"},
            "deep": set(),
            "vision": set(),
            "raw": set(),
        },
    )
    monkeypatch.setattr(
        nova_model_memory,
        "nova_managed_ollama_models",
        lambda: {"qwen2.5:1.5b", "qwen2.5:3b"},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "unload_ollama_model",
        lambda name, timeout=20: unloaded.append(name) or {"model": name, "unloaded": True},
    )

    with nova_model_memory.managed_model_residency(
        "qwen2.5:3b",
        target_family="middle",
    ) as active:
        assert active["allowed"] is True
        assert nova_model_memory.model_activity_status()["reviewer"] == 1
        blocked = nova_model_memory.prepare_model_residency(
            "qwen2.5:1.5b",
            target_family="primary",
            estimated_model_bytes=1_500_000_000,
        )

    assert blocked["allowed"] is False
    assert unloaded == []
    assert blocked["skipped"][0]["reason"] == "generation_in_progress"
    assert nova_model_memory.model_activity_status() == {}
