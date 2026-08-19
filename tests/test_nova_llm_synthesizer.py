from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_local_llm_connector
import nova_llm_synthesizer as synthesizer


def test_synthesizer_uses_raw_output_from_local_llm_response(monkeypatch):
    class FakeConnector:
        def generate(self, context_packet):
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Final answer from Dolphin3.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "You are Nova.",
            "user_question": "Explain loops.",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "Final answer from Dolphin3."


def test_synthesizer_rejects_provider_output_cut_off_by_token_limit(monkeypatch):
    class FakeConnector:
        def generate(self, context_packet):
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Start with the ingredients, mix them, and then transfer",
                fallback_reason=None,
                finish_reason="length",
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "You are Nova.",
            "user_question": "Give me complete instructions.",
        }
    )

    assert answer is None
    assert ok is False
    assert error == "llm_output_truncated"


def test_synthesizer_sends_built_prompt_to_local_llm(monkeypatch):
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Robots should test code before users see it.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    synthesizer.generate(
        {
            "system_prompt": "System rules here.",
            "user_question": "Why test robot code?",
        }
    )

    assert "raw_prompt" in captured
    assert "System rules here." in captured["raw_prompt"]
    assert "Why test robot code?" in captured["raw_prompt"]
    assert captured["local_llm_model"] == "qwen2.5:1.5b"
    assert captured["local_llm_timeout"] == nova_local_llm_connector.LocalLLMConfig().timeout
    assert 30 <= captured["local_llm_timeout"] <= 120
    assert captured["ollama_options"]["num_ctx"] == nova_local_llm_connector.LocalLLMConfig().context_window


def test_synthesizer_returns_content_free_model_residency_to_cognitive_trace(monkeypatch):
    class FakeConnector:
        def generate(self, context_packet):
            context_packet["model_residency"] = {
                "allowed": True,
                "reason": "headroom_available",
                "content_logged": False,
            }
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Nova's managed local answer.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)
    packet = {
        "system_prompt": "You are Nova.",
        "user_question": "Give one local answer.",
        "adaptive_model_memory": True,
    }

    answer, ok, error = synthesizer.generate(packet)

    assert ok is True
    assert error is None
    assert answer == "Nova's managed local answer."
    assert packet["_model_residency"]["reason"] == "headroom_available"
    assert packet["_model_residency"]["content_logged"] is False


def test_synthesizer_honors_direct_middle_primary_override(monkeypatch):
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                provider="ollama",
                model="qwen2.5:3b",
                raw_output="Use local storage first, then add consent-based remote sync.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "You are Nova.",
            "user_question": "Compare local and remote storage, then recommend a staged design.",
            "primary_model_override": "qwen2.5:3b",
            "primary_model_timeout": 175,
            "local_llm_keep_alive": "10m",
            "memory_context": "- The user prefers local-first designs.",
            "conversation_context": "User previously asked about phone privacy.",
            "primary_model_guidance": [
                "Local storage works offline; remote storage needs connectivity unless cached."
            ],
            "primary_model_required_aspects": [
                "privacy",
                "offline behavior",
                "latency",
                "migration risk",
                "cost",
            ],
        }
    )

    assert ok is True
    assert error is None
    assert answer.startswith("Use local storage")
    assert captured["local_llm_model"] == "qwen2.5:3b"
    assert captured["local_llm_timeout"] == 175
    assert captured["local_llm_keep_alive"] == "10m"
    assert captured["ollama_options"]["num_ctx"] == 4096
    assert captured["ollama_options"]["num_predict"] >= 256
    assert captured["ollama_options"]["temperature"] <= 0.2
    assert captured["ollama_options"]["seed"] == 0
    assert captured["raw_prompt"].startswith("You are Nova Creature's local reasoning cortex.")
    assert "The user prefers local-first designs." in captured["raw_prompt"]
    assert "User previously asked about phone privacy." in captured["raw_prompt"]
    assert "NOVA VERIFIED TECHNICAL INVARIANTS" in captured["raw_prompt"]
    assert "unless cached" in captured["raw_prompt"]
    assert "MANDATORY REQUESTED COVERAGE" in captured["raw_prompt"]
    assert "\n- cost" in captured["raw_prompt"]
    assert "Keep the complete answer under 200 words" in captured["raw_prompt"]
    assert "exactly one final Recommendation line" in captured["raw_prompt"]


