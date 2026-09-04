from pathlib import Path
from contextlib import nullcontext
import json
import sys
import urllib.request
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_local_llm_connector as llm
import nova_llm_synthesizer
import nova_lora_runtime
from nova_model_quality import NovaModelQualityRegistry


@pytest.fixture(autouse=True)
def _isolated_model_quality_registry(monkeypatch, tmp_path):
    """Prevent managed connector tests from changing live quality state."""

    import nova_model_quality

    registry = NovaModelQualityRegistry(
        tmp_path / "model_quality.json",
        enabled=True,
    )
    monkeypatch.setattr(nova_model_quality, "_DEFAULT_REGISTRY", registry)
    yield


def test_qwen3_reasoning_control_is_selective_and_provider_neutral():
    prompt, metadata = llm.apply_qwen_reasoning_control(
        "Answer this.",
        "nova-qwen3-14b-8k",
        {"reasoning_mode": "deep", "reasoning_enabled": True, "reasoning_budget": 800},
    )
    assert prompt.startswith("/think\n")
    assert metadata["reasoning_enabled"] is True
    assert metadata["reasoning_budget"] == 800
    assert metadata["reasoning_content_stored"] is False

    fast_prompt, fast_metadata = llm.apply_qwen_reasoning_control(
        "Say hello.",
        "nova-qwen3-14b-8k",
        {"reasoning_mode": "fast", "reasoning_enabled": False},
    )
    assert fast_prompt.startswith("/no_think\n")
    assert fast_metadata["reasoning_enabled"] is False

    untouched, metadata = llm.apply_qwen_reasoning_control(
        "Raw Qwen 2.5 prompt.",
        "qwen2.5:1.5b",
        {"reasoning_mode": "deep"},
    )
    assert untouched == "Raw Qwen 2.5 prompt."
    assert metadata["provider_directive"] is None


def test_reasoning_cleaner_removes_complete_and_interrupted_private_traces():
    assert llm.clean_local_llm_output(
        "<think>private chain</think>Visible answer."
    ) == "Visible answer."
    assert llm.clean_local_llm_output(
        "Safe prefix.<think>unfinished private chain"
    ) == "Safe prefix."


def test_incremental_reasoning_filter_never_publishes_think_content():
    visible = []
    gate = llm._VisibleReasoningFilter(lambda value: visible.append(value) or True)
    for chunk in ("<thi", "nk>secret", " reasoning</thi", "nk>Final ", "answer."):
        assert gate.feed(chunk) is True
    assert gate.finish() is True
    assert "".join(visible) == "Final answer."
    assert "secret" not in "".join(visible)


