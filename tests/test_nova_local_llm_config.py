from pathlib import Path
import json
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_local_llm_connector as llm


def test_default_local_llm_model_is_deepseek_r1_7b():
    assert llm.DEFAULT_LOCAL_LLM_MODEL == "deepseek-r1:7b"
    assert llm.DEFAULT_FAST_LOCAL_LLM_MODEL == "qwen2.5:1.5b"
    assert llm.DEFAULT_DEEP_LOCAL_LLM_MODEL == "deepseek-r1:7b"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LOCAL_LLM_MODEL"] == "deepseek-r1:7b"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_FAST_LOCAL_LLM_MODEL"] == "qwen2.5:1.5b"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_DEEP_LOCAL_LLM_MODEL"] == "deepseek-r1:7b"


def test_checked_in_local_llm_configs_select_deepseek_r1_7b():
    env_config = (ROOT / ".nova_llm_config").read_text(encoding="utf-8")
    json_config = json.loads((ROOT / "nova_llm_config.json").read_text(encoding="utf-8"))

    assert "NOVA_LOCAL_LLM_MODEL=deepseek-r1:7b" in env_config
    assert "NOVA_FAST_LOCAL_LLM_MODEL=qwen2.5:1.5b" in env_config
    assert "NOVA_DEEP_LOCAL_LLM_MODEL=deepseek-r1:7b" in env_config
    assert json_config["NOVA_LOCAL_LLM_MODEL"] == "deepseek-r1:7b"
    assert json_config["NOVA_FAST_LOCAL_LLM_MODEL"] == "qwen2.5:1.5b"
    assert json_config["NOVA_DEEP_LOCAL_LLM_MODEL"] == "deepseek-r1:7b"


def test_local_llm_timeout_allows_deepseek_r1_7b_runtime():
    env_config = (ROOT / ".nova_llm_config").read_text(encoding="utf-8")
    json_config = json.loads((ROOT / "nova_llm_config.json").read_text(encoding="utf-8"))

    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LOCAL_LLM_TIMEOUT"] >= 120
    assert "NOVA_LOCAL_LLM_TIMEOUT=120" in env_config
    assert json_config["NOVA_LOCAL_LLM_TIMEOUT"] >= 120


def test_deepseek_thinking_block_is_removed_from_local_llm_output():
    raw = "<think>\nprivate reasoning that should not be shown\n</think>\n\nFinal answer only."

    assert llm.clean_local_llm_output(raw) == "Final answer only."


def test_local_llm_connector_allows_raw_prompt_override():
    connector = llm.LocalLLMConnector()

    assert connector._build_prompt({"raw_prompt": "Return JSON only."}) == "Return JSON only."


def test_local_llm_connector_accepts_ollama_option_overrides(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"response":"OK"}'

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm, "HAS_HTTPX", False)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    connector = llm.LocalLLMConnector()
    response = connector._call_ollama(
        "Return JSON.",
        options_override={"temperature": 0, "num_predict": 700},
    )

    assert response.local_llm_used is True
    assert captured["payload"]["options"]["temperature"] == 0
    assert captured["payload"]["options"]["num_predict"] == 700


def test_local_llm_connector_accepts_model_and_timeout_overrides(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"response":"OK"}'

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm, "HAS_HTTPX", False)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    connector = llm.LocalLLMConnector()
    response = connector._call_ollama(
        "Fast answer.",
        model_override="qwen2.5:1.5b",
        timeout_override=20,
    )

    assert response.local_llm_used is True
    assert response.model == "qwen2.5:1.5b"
    assert captured["payload"]["model"] == "qwen2.5:1.5b"
    assert captured["timeout"] == 20


def test_hybrid_router_direct_llm_fallback_uses_deepseek_safe_timeout_and_cleaner():
    source = (ROOT / "src" / "nova_hybrid_router.py").read_text(encoding="utf-8")

    assert '"model": "deepseek-r1:7b"' in source
    assert "timeout=120" in source
    assert "clean_local_llm_output" in source