def test_synthesizer_obeys_explicit_one_idea_request_with_small_budget(monkeypatch):
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                provider="ollama",
                model="qwen2.5:1.5b",
                raw_output=(
                    "Keep one short checklist with each task, its next action, and its status."
                ),
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "You are Nova.",
            "user_question": (
                "Give me one practical idea for keeping a small personal project organized."
            ),
            "memory_context": "- The user likes local tools.",
        }
    )

    assert ok is True
    assert error is None
    assert answer.startswith("Keep one short checklist")
    assert captured["local_llm_model"] == "qwen2.5:1.5b"
    assert captured["ollama_options"]["num_predict"] == 72
    assert captured["ollama_options"]["num_ctx"] == 4096
    assert captured["ollama_options"]["stop"] == [". "]
    assert "Follow the user's requested count and length exactly" in captured["raw_prompt"]
    assert "The user likes local tools." in captured["raw_prompt"]
    assert synthesizer._finish_explicit_brief_sentence(
        "Keep one short checklist",
        {"stop": [". "]},
    ) == "Keep one short checklist."


def test_synthesizer_smart_default_uses_natural_nova_prompt(monkeypatch):
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                provider="ollama",
                model="dolphin3",
                raw_output="Direct answer.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "System rules here. " * 300,
            "user_question": "WHEN DID THEY WRITE THE BIBLE",
            "route": "general_conversation",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "Direct answer."
    assert captured["raw_prompt"].startswith("SYSTEM:\nYou are Nova Creature.")
    assert "You speak like a real human having a natural conversation." in captured["raw_prompt"]
    assert "NOVA CONVERSATION STATE:" in captured["raw_prompt"]
    assert "NOVA ROUTER CONTEXT:" in captured["raw_prompt"]
    assert "System rules here." in captured["raw_prompt"]
    assert "CURRENT USER MESSAGE:\nWHEN DID THEY WRITE THE BIBLE" in captured["raw_prompt"]
    assert "Your job is to help word the final answer" not in captured["raw_prompt"]


def test_synthesizer_retries_lora_when_dolphin_answer_is_generic(monkeypatch):
    calls = []

    class FakeConnector:
        def generate(self, context_packet):
            calls.append(dict(context_packet))
            if context_packet.get("use_lora_runtime"):
                return SimpleNamespace(
                    local_llm_used=True,
                    provider="hf_peft_lora",
                    model="Qwen/Qwen2.5-1.5B-Instruct + LoRA",
                    raw_output="The Bible was written over many centuries, with major parts composed from roughly 1200 BC to the 1st century AD.",
                    fallback_reason=None,
                )
            return SimpleNamespace(
                local_llm_used=True,
                provider="ollama",
                model="dolphin3",
                raw_output="I'm here with you. Tell me what you want to do next.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "System rules here.",
            "user_question": "When did they write the Bible?",
            "route": "general_conversation",
        }
    )

    assert ok is True
    assert error is None
    assert "major parts" in answer
    assert calls[0].get("use_lora_runtime") is None
    assert calls[1]["use_lora_runtime"] is True
    assert calls[1]["lora_retry_after_dolphin"] is True
    assert synthesizer.LAST_LOCAL_LLM_MODEL == "Qwen/Qwen2.5-1.5B-Instruct + LoRA"


def test_synthesizer_keeps_good_dolphin_answer_without_lora_retry(monkeypatch):
    calls = []

    class FakeConnector:
        def generate(self, context_packet):
            calls.append(dict(context_packet))
            return SimpleNamespace(
                local_llm_used=True,
                provider="ollama",
                model="dolphin3",
                raw_output="The Bible was written over many centuries, with major texts composed from roughly 1200 BC through the 1st century AD.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "System rules here.",
            "user_question": "When did they write the Bible?",
            "route": "general_conversation",
        }
    )

    assert ok is True
    assert error is None
    assert "many centuries" in answer
    assert len(calls) == 1
    assert calls[0].get("use_lora_runtime") is None
    assert synthesizer.LAST_LOCAL_LLM_MODEL == "dolphin3"