def test_default_regular_local_llm_is_small_qwen_with_dolphin_reserved_for_direct_deep():
    assert llm.DEFAULT_LOCAL_LLM_MODEL == "qwen2.5:1.5b"
    assert llm.DEFAULT_FAST_LOCAL_LLM_MODEL == "qwen2.5:1.5b"
    assert llm.DEFAULT_DEEP_LOCAL_LLM_MODEL == "qwen2.5:1.5b"
    assert llm.DEFAULT_DIRECT_DEEPSEEK_MODEL == "dolphin3"
    assert llm.DEFAULT_LOCAL_LLM_CONTEXT == 8192
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LOCAL_LLM_MODEL"] == "qwen2.5:1.5b"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_FAST_LOCAL_LLM_MODEL"] == "qwen2.5:1.5b"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_DEEP_LOCAL_LLM_MODEL"] == "qwen2.5:1.5b"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_DIRECT_DEEPSEEK_MODEL"] == "dolphin3"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_DIRECT_DEEPSEEK_TIMEOUT"] >= 180
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LOCAL_LLM_CONTEXT"] == 8192
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_NATURAL_CHAT"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_ULTRA_THINK"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_AGENT_MODE"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_AGENT_MAX_STEPS"] == 6
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_AGENT_REQUIRE_APPROVAL"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_AGENT_ALLOW_SHELL"] is False
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_AGENT_ALLOW_FILE_WRITE"] is False
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_AGENT_ALLOW_WEB"] is False
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_AGENT_TRACE"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LORA_ADAPTER_ENABLED"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LORA_BASE_MODEL"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LORA_RUNTIME_ENABLED"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LORA_DEVICE"] == "auto"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LORA_MAX_NEW_TOKENS"] == 256
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LORA_AUTO_MODE"] == "ollama_qwen_first"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_REGULAR_CHAT_ESCALATION_ENABLED"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_MIDDLE_REVIEWER_ENABLED"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_DIRECT_MIDDLE_ENABLED"] is True
    assert llm.LocalLLMConfig().direct_middle_threshold == 0.84
    assert llm.LocalLLMConfig().direct_middle_max_tokens == 256
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_MIDDLE_REVIEWER_MIN_MODEL_BYTES"] < 3_000_000_000
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_MIDDLE_REVIEWER_MAX_MODEL_BYTES"] == 3_000_000_000
    assert llm.LocalLLMConfig().middle_reviewer_model_preferences("reasoning")[0] == "qwen2.5:3b"
    assert llm.LocalLLMConfig().middle_reviewer_warmup_min_available_gb == 5.0
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_ESCALATION_MIN_MODEL_BYTES"] == 3_000_000_000
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_ESCALATION_MAX_MODEL_BYTES"] == 8_000_000_000
    assert llm.LocalLLMConfig().escalation_model_preferences("reasoning")[0] == "qwen2.5-coder:7b"
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_ALLOW_MODEL_DOWNLOADS"] is False
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_MODEL_WARMUP"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_MODEL_WARMUP_DELAY_SECONDS"] >= 1
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_MODEL_WARMUP_TIMEOUT"] >= 30
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_OLLAMA_KEEP_ALIVE"]
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_REVIEWER_WARMUP"] is True
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_REVIEWER_WARMUP_MIN_AVAILABLE_GB"] >= 2
    assert llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_REVIEWER_KEEP_ALIVE"]
    assert llm.LocalLLMConfig().allow_model_downloads is False


def test_optional_strong_model_configuration_is_explicit_and_does_not_replace_default():
    config = llm.LocalLLMConfig()
    json_config = json.loads((ROOT / "nova_llm_config.json").read_text(encoding="utf-8"))

    assert config.optional_strong_model == "qwen3:8b"
    assert config.optional_strong_timeout == 240
    assert config.optional_strong_keep_alive == "5m"
    assert json_config["NOVA_OPTIONAL_STRONG_MODEL"] == "qwen3:8b"
    assert json_config["NOVA_OPTIONAL_STRONG_TIMEOUT"] == 240
    assert json_config["NOVA_OPTIONAL_STRONG_KEEP_ALIVE"] == "5m"
    assert config.deep_model != config.optional_strong_model


