import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nova_enhanced_server as server


def test_raw_qwen_adapter_prefers_dedicated_ollama_lora(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        server,
        "_adapter_compare_metadata",
        lambda adapter_id: {"base_model": "Qwen/Qwen2.5-1.5B-Instruct"},
    )
    monkeypatch.setenv(
        "NOVA_QWEN_LORA_OLLAMA_URL",
        "http://127.0.0.1:11434/api/chat",
    )
    monkeypatch.setattr(server, "_ollama_adapter_model_available", lambda *args, **kwargs: True)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {"message": {"role": "assistant", "content": "A raw Qwen answer."}}
            ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    result = server._generate_raw_lora_adapter(
        "Explain rain in one sentence.",
        "nova-qwen2-5-1-5b-big-sft-20260713",
        max_new_tokens=32,
    )

    assert result["raw_output"] == "A raw Qwen answer."
    assert result["provider"] == "ollama_lora_adapter"
    assert result["model"] == "nova-qwen2.5-1.5b-lora"
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["model"] == "nova-qwen2.5-1.5b-lora"
    assert captured["payload"]["messages"] == [
        {"role": "user", "content": "Explain rain in one sentence."}
    ]
    assert captured["payload"]["options"]["num_predict"] == 32


def test_raw_qwen_ollama_waits_for_slow_cpu_generation(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        server,
        "_adapter_compare_metadata",
        lambda adapter_id: {"base_model": "Qwen/Qwen2.5-1.5B-Instruct"},
    )
    monkeypatch.setenv("NOVA_QWEN_LORA_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    monkeypatch.delenv("NOVA_RAW_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("NOVA_DOLPHIN_LORA_OLLAMA_TIMEOUT", raising=False)
    monkeypatch.setattr(server, "_ollama_adapter_model_available", lambda *args, **kwargs: True)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps({"message": {"content": "The slow raw answer finished."}}).encode()

    def fake_urlopen(request, timeout=0):
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    result = server._generate_raw_lora_adapter(
        "Take your time and explain this carefully.",
        "nova-qwen2-5-1-5b-big-sft-20260713",
        max_new_tokens=256,
    )

    assert result["raw_output"] == "The slow raw answer finished."
    assert captured["timeout"] >= 1800