def test_synthesizer_removes_internal_nova_speaker_label(monkeypatch):
    class FakeConnector:
        def generate(self, context_packet):
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Extra draft text.\n\nNova: Final clean answer.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "System rules here.",
            "user_question": "Why test robot code?",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "Final clean answer."


def test_synthesizer_uses_compact_prompt_for_college_question(monkeypatch):
    captured = {}
    monkeypatch.setenv("NOVA_DEEP_LOCAL_LLM_MODEL", "academic-deep-test-model")

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="x = 4.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "Very long system prompt " * 50,
            "user_question": "College algebra: solve 2x + 3 = 11.",
            "route": "general_conversation",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "x = 4."
    assert captured["raw_prompt"].startswith("Answer the academic question directly.")
    assert "Very long system prompt" not in captured["raw_prompt"]
    assert captured["local_llm_model"] == "academic-deep-test-model"
    assert captured["local_llm_timeout"] == nova_local_llm_connector.LocalLLMConfig().direct_deepseek_timeout


def test_synthesizer_direct_legacy_deepseek_route_uses_configured_dolphin_model(monkeypatch):
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Dolphin direct answer.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "Use the configured local model.",
            "user_question": "Explain this clearly.",
            "route": "deepseek_direct",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "Dolphin direct answer."
    assert captured["local_llm_model"] == "dolphin3"
    assert captured["local_llm_timeout"] == nova_local_llm_connector.LocalLLMConfig().direct_deepseek_timeout


def test_synthesizer_direct_deepseek_route_uses_compact_prompt(monkeypatch):
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Dolphin direct answer.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "Very long system prompt " * 50,
            "user_question": "Explain gravity in one sentence.",
            "route": "deepseek_direct",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "Dolphin direct answer."
    assert captured["raw_prompt"].startswith("Answer directly as Nova using the configured local LLM.")
    assert "Very long system prompt" not in captured["raw_prompt"]
    assert captured["ollama_options"]["num_ctx"] == 8192
    assert captured["ollama_options"]["num_predict"] == 320


def test_synthesizer_prefers_clean_answer_label_when_complete():
    cleaned = synthesizer._clean_synthesized_answer(
        "Draft line that repeats itself.\n\nAnswer:\nThe correct line is `print('hello')` because the original missed a closing parenthesis."
    )

    assert cleaned == "The correct line is `print('hello')` because the original missed a closing parenthesis."


def test_generate_uses_gpu_hub_aware_semantic_provider_selection(monkeypatch):
    from nova_model_provider import ModelGenerationResult

    gpu_state = {
        "mode": "vast_gpu",
        "effective_mode": "vast_gpu",
        "available": True,
        "verified": True,
        "verified_backend": "vast_gpu",
        "endpoint": {"url": "https://worker.example", "model": "qwen3", "provider": "vllm"},
    }
    observed = []

    class Provider:
        provider_id = "vllm"
        model_id = "qwen3"

        def generate(self, request):
            return ModelGenerationResult("Remote answer.", "vllm", request.model or "qwen3")

    monkeypatch.setattr(
        synthesizer,
        "_prepare_generation",
        lambda _packet: ("question", "prompt", {"num_predict": 32}, "local", 15),
    )
    monkeypatch.setattr(synthesizer, "_gpu_hub_runtime_state", lambda: gpu_state, raising=False)
    monkeypatch.setattr(
        synthesizer,
        "_configured_semantic_provider",
        lambda: observed.append("selected") or Provider(),
    )

    answer, ok, error = synthesizer.generate({})

    assert (answer, ok, error) == ("Remote answer.", True, None)
    assert observed == ["selected"]