def test_portable_local_llm_config_selects_small_qwen_for_regular_chat():
    json_config = json.loads((ROOT / "nova_llm_config.json").read_text(encoding="utf-8"))

    assert json_config["NOVA_LOCAL_LLM_MODEL"] == "qwen2.5:1.5b"
    assert json_config["NOVA_FAST_LOCAL_LLM_MODEL"] == "qwen2.5:1.5b"
    assert json_config["NOVA_DEEP_LOCAL_LLM_MODEL"] == "qwen2.5:1.5b"
    assert json_config["NOVA_DIRECT_DEEPSEEK_MODEL"] == "dolphin3"
    assert json_config["NOVA_DIRECT_DEEPSEEK_TIMEOUT"] == 180
    assert json_config["NOVA_LOCAL_LLM_CONTEXT"] == 8192
    assert json_config["NOVA_NATURAL_CHAT"] is True
    assert json_config["NOVA_ULTRA_THINK"] is True
    assert json_config["NOVA_AGENT_MODE"] is True
    assert json_config["NOVA_AGENT_MAX_STEPS"] == 6
    assert json_config["NOVA_AGENT_REQUIRE_APPROVAL"] is True
    assert json_config["NOVA_AGENT_ALLOW_SHELL"] is False
    assert json_config["NOVA_AGENT_ALLOW_FILE_WRITE"] is False
    assert json_config["NOVA_AGENT_ALLOW_WEB"] is False
    assert json_config["NOVA_AGENT_TRACE"] is True
    assert json_config["NOVA_LORA_ADAPTER_ENABLED"] is True
    assert json_config["NOVA_LORA_BASE_MODEL"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert json_config["NOVA_LORA_RUNTIME_ENABLED"] is True
    assert json_config["NOVA_LORA_DEVICE"] == "auto"
    assert json_config["NOVA_LORA_MAX_NEW_TOKENS"] == 256
    assert json_config["NOVA_LORA_AUTO_MODE"] == "ollama_qwen_first"
    assert json_config["NOVA_REGULAR_CHAT_ESCALATION_ENABLED"] is True
    assert json_config["NOVA_ESCALATION_MIN_MODEL_BYTES"] == 3_000_000_000
    assert json_config["NOVA_ESCALATION_MAX_MODEL_BYTES"] == 8_000_000_000
    assert (
        json_config["NOVA_ESCALATION_REASONING_MODELS"].split(",", 1)[0]
        == "qwen2.5-coder:7b"
    )


def test_lora_adapter_config_properties_can_be_read_from_file(tmp_path, monkeypatch):
    config_file = tmp_path / ".nova_llm_config"
    config_file.write_text(
        "NOVA_LORA_ADAPTER_ENABLED=true\n"
        "NOVA_LORA_ADAPTER_PATH=models/lora_adapters/nova-test\n"
        "NOVA_LORA_BASE_MODEL=Qwen/Qwen2.5-1.5B-Instruct\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm, "ROOT", tmp_path)

    config = llm.LocalLLMConfig()

    assert config.lora_adapter_enabled is True
    assert config.lora_adapter_path == "models/lora_adapters/nova-test"
    assert config.lora_base_model == "Qwen/Qwen2.5-1.5B-Instruct"


def test_portable_json_config_is_loaded_before_machine_local_overrides(tmp_path, monkeypatch):
    (tmp_path / "nova_llm_config.json").write_text(
        json.dumps(
            {
                "NOVA_USE_LOCAL_LLM": True,
                "NOVA_LOCAL_LLM_MODEL": "portable-small-model",
                "NOVA_LOCAL_LLM_CONTEXT": 8192,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".nova_llm_config").write_text(
        "NOVA_LOCAL_LLM_MODEL=machine-specific-model\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm, "ROOT", tmp_path)

    config = llm.LocalLLMConfig()

    assert config.use_local_llm is True
    assert config.model == "machine-specific-model"
    assert config.context_window == 8192


def test_local_llm_timeout_and_context_allow_cpu_qwen_to_finish():
    json_config = json.loads((ROOT / "nova_llm_config.json").read_text(encoding="utf-8"))

    assert 30 <= llm.LocalLLMConfig.DEFAULT_CONFIG["NOVA_LOCAL_LLM_TIMEOUT"] <= 120
    assert 30 <= json_config["NOVA_LOCAL_LLM_TIMEOUT"] <= 120
    assert json_config["NOVA_LOCAL_LLM_CONTEXT"] == 8192


def test_deepseek_thinking_block_is_removed_from_local_llm_output():
    raw = "<think>\nprivate reasoning that should not be shown\n</think>\n\nFinal answer only."

    assert llm.clean_local_llm_output(raw) == "Final answer only."


def test_local_llm_connector_allows_raw_prompt_override():
    connector = llm.LocalLLMConnector()

    assert connector._build_prompt({"raw_prompt": "Return JSON only."}) == "Return JSON only."


def test_local_llm_response_serializes_finish_reason():
    response = llm.LocalLLMResponse(
        local_llm_used=True,
        raw_output="Partial",
        finish_reason="length",
    )

    assert response.finish_reason == "length"
    assert response.to_dict()["finish_reason"] == "length"


def test_local_llm_warmup_prefers_cached_lora_without_generation(monkeypatch):
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_MODEL_WARMUP": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_AUTO_MODE": "qwen_first",
        }
    )
    observed = {}

    def fake_warm_up_lora(actual_config):
        observed["config"] = actual_config
        return {"ok": True, "state": "ready", "provider": "hf_peft_lora", "model": "Nova test adapter"}

    monkeypatch.setattr(nova_lora_runtime, "warm_up_lora", fake_warm_up_lora)

    result = llm.LocalLLMConnector(config).warm_up()

    assert result["ok"] is True
    assert result["provider"] == "hf_peft_lora"
    assert observed["config"] is config


def test_local_llm_warmup_falls_back_to_ollama_keep_alive(monkeypatch):
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_MODEL_WARMUP": True,
            "NOVA_LOCAL_LLM_PROVIDER": "ollama",
            "NOVA_LOCAL_LLM_MODEL": "nova-test-model",
            "NOVA_LORA_AUTO_MODE": "ollama_qwen_first",
            "NOVA_MODEL_WARMUP_TIMEOUT": 45,
            "NOVA_OLLAMA_KEEP_ALIVE": "20m",
        }
    )
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"done":true}'

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        nova_lora_runtime,
        "warm_up_lora",
        lambda _config: (_ for _ in ()).throw(
            AssertionError("Ollama Qwen primary warm-up must not load a Hugging Face adapter")
        ),
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = llm.LocalLLMConnector(config).warm_up()

    assert result["ok"] is True
    assert result["provider"] == "ollama"
    assert captured["payload"]["prompt"] == ""
    assert captured["payload"]["options"]["num_predict"] == 0
    assert captured["payload"]["keep_alive"] == "20m"
    assert captured["timeout"] == 45


def test_local_llm_connector_injects_dolphin_nova_training_profile():
    connector = llm.LocalLLMConnector()

    prompt = connector._build_prompt({"user_message": "How should Nova talk?"})

    assert "DOLPHIN NOVA TRAINING PROFILE" in prompt
    assert "Dolphin is Nova Creature's fast first language cortex" in prompt
    assert "If you are unsure, say what you know and what you do not know" in prompt


def test_normal_chat_synthesis_uses_short_generation_budget():
    _prompt, options = nova_llm_synthesizer._build_prompt(
        {
            "user_question": "How are you doing today?",
            "route": "general_conversation",
            "system_prompt": "",
        }
    )

    assert options["num_predict"] <= 160


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
    assert captured["payload"]["options"]["num_ctx"] == 8192
    assert captured["payload"]["keep_alive"] == connector.config.ollama_keep_alive


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
        model_override="example-override-model",
        timeout_override=20,
    )

    assert response.local_llm_used is True
    assert response.model == "example-override-model"
    assert captured["payload"]["model"] == "example-override-model"
    assert captured["payload"]["keep_alive"] == connector.config.ollama_keep_alive
    assert captured["timeout"] == 20


def test_local_llm_connector_accepts_bounded_keep_alive_override(monkeypatch):
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
        return FakeResponse()

    monkeypatch.setattr(llm, "HAS_HTTPX", False)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    connector = llm.LocalLLMConnector()
    response = connector.generate(
        {
            "raw_prompt": "Use the middle local model.",
            "local_llm_model": "qwen2.5:3b",
            "local_llm_keep_alive": "10m",
        }
    )

    assert response.local_llm_used is True
    assert captured["payload"]["model"] == "qwen2.5:3b"
    assert captured["payload"]["keep_alive"] == "10m"


def test_local_llm_connector_runs_managed_generation_inside_residency_guard(monkeypatch):
    connector = llm.LocalLLMConnector()
    captured = {}
    decision = {
        "enabled": True,
        "allowed": True,
        "reason": "headroom_available",
        "content_logged": False,
    }
    monkeypatch.setattr(
        connector,
        "_ollama_residency_context",
        lambda context, model, family: (
            captured.update(model=model, family=family) or nullcontext(decision)
        ),
    )
    monkeypatch.setattr(
        connector,
        "_call_ollama",
        lambda prompt, **kwargs: llm.LocalLLMResponse(
            local_llm_used=True,
            provider="ollama",
            model=kwargs.get("model_override"),
            raw_output="managed answer",
        ),
    )

    context = {
        "raw_prompt": "Answer through Nova.",
        "local_llm_model": "qwen2.5:3b",
        "primary_model_tier": "middle",
        "adaptive_model_memory": True,
    }
    response = connector.generate(context)

    assert response.local_llm_used is True
    assert captured == {"model": "qwen2.5:3b", "family": "middle"}
    assert context["model_residency"] == decision