def test_generate_records_vast_backend_in_semantic_provider_metadata(monkeypatch):
    from nova_model_provider import ModelGenerationResult

    gpu_state = {
        "mode": "vast_gpu",
        "effective_mode": "vast_gpu",
        "available": True,
        "verified": True,
        "verified_backend": "vast_gpu",
        "endpoint": {"url": "https://worker.example", "model": "qwen3", "provider": "vllm"},
    }

    class Provider:
        provider_id = "vllm"
        model_id = "qwen3"

        def generate(self, request):
            return ModelGenerationResult("Remote answer.", "vllm", request.model or "qwen3")

    monkeypatch.setattr(synthesizer, "_prepare_generation", lambda _packet: ("question", "prompt", {}, "local", 15))
    monkeypatch.setattr(synthesizer, "_gpu_hub_runtime_state", lambda: gpu_state, raising=False)
    monkeypatch.setattr(synthesizer, "_configured_semantic_provider", lambda: Provider())

    packet = {}
    answer, ok, error = synthesizer.generate(packet)

    assert (answer, ok, error) == ("Remote answer.", True, None)
    assert packet["_semantic_provider"]["gpu_backend"] == "vast_gpu"


def test_generate_forces_cpu_option_on_normal_local_connector(monkeypatch):
    observed = {}

    class Response:
        local_llm_used = True
        raw_output = "CPU answer."
        model = "local"
        finish_reason = "stop"

    class Connector:
        def generate(self, context):
            observed.update(context)
            return Response()

    monkeypatch.setattr(
        synthesizer,
        "_prepare_generation",
        lambda _packet: ("question", "prompt", {"num_predict": 32, "num_gpu": 99}, "local", 15),
    )
    monkeypatch.setattr(
        synthesizer,
        "_gpu_hub_runtime_state",
        lambda: {"mode": "cpu", "effective_mode": "cpu", "available": True, "verified": False},
        raising=False,
    )
    monkeypatch.setattr(synthesizer, "_configured_semantic_provider", lambda: None)
    monkeypatch.setattr("nova_local_llm_connector.LocalLLMConnector", Connector)

    answer, ok, error = synthesizer.generate({})

    assert (answer, ok, error) == ("CPU answer.", True, None)
    assert observed["ollama_options"]["num_gpu"] == 0


def test_synthesizer_keeps_first_complete_answer_when_final_label_is_truncated():
    cleaned = synthesizer._clean_synthesized_answer(
        "Newton's second law says force equals mass times acceleration. A heavier object needs more force for the same acceleration.\n\nFinal answer: Newton's second law says force equals mass"
    )

    assert cleaned == (
        "Newton's second law says force equals mass times acceleration. "
        "A heavier object needs more force for the same acceleration."
    )


def test_native_stream_hides_reasoning_and_reconstructs_exact_answer(monkeypatch):
    emitted = []

    class FakeConnector:
        def generate_stream(self, context_packet, on_delta, is_cancelled):
            chunks = ["<thi", "nk>private reasoning.</thi", "nk>Nova: First ", "sentence. ", "Second line"]
            for chunk in chunks:
                assert on_delta(chunk) is not False
            return SimpleNamespace(
                local_llm_used=True,
                provider="ollama",
                model="dolphin3",
                raw_output="<think>private reasoning.</think>Nova: First sentence. Second line",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)
    packet = {
        "system_prompt": "You are Nova.",
        "user_question": "Give two short thoughts.",
        "stream_answer_validator": lambda answer: "private reasoning" not in answer,
    }

    answer, ok, error = synthesizer.generate_stream(packet, lambda delta: emitted.append(delta) or True)

    assert ok is True
    assert error is None
    assert answer == "".join(emitted) == "First sentence. Second line"
    assert len(emitted) >= 4
    assert "think" not in answer.lower()
    assert "nova:" not in answer.lower()
    assert packet["_native_stream_incremental"] is True