def test_primary_residency_uses_installed_model_size_instead_of_family_guess(
    monkeypatch,
):
    import nova_model_memory

    captured = {}

    monkeypatch.setattr(
        nova_model_memory,
        "installed_ollama_model_size_bytes",
        lambda model_name: 986_000_000,
    )

    def fake_residency(model_name, **kwargs):
        captured.update(model=model_name, **kwargs)
        return nullcontext(
            {
                "enabled": True,
                "allowed": True,
                "reason": "headroom_available",
            }
        )

    monkeypatch.setattr(nova_model_memory, "managed_model_residency", fake_residency)

    connector = llm.LocalLLMConnector()
    with connector._ollama_residency_context(
        {"adaptive_model_memory": True},
        "qwen2.5:1.5b",
        "primary",
    ) as decision:
        assert decision["allowed"] is True

    assert captured["estimated_model_bytes"] == 986_000_000


def test_local_llm_connector_does_not_load_model_when_residency_guard_blocks(monkeypatch):
    connector = llm.LocalLLMConnector()
    monkeypatch.setattr(
        connector,
        "_ollama_residency_context",
        lambda *_args, **_kwargs: nullcontext(
            {
                "enabled": True,
                "allowed": False,
                "reason": "insufficient_safe_memory",
                "content_logged": False,
            }
        ),
    )
    monkeypatch.setattr(
        connector,
        "_call_ollama",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("a blocked model must not load")
        ),
    )

    response = connector.generate(
        {
            "raw_prompt": "Answer through Nova.",
            "adaptive_model_memory": True,
        }
    )

    assert response.local_llm_used is False
    assert response.fallback_used is True
    assert response.error == "adaptive_model_memory:insufficient_safe_memory"


def test_local_llm_connector_skips_quarantined_managed_model(monkeypatch):
    import nova_model_quality

    registry = nova_model_quality.get_default_model_quality_registry()
    registry.record_failure(
        "ollama",
        "qwen2.5:1.5b",
        reason="provider_error",
    )
    registry.record_failure(
        "ollama",
        "qwen2.5:1.5b",
        reason="provider_error",
    )
    connector = llm.LocalLLMConnector()
    monkeypatch.setattr(
        connector,
        "_call_ollama",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("a quarantined managed model must not be loaded")
        ),
    )

    response = connector.generate(
        {
            "raw_prompt": "Answer through Nova.",
            "local_llm_model": "qwen2.5:1.5b",
            "adaptive_model_memory": True,
        }
    )

    assert response.local_llm_used is False
    assert response.error == "adaptive_model_memory:model_quality_quarantined"
    assert registry.model_status("ollama", "qwen2.5:1.5b")["quarantined"] is True


def test_local_llm_connector_consumes_true_ollama_ndjson_stream(monkeypatch):
    captured = {}
    emitted = []

    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __iter__(self):
            return iter(
                [
                    b'{"response":"Nova ","done":false}\n',
                    b'{"response":"streams.","done":false}\n',
                    b'{"response":"","done":true}\n',
                ]
            )

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeStreamResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    connector = llm.LocalLLMConnector()
    response = connector._call_ollama_stream(
        "Stream this.",
        lambda delta: emitted.append(delta) or True,
        model_override="stream-model",
        timeout_override=17,
    )

    assert response.local_llm_used is True
    assert response.raw_output == "Nova streams."
    assert emitted == ["Nova ", "streams."]
    assert captured["payload"]["keep_alive"] == connector.config.ollama_keep_alive
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["model"] == "stream-model"
    assert captured["timeout"] == 17


def test_hybrid_router_direct_llm_fallback_uses_configured_model_timeout_and_cleaner():
    source = (ROOT / "src" / "nova_hybrid_router.py").read_text(encoding="utf-8")

    assert '"model": "deepseek-r1:7b"' not in source
    assert '"model": _llm_config.deep_model' in source
    assert "timeout=max(120, _llm_config.timeout)" in source
    assert "clean_local_llm_output" in source