def test_native_stream_critic_replaces_unsafe_segment_before_publication(monkeypatch):
    emitted = []

    class FakeConnector:
        def generate_stream(self, context_packet, on_delta, is_cancelled):
            for chunk in ["Safe first sentence. ", "debug: private internals."]:
                if on_delta(chunk) is False:
                    break
            return SimpleNamespace(
                local_llm_used=False,
                provider="ollama",
                model="dolphin3",
                raw_output="Safe first sentence. debug: private internals.",
                fallback_reason="stream stopped by safety gate",
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)
    packet = {
        "system_prompt": "You are Nova.",
        "user_question": "Respond safely.",
        "stream_answer_validator": lambda answer: "debug:" not in answer.lower(),
    }

    answer, ok, error = synthesizer.generate_stream(packet, lambda delta: emitted.append(delta) or True)

    assert ok is True
    assert error is None
    assert answer == "".join(emitted)
    assert answer.startswith("Safe first sentence.")
    assert "debug:" not in answer.lower()
    assert "stopped that draft" in answer
    assert packet["_native_stream_safety_repaired"] is True


def test_synthesizer_can_switch_to_internal_provider_without_client_bypass(monkeypatch):
    from nova_model_provider import MockModelProvider

    provider = MockModelProvider("Provider-independent answer.", "switchable-local")
    monkeypatch.setattr(synthesizer, "_configured_semantic_provider", lambda: provider)
    monkeypatch.setenv("NOVA_NATURAL_CHAT", "false")
    packet = {
        "system_prompt": "You are Nova.",
        "user_question": "Explain provider switching.",
        "reasoning_mode": "deep",
    }

    answer, ok, error = synthesizer.generate(packet)

    assert ok is True
    assert error is None
    assert answer == "Provider-independent answer."
    assert packet["_semantic_provider"]["provider_id"] == "mock"
    assert packet["_semantic_provider"]["reasoning_content_stored"] is False
    assert provider.requests[0].reasoning_enabled is True


def test_quarantined_deep_model_falls_back_to_healthy_primary(monkeypatch, tmp_path):
    import nova_model_quality

    registry = nova_model_quality.NovaModelQualityRegistry(
        tmp_path / "quality.json",
        failure_threshold=2,
        quarantine_seconds=3600,
    )
    registry.record_failure("ollama", "deep-test-model", reason="timeout")
    registry.record_failure("ollama", "deep-test-model", reason="timeout")
    monkeypatch.setattr(nova_model_quality, "_DEFAULT_REGISTRY", registry)
    monkeypatch.setenv("NOVA_ACTIVE_BRAIN", "deep-test-model")
    monkeypatch.setenv("NOVA_LOCAL_LLM_MODEL", "healthy-primary-model")
    monkeypatch.setenv("NOVA_FAST_LOCAL_LLM_MODEL", "healthy-primary-model")

    packet = {
        "system_prompt": "You are Nova.",
        "user_question": "Differentiate x cubed.",
        "route": "general_conversation",
        "reasoning_mode": "deep",
    }
    prepared = synthesizer._prepare_generation(packet)

    assert prepared is not None
    assert prepared[3] == "healthy-primary-model"
    assert packet["_model_quality_fallback"] == {
        "used": True,
        "provider": "ollama",
        "rejected_model": "deep-test-model",
        "selected_model": "healthy-primary-model",
        "reason": "selected_model_quarantined",
        "content_logged": False,
    }


def test_synthesizer_streams_through_internal_provider(monkeypatch):
    from nova_model_provider import MockModelProvider

    provider = MockModelProvider("Nova streams provider output.", "switchable-local")
    monkeypatch.setattr(synthesizer, "_configured_semantic_provider", lambda: provider)
    emitted = []
    packet = {
        "system_prompt": "You are Nova.",
        "user_question": "Stream it.",
        "reasoning_mode": "fast",
    }

    answer, ok, error = synthesizer.generate_stream(
        packet,
        lambda delta: emitted.append(delta) or True,
    )

    assert ok is True
    assert error is None
    assert answer == "".join(emitted)
    assert "Nova streams provider output." in answer
    assert packet["_semantic_provider"]["provider_id"] == "mock"
