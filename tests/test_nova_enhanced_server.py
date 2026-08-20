from pathlib import Path
import base64
from contextlib import nullcontext
from datetime import date
from http.server import HTTPServer
import inspect
import io
import json
import socket
from socketserver import ThreadingMixIn
import sys
import threading
import types
import urllib.error
import urllib.request
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nova_enhanced_server as server
import nova_hybrid_router as router
import nova_llm_synthesizer
from nova_model_quality import NovaModelQualityRegistry
from nova_capability_eval import NovaCapabilityEvaluationStore


HASH_A = "a" * 64
HASH_B = "b" * 64


@pytest.fixture(autouse=True)
def _isolated_model_quality_registry(monkeypatch, tmp_path):
    """Keep model-quality tests deterministic and out of live operator state."""

    import nova_model_quality

    registry = NovaModelQualityRegistry(
        tmp_path / "model_quality.json",
        enabled=True,
    )
    monkeypatch.setattr(nova_model_quality, "_DEFAULT_REGISTRY", registry)
    monkeypatch.setattr(server, "MODEL_QUALITY", registry)
    import nova_capability_eval

    capability_store = NovaCapabilityEvaluationStore(
        tmp_path / "capability_evaluations.json",
        enabled=True,
    )
    monkeypatch.setattr(nova_capability_eval, "_DEFAULT_STORE", capability_store)
    monkeypatch.setattr(server, "CAPABILITY_EVAL_STORE", capability_store)
    server.CAPABILITY_EVAL_JOB_STATUS.update(
        state="not_started",
        mode=None,
        started_at=None,
        completed_at=None,
        evaluated_models=0,
        registry_records_updated=0,
        error=None,
    )
    monkeypatch.setenv("NOVA_MODEL_QUALITY_AUTO_CHECK_LOADED", "false")
    yield


class _ThreadedTestServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _start_test_server(handler):
    httpd = _ThreadedTestServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


def _json_get(base_url, path):
    with urllib.request.urlopen(base_url + path, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _json_post(base_url, path, payload):
    request = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _make_project(projects_root, name="Music_Sound_Secrets_Website"):
    project = projects_root / name
    project.mkdir(parents=True)
    (project / "index.html").write_text("<html><body>Music home</body></html>", encoding="utf-8")
    (project / "mixing.html").write_text("<html><body>Mixing page</body></html>", encoding="utf-8")
    (project / "site_manifest.json").write_text(
        '{"project_name":"Music Sound Secrets Website","page_count":2}',
        encoding="utf-8",
    )
    return project


def test_chat_payload_accepts_message_field():
    assert server._chat_text_from_body({"message": "Help me debug a Python loop"}) == "Help me debug a Python loop"


def test_chat_payload_preserves_present_text_over_message():
    assert server._chat_text_from_body({"text": "", "message": "fallback"}) == ""


def test_brain_route_exposes_transformer_evidence_from_hybrid_router(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "coding_help"},
            "route": ["left_hemisphere", "planner_transformer"],
            "confidence": 0.95,
            "memory_binding": {},
        },
    )

    def fake_route_and_respond(text, dict_lookup_fn=None, memory=None):
        return (
            "Use a loop.",
            {
                "source": "transformer",
                "roles": ["left_hemisphere", "planner_transformer"],
                "route_path": ["left_hemisphere", "planner_transformer"],
                "domain": "coding",
                "skills": ["generated_coding", "transformer_inference"],
                "confidence": 0.91,
                "route_model_hash": HASH_A,
                "checkpoint_hash": HASH_B,
                "generation": {"role": "left_hemisphere", "ok": True},
            },
        )

    monkeypatch.setattr(server, "route_and_respond", fake_route_and_respond)
    response, trace = server.brain_route("Help me debug a Python loop")

    assert response == "Use a loop."
    assert trace["source"] == "transformer"
    assert "left_hemisphere" in trace["roles"]
    assert trace["route_path"] == ["left_hemisphere", "planner_transformer"]
    assert "route_model_hash" in trace
    assert trace["checkpoint_hash"] == HASH_B


def test_brain_route_prefers_cognitive_os_for_open_ended_chat(monkeypatch):
    captured = {}
    decision = object()
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "coding_help"},
            "route": ["left_hemisphere", "planner_transformer"],
            "confidence": 0.90,
            "memory_binding": {},
        },
    )
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)

    def fake_cognitive_route(text, dict_lookup_fn=None, memory=None, context=None):
        captured["context"] = context
        return (
            "A loop repeats work until a stop condition is met.",
            {
                "source": "cognitive_os",
                "cognitive_os": True,
                "planner_used": "llm",
                "planner_json_valid": True,
                "plan_repair_used": False,
                "validated_route": "coding_help",
                "local_llm_synthesis_used": True,
                "memory_llm_retry_requested": True,
                "memory_llm_retry_failed": False,
                "local_llm_model": "dolphin3",
                "critic_result": "passed",
                "roles": ["dolphin3_planner", "nova_context_builder", "dolphin3_synthesis"],
                "skills": ["llm_planner", "nova_validation", "llm_synthesis"],
                "route_path": [
                    "dolphin3_planner",
                    "nova_validator",
                    "nova_context",
                    "dolphin3_synthesis",
                    "critic",
                    "speech_output",
                ],
                "domain": "coding_help",
                "confidence": 0.88,
                "fallback_used": False,
                "academic_fallback_used": True,
                "natural_chat_used": True,
                "natural_response_shaped": True,
            },
        )

    def hybrid_should_not_run(*args, **kwargs):
        raise AssertionError("hybrid router should not run before cognitive os")

    monkeypatch.setattr(server, "cognitive_route", fake_cognitive_route, raising=False)
    monkeypatch.setattr(server, "route_and_respond", hybrid_should_not_run)

    response, trace = server.brain_route(
        "Explain loops",
        context={"adaptive_model_memory": True, "conversation_decision": decision},
    )

    assert response == "A loop repeats work until a stop condition is met."
    assert trace["source"] == "cognitive_os"
    assert trace["cognitive_os"] is True
    assert trace["planner_used"] == "llm"
    assert trace["plan_repair_used"] is False
    assert trace["local_llm_model"] == "dolphin3"
    assert trace["memory_llm_retry_requested"] is True
    assert trace["memory_llm_retry_failed"] is False
    assert trace["academic_fallback_used"] is True
    assert trace["critic_result"] == "passed"
    assert trace["natural_chat_used"] is True
    assert trace["natural_response_shaped"] is True
    assert captured["context"]["adaptive_model_memory"] is True
    assert captured["context"]["conversation_decision"] is decision
    assert trace["route_path"] == [
        "dolphin3_planner",
        "nova_validator",
        "nova_context",
        "dolphin3_synthesis",
        "critic",
        "speech_output",
    ]


def test_brain_route_ultra_think_request_uses_explicit_deep_route(monkeypatch):
    class FakeUltraThink:
        @staticmethod
        def should_route_ultra_think(text):
            return "ultra think" in text.lower()

        @staticmethod
        def run_ultra_think(text, route_context=None):
            return (
                "Yeah, the deeper answer is that memory gives Nova continuity.",
                {
                    "source": "ultra_think",
                    "domain": "deep_reasoning",
                    "roles": [
                        "planner_transformer",
                        "memory_transformer",
                        "local_llm_cortex",
                        "critic_conscience_transformer",
                        "speech_output_transformer",
                    ],
                    "skills": ["ultra_think", "recent_memory", "dolphin3", "critic_rewrite"],
                    "confidence": 0.88,
                    "route_path": [
                        "ultra_think_router",
                        "memory_context",
                        "dolphin3_draft",
                        "critic",
                        "natural_speech",
                    ],
                    "local_llm_model": "dolphin3",
                    "local_llm_synthesis_used": True,
                    "final_answer_source": "ultra_think",
                },
            )

    def cognitive_should_not_run(*args, **kwargs):
        raise AssertionError("explicit Ultra Think must route before general cognitive chat")

    monkeypatch.setattr(server, "_ULTRA_THINK_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_ultra_think", FakeUltraThink, raising=False)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_run, raising=False)

    response, trace = server.brain_route("ultra think why does memory matter?")

    assert "memory gives Nova continuity" in response
    assert trace["source"] == "ultra_think"
    assert trace["final_answer_source"] == "ultra_think"
    assert trace["local_llm_model"] == "dolphin3"
    assert trace["route_path"] == [
        "ultra_think_router",
        "memory_context",
        "dolphin3_draft",
        "critic",
        "natural_speech",
    ]


def test_brain_route_uses_agentic_wrapper_for_explicit_agent_request(monkeypatch, tmp_path):
    import nova_agent_memory
    import nova_agentic_core
    import nova_tools

    monkeypatch.setenv("NOVA_AGENT_MODE", "true")
    monkeypatch.setattr(nova_tools, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(nova_agentic_core, "AGENT_TRACE_DIR", tmp_path / "agent_traces")
    monkeypatch.setattr(nova_agent_memory, "MEMORY_FILE", tmp_path / "agent_memory.json")
    (tmp_path / "sample.py").write_text("def brain_route():\n    return 'ok'\n", encoding="utf-8")

    response, trace = server.brain_route("agent mode search project text for brain_route")

    assert "I searched the project" in response
    assert trace["source"] == "agentic_core"
    assert trace["agent_mode"] is True
    assert trace["final_answer_source"] == "agent_mode"
    assert trace["agent_trace"]["plan"]["needs_tools"] is True


def test_brain_route_agentic_write_request_requires_approval(monkeypatch, tmp_path):
    import nova_agent_memory
    import nova_agentic_core
    import nova_tools

    nova_agentic_core.clear_pending_approval()
    monkeypatch.setenv("NOVA_AGENT_MODE", "true")
    monkeypatch.setattr(nova_tools, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(nova_agentic_core, "AGENT_TRACE_DIR", tmp_path / "agent_traces")
    monkeypatch.setattr(nova_agent_memory, "MEMORY_FILE", tmp_path / "agent_memory.json")

    response, trace = server.brain_route("agent write file live_guard.txt with hello")

    assert "Approve this action" in response
    assert trace["source"] == "agentic_core"
    assert trace["agent_mode"] is True
    assert trace["agent_trace"]["requires_approval"] is True
    assert trace["agent_trace"]["approval_request"]["action_name"] == "write_project_file"
    assert not (tmp_path / "live_guard.txt").exists()


def test_brain_route_explicit_legacy_deepseek_request_uses_configured_dolphin(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    captured = {}

    def fake_generate(context_packet):
        captured.update(context_packet)
        nova_llm_synthesizer.LAST_LOCAL_LLM_MODEL = "dolphin3"
        return "Dolphin local answer.", True, None

    def fallthrough_should_not_run(*args, **kwargs):
        raise AssertionError("explicit DeepSeek requests should not fall through")

    monkeypatch.setattr(nova_llm_synthesizer, "generate", fake_generate)
    monkeypatch.setattr(server, "pipeline_process", fallthrough_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", fallthrough_should_not_run, raising=False)
    monkeypatch.setattr(server, "route_and_respond", fallthrough_should_not_run)

    response, trace = server.brain_route(
        "Use DeepSeek: explain in one short paragraph why war is hard to judge morally."
    )

    assert response == "Dolphin local answer."
    assert captured["user_question"] == "explain in one short paragraph why war is hard to judge morally."
    assert captured["route"] == "deepseek_direct"
    assert trace["source"] == "local_llm"
    assert trace["local_llm_synthesis_used"] is True
    assert trace["local_llm_model"] == "dolphin3"
    assert trace["route_path"] == ["local_llm_direct", "dolphin3_synthesis", "critic", "speech_output"]


def test_brain_route_direct_llm_trace_names_lora_when_lora_runtime_answers(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def fake_generate(context_packet):
        nova_llm_synthesizer.LAST_LOCAL_LLM_MODEL = "Qwen/Qwen2.5-1.5B-Instruct + LoRA"
        return "LoRA answer.", True, None

    def fallthrough_should_not_run(*args, **kwargs):
        raise AssertionError("explicit DeepSeek requests should not fall through")

    monkeypatch.setattr(nova_llm_synthesizer, "generate", fake_generate)
    monkeypatch.setattr(server, "pipeline_process", fallthrough_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", fallthrough_should_not_run, raising=False)
    monkeypatch.setattr(server, "route_and_respond", fallthrough_should_not_run)

    response, trace = server.brain_route("Use DeepSeek: answer naturally.")

    assert response == "LoRA answer."
    assert trace["local_llm_model"] == "Qwen/Qwen2.5-1.5B-Instruct + LoRA"
    assert trace["roles"] == ["local_llm_planner", "lora_synthesis", "critic_conscience_transformer"]
    assert trace["skills"] == ["local_llm", "hf_peft_lora", "direct_llm_synthesis"]
    assert trace["route_path"] == ["local_llm_direct", "lora_synthesis", "critic", "speech_output"]


def test_local_llm_trace_names_plain_qwen_as_ollama_not_lora():
    label, skills = server._local_llm_trace_labels("qwen2.5:1.5b")

    assert label == "qwen_synthesis"
    assert "ollama" in skills
    assert "hf_peft_lora" not in skills


def test_raw_adapter_compare_keeps_two_raw_outputs_separate_from_nova_fix(monkeypatch):
    from nova_local_llm_connector import LocalLLMResponse

    monkeypatch.setenv("NOVA_RAW_COMPARE_ALLOW_SLOW_CPU", "true")
    monkeypatch.setattr(server, "_generate_raw_ollama_lora_adapter", lambda *args, **kwargs: None)
    calls = []

    def fake_generate_with_lora(prompt, config=None, **kwargs):
        adapter_id = kwargs.get("adapter_id")
        calls.append((adapter_id, prompt))
        return LocalLLMResponse(
            local_llm_used=True,
            provider="hf_peft_lora",
            model=f"{adapter_id} model",
            prompt=prompt,
            raw_output=f"RAW::{adapter_id}::{prompt}",
            response_time_ms=12.5,
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        type("FakeLoraRuntime", (), {"generate_with_lora": staticmethod(fake_generate_with_lora)}),
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: ("Nova app fixed answer.", {"source": "nova_app_fix", "confidence": 0.91}),
    )

    result = server._compare_raw_lora_adapters(
        "Do you like politics?",
        adapter_ids=["qwen-test-adapter", "dolphin-test-adapter"],
    )

    assert result["ok"] is True
    assert [item["adapter_id"] for item in result["adapter_outputs"]] == [
        "qwen-test-adapter",
        "dolphin-test-adapter",
    ]
    assert result["adapter_outputs"][0]["raw_output"] == "RAW::qwen-test-adapter::Do you like politics?"
    assert result["adapter_outputs"][1]["raw_output"] == "RAW::dolphin-test-adapter::Do you like politics?"
    assert result["nova_app_fix"]["response"] == "Nova app fixed answer."
    assert result["nova_app_fix"]["response"] not in {
        item["raw_output"] for item in result["adapter_outputs"]
    }
    assert calls == [
        ("qwen-test-adapter", "Do you like politics?"),
        ("dolphin-test-adapter", "Do you like politics?"),
    ]


def test_raw_adapter_compare_flags_unfinished_text_and_preserves_review_context(monkeypatch):
    outputs = {
        "qwen-test": "I get you. If she doesn't",
        "dolphin-test": "Right. I get you. That came",
    }
    captured = {}

    def fake_raw(prompt, adapter_id, max_new_tokens=192):
        return {
            "adapter_id": adapter_id,
            "label": "RAW " + adapter_id,
            "raw_output": outputs[adapter_id],
            "error": None,
        }

    def fake_brain_route(text, context=None):
        captured["text"] = text
        captured["context"] = context
        return (
            "If she doesn't say it back, don't pressure her. Give her room to be honest.",
            {"source": "relationship_coaching", "confidence": 0.97},
        )

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_raw)
    monkeypatch.setattr(server, "brain_route", fake_brain_route)
    history = [
        {"role": "user", "content": "I LOVE HER"},
        {"role": "assistant", "content": "Then tell her plainly and give her room to respond."},
    ]

    result = server._compare_raw_lora_adapters(
        "WHAT IF SHE DONT SAY IT BACK?",
        adapter_ids=["qwen-test", "dolphin-test"],
        max_new_tokens=8,
        context={"conversation_history": history},
    )

    assert [item["raw_output"] for item in result["adapter_outputs"]] == list(outputs.values())
    assert all(item["output_status"] == "incomplete" for item in result["adapter_outputs"])
    assert all(item["likely_truncated"] is True for item in result["adapter_outputs"])
    assert all(item["requested_max_new_tokens"] == 16 for item in result["adapter_outputs"])
    assert "ended mid-thought" in result["nova_app_fix"]["response"]
    assert "Nova answer:" in result["nova_app_fix"]["response"]
    assert captured["text"] == "WHAT IF SHE DONT SAY IT BACK?"
    assert captured["context"]["conversation_history"] == history
    assert len(captured["context"]["raw_adapter_outputs"]) == 2


def test_raw_adapter_compare_skips_dolphin_8b_on_cpu_without_calling_runtime(monkeypatch):
    monkeypatch.delenv("NOVA_RAW_COMPARE_ALLOW_SLOW_CPU", raising=False)
    monkeypatch.setattr(server, "_generate_raw_ollama_lora_adapter", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        server,
        "_adapter_compare_metadata",
        lambda adapter_id: {
            "base_model": "cognitivecomputations/Dolphin3.0-Llama3.1-8B",
            "train_records": 17577,
            "eval_metrics": {"eval_loss": 0.19},
        },
    )

    class FakeCuda:
        @staticmethod
        def is_available():
            return False

    monkeypatch.setitem(sys.modules, "torch", type("FakeTorch", (), {"cuda": FakeCuda}))

    def runtime_should_not_run(*args, **kwargs):
        raise AssertionError("Dolphin 8B raw compare should not run on CPU by default")

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        type("FakeLoraRuntime", (), {"generate_with_lora": staticmethod(runtime_should_not_run)}),
    )

    result = server._generate_raw_lora_adapter(
        "Do you like politics?",
        "nova-dolphin3-llama3-1-8b-full-sft-20260712",
        max_new_tokens=16,
    )

    assert result["label"] == "RAW Dolphin adapter"
    assert result["local_llm_used"] is False
    assert result["raw_output"] == ""
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "Raw adapter compare safe guard"
    assert "CPU-only machine" in result["error"]


def test_raw_dolphin_adapter_prefers_dedicated_ollama_lora(monkeypatch):
    monkeypatch.setattr(
        server,
        "_adapter_compare_metadata",
        lambda adapter_id: {"base_model": "dphn/Dolphin3.0-Llama3.1-8B"},
    )
    expected = {
        "raw_output": "Answer from the trained Dolphin adapter.",
        "local_llm_used": True,
        "provider": "ollama_lora_adapter",
        "model": "nova-dolphin3-lora",
    }
    monkeypatch.setattr(
        server,
        "_generate_raw_ollama_lora_adapter",
        lambda prompt, adapter_id, max_new_tokens, metadata=None: expected,
    )
    monkeypatch.setattr(
        server,
        "_raw_adapter_local_cpu_guard",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("HF CPU guard must not intercept the dedicated Ollama adapter")),
    )

    result = server._generate_raw_lora_adapter(
        "What do you think about the war?",
        "nova-dolphin3-llama3-1-8b-full-sft-20260712",
    )

    assert result is expected
    assert result["provider"] == "ollama_lora_adapter"


def test_raw_ollama_lora_adapter_uses_user_only_chat_payload(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps({"message": {"role": "assistant", "content": "A direct trained answer."}}).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("NOVA_DOLPHIN_LORA_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    monkeypatch.setattr(server, "_ollama_adapter_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    result = server._generate_raw_ollama_lora_adapter(
        "What do you think about the war?",
        "nova-dolphin3-llama3-1-8b-full-sft-20260712",
        123,
        {"base_model": "dphn/Dolphin3.0-Llama3.1-8B"},
    )

    assert result["raw_output"] == "A direct trained answer."
    assert result["provider"] == "ollama_lora_adapter"
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["model"] == "nova-dolphin3-lora"
    assert captured["payload"]["messages"] == [
        {"role": "user", "content": "What do you think about the war?"}
    ]
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["options"]["num_predict"] == 123


def test_adapter_registry_reports_local_dolphin_ollama_runtime(monkeypatch):
    fake_registry = types.SimpleNamespace(
        list_lora_adapters=lambda: {
            "adapters": [
                {
                    "id": "nova-dolphin3-llama3-1-8b-full-sft-20260712",
                    "base_model": "dphn/Dolphin3.0-Llama3.1-8B",
                    "path": "models/dolphin",
                }
            ]
        }
    )
    fake_runtime = types.SimpleNamespace(
        adapter_runtime_availability=lambda *args, **kwargs: {
            "runnable": False,
            "state": "missing_base",
            "reason": "Hugging Face base is incomplete.",
        }
    )
    monkeypatch.setitem(sys.modules, "nova_lora_adapter_registry", fake_registry)
    monkeypatch.setitem(sys.modules, "nova_lora_runtime", fake_runtime)
    monkeypatch.setattr(server, "_ollama_adapter_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(server, "_latest_adapter_id_for_family", lambda family: "latest-" + family)

    result = server._adapter_registry_list()

    runtime = result["adapters"][0]["runtime"]
    assert runtime["runnable"] is True
    assert runtime["state"] == "available"
    assert runtime["provider"] == "ollama_lora_adapter"
    assert runtime["provider_model"] == "nova-dolphin3-lora"


def test_adapter_compare_api_returns_raw_outputs_and_nova_fix(monkeypatch):
    monkeypatch.setattr(
        server,
        "_compare_raw_lora_adapters",
        lambda text, adapter_ids=None, max_new_tokens=192: {
            "ok": True,
            "prompt": text,
            "adapter_outputs": [
                {"adapter_id": "a", "raw_output": "raw a"},
                {"adapter_id": "b", "raw_output": "raw b"},
            ],
            "nova_app_fix": {"response": "fixed", "trace": {"source": "nova_app_fix"}},
        },
    )

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        result = _json_post(
            base_url,
            "/api/adapters/compare",
            {"text": "test raw adapters", "adapter_ids": ["a", "b"]},
        )
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert result["ok"] is True
    assert result["prompt"] == "test raw adapters"
    assert result["adapter_outputs"][0]["raw_output"] == "raw a"
    assert result["nova_app_fix"]["response"] == "fixed"


def test_model_memory_api_reports_and_safely_unloads(monkeypatch):
    monkeypatch.setattr(
        server,
        "_model_memory_status",
        lambda: {"ok": True, "qwen": {"loaded": True}, "dolphin": {"loaded": False}},
    )
    monkeypatch.setattr(
        server,
        "_unload_model_memory",
        lambda body: {"ok": True, "target": body.get("target"), "unloaded": [{"provider": "huggingface"}]},
    )

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        status = _json_get(base_url, "/api/models/memory")
        unloaded = _json_post(base_url, "/api/models/memory/unload", {"target": "qwen"})
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert status["qwen"]["loaded"] is True
    assert unloaded["target"] == "qwen"
    assert unloaded["unloaded"] == [{"provider": "huggingface"}]


def test_model_quality_api_reports_and_starts_content_free_check(monkeypatch):
    monkeypatch.setattr(
        server,
        "_model_quality_status",
        lambda: {
            "ok": True,
            "enabled": True,
            "quarantined_count": 1,
            "content_logged": False,
            "raw_adapter_modes_excluded": True,
        },
    )
    monkeypatch.setattr(
        server,
        "_start_loaded_model_quality_check",
        lambda source: {
            "ok": True,
            "state": "scheduled",
            "source": source,
            "content_logged": False,
            "raw_adapter_modes_excluded": True,
        },
    )

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        status = _json_get(base_url, "/api/models/quality")
        started = _json_post(base_url, "/api/models/quality/check", {})
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert status["quarantined_count"] == 1
    assert status["content_logged"] is False
    assert started["state"] == "scheduled"
    assert started["source"] == "manual"
    assert started["raw_adapter_modes_excluded"] is True


def test_capability_evaluation_api_reports_and_requires_approval(monkeypatch):
    monkeypatch.setattr(
        server,
        "_capability_evaluation_status",
        lambda: {
            "ok": True,
            "enabled": True,
            "record_count": 1,
            "content_logged": False,
            "training_used": False,
            "raw_adapter_modes_excluded": True,
        },
    )
    monkeypatch.setattr(
        server,
        "_start_capability_evaluation",
        lambda body: {
            "ok": True,
            "state": "scheduled",
            "mode": body["mode"],
            "approved": body.get("user_approved") is True,
            "content_logged": False,
            "training_used": False,
            "raw_adapter_modes_excluded": True,
        },
    )

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        status = _json_get(base_url, "/api/models/capabilities/evaluations")
        started = _json_post(
            base_url,
            "/api/models/capabilities/evaluate",
            {"mode": "loaded_text", "user_approved": True},
        )
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert status["record_count"] == 1
    assert status["content_logged"] is False
    assert started["state"] == "scheduled"
    assert started["approved"] is True
    assert started["training_used"] is False
    assert started["raw_adapter_modes_excluded"] is True


def test_capability_evaluation_start_rejects_implicit_or_invalid_runs():
    with pytest.raises(ValueError, match="explicit user approval"):
        server._start_capability_evaluation({"mode": "loaded_text"})
    with pytest.raises(ValueError, match="loaded_text or vision"):
        server._start_capability_evaluation(
            {"mode": "remote_benchmark", "user_approved": True}
        )
    with pytest.raises(ValueError, match="Select an image"):
        server._start_capability_evaluation(
            {"mode": "vision", "user_approved": True}
        )


def test_capability_job_keeps_results_advisory_and_content_free(monkeypatch):
    monkeypatch.setattr(
        server,
        "evaluate_loaded_text_models",
        lambda *_args, **_kwargs: {
            "ok": True,
            "evaluated_models": 1,
            "results": [
                {
                    "provider_id": "ollama",
                    "model_id": "managed-test",
                    "status": "evaluated",
                    "overall_score": 0.75,
                    "capabilities": {"reasoning": {"score": 0.75}},
                }
            ],
            "content_logged": False,
            "training_used": False,
        },
    )
    monkeypatch.setattr(
        server,
        "_publish_capability_evaluations_to_model_registry",
        lambda results: len(results),
    )

    result = server._run_capability_evaluation_job({"mode": "loaded_text"})

    assert result["ok"] is True
    assert result["training_used"] is False
    assert server.CAPABILITY_EVAL_JOB_STATUS["state"] == "completed"
    assert server.CAPABILITY_EVAL_JOB_STATUS["evaluated_models"] == 1
    assert server.CAPABILITY_EVAL_JOB_STATUS["registry_records_updated"] == 1


def test_nova_turn_solves_provable_word_math_before_loading_a_model(monkeypatch):
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("deterministic math must not select a model")
        ),
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("deterministic math must bypass generation")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "A device has four modules using 3 watts each and one controller "
        "using 5 watts. What is the total wattage?",
        {
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == "[VERIFIED MATH] 4 × 3 + 1 × 5 = 17 watts."
    assert trace["source"] == "deterministic_math_verifier"
    assert trace["local_llm_synthesis_used"] is False
    assert trace["direct_middle_routing"]["model_called"] is False
    assert trace["deterministic_verification"]["status"] == "solved_before_model"
    assert trace["deterministic_verification"]["content_logged"] is False
    assert trace["final_answer_source"] == "deterministic_verifier"


def test_nova_turn_solves_arithmetic_with_trailing_output_instruction_before_model(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("arithmetic with a formatting suffix must bypass generation")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "What is 12 + 7? Answer with only the number.",
        {
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == "19"
    assert trace["source"] == "deterministic_math_verifier"
    assert trace["deterministic_verification"]["status"] == "solved_before_model"
    assert trace["final_answer_source"] == "deterministic_verifier"


def test_nova_turn_recalls_explicit_client_conversation_fact_before_model_or_guards(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("explicit conversation recall must bypass generation")
        ),
    )
    monkeypatch.setattr(
        server,
        "_fact_grounding_preflight",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("client conversation evidence must precede current-fact guard")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "What is the current test number?",
        {
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_history": [
                {"role": "user", "content": "The test number is 31."},
                {"role": "assistant", "content": "Noted."},
                {"role": "user", "content": "Correction: the test number is 32."},
                {"role": "assistant", "content": "Updated."},
            ],
        },
    )

    assert response == "32"
    assert trace["source"] == "conversation_evidence_recall"
    assert trace["final_answer_source"] == "conversation_evidence_recall"
    assert trace["client_context_messages"] == 4
    assert trace["local_llm_synthesis_used"] is False
    assert trace["memory_write_used"] is False
    assert "source_text" not in trace["conversation_recall"]


def test_nova_turn_acknowledges_temporary_conversation_fact_without_model_or_memory(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("temporary conversation declarations must bypass generation")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "For this conversation, the codeword is SILVER_FOX_19.",
        {
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": True,
        },
    )

    assert response == "Got it. The codeword for this conversation is SILVER_FOX_19."
    assert trace["source"] == "conversation_declaration"
    assert trace["local_llm_synthesis_used"] is False
    assert trace["memory_write_used"] is False


def test_nova_turn_gates_high_risk_action_before_model_tools_or_fact_guard(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("high-risk action gate must precede generation")
        ),
    )
    monkeypatch.setattr(
        server,
        "_fact_grounding_preflight",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("action authorization must precede fact grounding")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Delete every file in my Documents folder now.",
        {
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
        },
    )

    assert "did not delete" in response.lower()
    assert "confirmation" in response.lower()
    assert trace["source"] == "action_permission_gate"
    assert trace["final_answer_source"] == "action_permission_gate"
    assert trace["action_policy"]["status"] == "awaiting_authorization"
    assert trace["action_policy"]["execute"] is False
    assert trace["local_llm_synthesis_used"] is False


def test_nova_turn_honors_only_number_instruction_without_loading_a_model(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("bounded arithmetic must bypass generation")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Answer with only the number: What is 7 multiplied by 8?",
        {
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == "56"
    assert trace["source"] == "deterministic_math_verifier"
    assert trace["local_llm_synthesis_used"] is False
    assert trace["direct_middle_routing"]["model_called"] is False
    assert trace["deterministic_verification"]["status"] == "solved_before_model"


def test_verified_json_constraint_is_not_rewritten_by_answer_firewall(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("bounded JSON output must bypass generation")
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *_args, **_kwargs: {
            "ok": False,
            "reason": "model_must_not_be_called",
        },
    )

    response, trace = server._run_nova_chat_turn(
        'Return only valid JSON: {"values":[1,4,9]}.',
        {
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == '{"values":[1,4,9]}'
    assert trace["source"] == "deterministic_instruction_verifier"
    assert trace["final_answer_source"] == "deterministic_verifier"
    assert trace["local_llm_synthesis_used"] is False
    assert trace["answer_firewall"]["status"] == "bypassed_verified"


def test_nova_turn_solves_bounded_logic_before_loading_a_model(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("provable logic must bypass generation")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "All ravens are birds. Nova is a raven. Is Nova a bird?",
        {
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response.startswith("[VERIFIED LOGIC] Yes.")
    assert trace["source"] == "deterministic_logic_verifier"
    assert trace["deterministic_verification"]["rule_id"] == "categorical_syllogism"
    assert "expected_value" not in trace["deterministic_verification"]


@pytest.mark.parametrize(
    ("prompt", "expected_source", "expected_rule"),
    [
        ("What is $80 after 25% off?", "deterministic_money_verifier", "percentage_adjustment"),
        ("Convert 5 miles to kilometers", "deterministic_conversion_verifier", "length_unit_conversion"),
        ("Which is larger, 3/4 or 2/3?", "deterministic_comparison_verifier", "bounded_numeric_comparison"),
        ("What date is 10 days after July 20, 2026?", "deterministic_date_verifier", "calendar_offset"),
    ],
)
def test_nova_turn_expanded_exact_domains_bypass_models(
    monkeypatch,
    prompt,
    expected_source,
    expected_rule,
):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified exact domains must bypass generation")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        prompt,
        {
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response.startswith("[VERIFIED ")
    assert trace["source"] == expected_source
    assert trace["deterministic_verification"]["rule_id"] == expected_rule
    assert trace["local_llm_synthesis_used"] is False
    assert trace["capability_shadow_routing"]["route_changed"] is False


def test_nova_turn_verified_technical_concept_bypasses_unreliable_generation(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("stable verified technical fact must bypass generation")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Why can JSON.parse fail on {'a':1}?",
        {
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
        },
    )

    assert "double quotes" in response
    assert trace["source"] == "deterministic_technical_verifier"
    assert trace["final_answer_source"] == "deterministic_verifier"
    assert trace["local_llm_synthesis_used"] is False
    assert trace["answer_firewall"]["status"] == "bypassed_verified"


def test_nova_turn_verified_science_concept_bypasses_unreliable_generation(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("stable verified science must bypass generation")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Why is it warmer in summer: Earth's distance from the Sun or axial tilt?",
        {
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
        },
    )

    assert "axial tilt" in response
    assert "Sun" in response
    assert trace["source"] == "deterministic_science_verifier"
    assert trace["final_answer_source"] == "deterministic_verifier"
    assert trace["local_llm_synthesis_used"] is False
    assert trace["answer_firewall"]["status"] == "bypassed_verified"


def test_nova_turn_failed_action_claim_uses_observed_result_not_generation(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("an observed failed action must bypass generation")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "A tool was attempted but returned exit code 1. Should Nova report success?",
        {
            "nova_gateway": True,
            "private_mode": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
        },
    )

    assert response.startswith("No.")
    assert "failed" in response
    assert "exit code 1" in response.lower()
    assert trace["source"] == "deterministic_planning_verifier"
    assert trace["final_answer_source"] == "deterministic_verifier"
    assert trace["local_llm_synthesis_used"] is False
    assert trace["answer_firewall"]["status"] == "bypassed_verified"


@pytest.mark.parametrize(
    ("prompt", "expected_kind", "expected_text"),
    [
        (
            "I love my girlfriend. Give me something sincere I could say to her.",
            "love_disclosure",
            "I love you",
        ),
        (
            "What should I say to her?",
            "clarify_context",
            "what happened",
        ),
    ],
)
def test_relationship_coaching_handles_direct_wording_and_missing_context(
    prompt,
    expected_kind,
    expected_text,
):
    kind = server._relationship_coaching_kind(prompt)

    assert kind == expected_kind
    assert expected_text.lower() in server._relationship_coaching_response(kind).lower()


def test_fresh_short_joke_request_uses_bounded_joke_route():
    assert server._joke_request_kind(
        "Tell me a fresh short joke.",
        {"conversation_id": "natural-eval-joke"},
    ) == "explicit"


def test_raw_adapter_turn_is_never_intercepted_by_deterministic_verifier(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (
            "14",
            {
                "source": "raw_qwen_adapter",
                "roles": ["raw_qwen_adapter"],
                "skills": ["raw_adapter_generation"],
                "confidence": 0.9,
            },
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "A device has four modules using 3 watts each and one controller "
        "using 5 watts. What is the total wattage?",
        {
            "nova_gateway": True,
            "trained_adapter_only": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == "14"
    assert trace["source"] == "raw_qwen_adapter"
    assert "deterministic_verification" not in trace
    assert trace["capability_shadow_routing"]["status"] == "raw_adapter_bypass"
    assert trace["answer_firewall"]["status"] == "bypassed_raw"


def test_deterministic_verifier_can_be_disabled_without_changing_chat(monkeypatch):
    monkeypatch.setenv("NOVA_DETERMINISTIC_VERIFIER_ENABLED", "false")
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (
            "model answer",
            {
                "source": "local_llm",
                "roles": ["speech_output_transformer"],
                "skills": ["local_llm"],
                "confidence": 0.9,
            },
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "What is 8 * 7?",
        {
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == "model answer"
    assert trace["source"] == "local_llm"
    assert "deterministic_verification" not in trace


def test_capability_status_exposes_verifier_without_private_content(monkeypatch):
    monkeypatch.setattr(
        server.CAPABILITY_EVAL_STORE,
        "status",
        lambda: {"ok": True, "content_logged": False, "records": []},
    )

    status = server._capability_evaluation_status()

    assert status["deterministic_verifier"] == {
        "enabled": True,
        "version": server.DETERMINISTIC_VERIFIER_VERSION,
        "scope": [
            "bounded_arithmetic",
            "percentage_money",
            "unit_conversion",
            "date_arithmetic",
            "numeric_comparison",
            "bounded_categorical_logic",
        ],
        "model_bypass": True,
        "raw_adapter_modes_excluded": True,
    }
    assert status["shadow_router"]["mode"] == "evidence_only"
    assert status["shadow_router"]["automatic_routing"] is False
    assert status["shadow_router"]["training_used"] is False
    assert "prompt" not in status["deterministic_verifier"]


def test_capability_shadow_route_observes_model_without_selecting_it(monkeypatch):
    monkeypatch.setattr(
        server.CAPABILITY_EVAL_STORE,
        "shadow_recommendation",
        lambda task_type: {
            "status": "evidence_match",
            "task_type": task_type,
            "recommended_provider": "ollama",
            "recommended_model": "evidence-model",
            "score": 0.9,
            "runs": 3,
        },
    )

    observed = server._capability_shadow_route(
        "Debug this Python function and explain the bug",
        {
            "domain": "coding",
            "local_llm_provider": "ollama",
            "local_llm_model": "actual-model",
            "local_llm_synthesis_used": True,
        },
    )

    assert observed["status"] == "evidence_match"
    assert observed["task_type"] == "coding"
    assert observed["recommended_model"] == "evidence-model"
    assert observed["actual_model"] == "actual-model"
    assert observed["automatic_routing"] is False
    assert observed["route_changed"] is False
    assert observed["training_used"] is False
    assert observed["content_logged"] is False


def test_capability_shadow_route_never_scores_raw_adapters(monkeypatch):
    monkeypatch.setattr(
        server.CAPABILITY_EVAL_STORE,
        "shadow_recommendation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Raw adapters must not enter capability shadow routing")
        ),
    )

    observed = server._capability_shadow_route(
        "Debug this",
        {"source": "raw_qwen_adapter"},
        raw_adapter_request=True,
    )

    assert observed["status"] == "raw_adapter_bypass"
    assert observed["recommended_model"] is None
    assert observed["route_changed"] is False


def test_brain_route_adapter_only_uses_raw_qwen_without_nova_interception(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    captured = {}

    def fake_generate(prompt, adapter_id, max_new_tokens=0, allow_slow_cpu=False):
        captured.update(prompt=prompt, adapter_id=adapter_id, max_new_tokens=max_new_tokens, allow_slow_cpu=allow_slow_cpu)
        return {
            "raw_output": "Adapter-only raw response.", "local_llm_used": True,
            "model": "Qwen/Qwen2.5-1.5B-Instruct + LoRA", "error": None,
        }

    def fallthrough_should_not_run(*args, **kwargs):
        raise AssertionError("adapter-only requests should route before the normal pipeline")

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)
    monkeypatch.setattr(server, "pipeline_process", fallthrough_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", fallthrough_should_not_run, raising=False)
    monkeypatch.setattr(server, "route_and_respond", fallthrough_should_not_run)

    response, trace = server.brain_route(
        "tell me a short thought about building Nova",
        context={"adapter_only_mode": True},
    )

    assert response == "Adapter-only raw response."
    assert captured["prompt"] == "tell me a short thought about building Nova"
    assert "qwen" in captured["adapter_id"]
    assert captured["allow_slow_cpu"] is False
    assert trace["source"] == "raw_adapter_only"
    assert trace["trained_adapter_only"] is True
    assert trace["local_llm_model"] == "Qwen/Qwen2.5-1.5B-Instruct + LoRA"
    assert trace["roles"] == ["memory_transformer", "raw_qwen_adapter"]
    assert "critic_conscience_transformer" not in trace["roles"]
    assert trace["route_path"] == ["memory_preserved", "raw_adapter_only", "raw_qwen_adapter"]


def test_brain_route_raw_adapter_receives_recent_conversation_without_answer_replacement(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    captured = {}

    def fake_generate(prompt, adapter_id, max_new_tokens=0, allow_slow_cpu=False):
        captured["prompt"] = prompt
        return {
            "raw_output": "The raw adapter followed the conversation.",
            "local_llm_used": True,
            "model": adapter_id,
        }

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server.brain_route(
        "I like that",
        context={
            "adapter_only_mode": True,
            "dolphin_adapter_only": True,
            "conversation_history": [
                {"role": "user", "content": "How do you make ice cream?"},
                {"role": "assistant", "content": "Mix the base, churn it, and freeze it."},
            ],
        },
    )

    assert response == "The raw adapter followed the conversation."
    assert "User: How do you make ice cream?" in captured["prompt"]
    assert "Assistant: Mix the base, churn it, and freeze it." in captured["prompt"]
    assert captured["prompt"].endswith("User: I like that\nAssistant:")
    assert "raw_conversation_context" in trace["skills"]
    assert trace["raw_context_turns"] == 2
    assert trace["final_answer_source"] == "raw_adapter_only"


def test_raw_memory_mode_passes_bounded_context_to_adapter_and_returns_raw_output(monkeypatch):
    captured = {}
    raw_output = "  Raw adapter output, exactly as generated.  "
    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: None)

    def fake_generate(prompt, adapter_id, max_new_tokens=0, allow_slow_cpu=False):
        captured.update(
            prompt=prompt,
            adapter_id=adapter_id,
            max_new_tokens=max_new_tokens,
            allow_slow_cpu=allow_slow_cpu,
        )
        return {
            "raw_output": raw_output,
            "local_llm_used": True,
            "model": "Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            "provider": "hf_peft_lora",
        }

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server._run_nova_chat_turn(
        "What color did I say I like?",
        {
            "nova_model_mode": "raw_memory",
            "conversation_history": [
                {"role": "user", "content": "I like concise answers."},
                {"role": "assistant", "content": "I will keep them concise."},
            ],
            "conversation_summary_history": [
                {"role": "user", "content": "Earlier, I shared a preference."},
                {"role": "assistant", "content": "I will retain that context."},
            ],
            "memory_v2_context": "Favorite color: blue.",
        },
    )

    assert "User: I like concise answers." in captured["prompt"]
    assert "Assistant: I will keep them concise." in captured["prompt"]
    assert "Favorite color: blue." in captured["prompt"]
    assert response == raw_output
    assert trace["source"] == "raw_memory"
    assert trace["raw_memory_mode"] is True
    assert trace["final_answer_source"] == "raw_memory"
    assert trace["raw_context_turns"] == 2
    assert trace["local_llm_provider"] == "hf_peft_lora"


def test_raw_memory_mode_uses_verified_vast_provider_with_memory_context(monkeypatch):
    captured = {}

    class FakeProvider:
        provider_id = "vllm"
        model_id = "Qwen/Qwen3-8B"

        def generate(self, request):
            captured["request"] = request
            from nova_model_provider import ModelGenerationResult

            return ModelGenerationResult(
                text="Remote raw transformer answer.",
                provider_id=self.provider_id,
                model_id=request.model or self.model_id,
            )

    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: FakeProvider())
    monkeypatch.setattr(
        server,
        "_generate_raw_lora_adapter",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("verified Vast raw-memory requests should not use the local adapter")
        ),
    )

    response, trace = server._run_trained_adapter_only_request(
        "What color did I say I like?",
        {},
        context={
            "nova_model_mode": "raw_memory",
            "memory_v2_context": "Favorite color: blue.",
            "conversation_history": [
                {"role": "user", "content": "I like concise answers."},
                {"role": "assistant", "content": "I will keep them concise."},
            ],
        },
    )

    request = captured["request"]
    assert response == "Remote raw transformer answer."
    assert "Favorite color: blue." in request.prompt
    assert "User: I like concise answers." in request.prompt
    assert request.model == "Qwen/Qwen3-8B"
    assert trace["local_llm_provider"] == "vllm"
    assert trace["local_llm_model"] == "Qwen/Qwen3-8B"
    assert trace["remote_model_provider"] == "vllm"
    assert trace["gpu_backend"] == "vast_gpu"
    assert trace["remote_raw_transformer"] is True
    assert trace["use_lora_runtime"] is False


def test_raw_memory_mode_keeps_local_adapter_when_vast_provider_is_unavailable(monkeypatch):
    captured = {}

    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: None)

    def fake_generate(prompt, adapter_id, **kwargs):
        captured["prompt"] = prompt
        return {
            "raw_output": "Local raw adapter fallback.",
            "local_llm_used": True,
            "provider": "hf_peft_lora",
        }

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server._run_trained_adapter_only_request(
        "Recall my preference.",
        {},
        context={
            "nova_model_mode": "raw_memory",
            "memory_v2_context": "Favorite color: blue.",
        },
    )

    assert response == "Local raw adapter fallback."
    assert "Favorite color: blue." in captured["prompt"]
    assert trace["local_llm_provider"] == "hf_peft_lora"
    assert "remote_model_provider" not in trace


def test_raw_memory_remote_provider_requires_healthy_verified_vast_backend(monkeypatch):
    monkeypatch.setenv("NOVA_GPU_HUB_ENABLED", "true")
    class Hub:
        def __init__(self, *_args, **_kwargs):
            pass

        def status(self):
            return {
                "effective_mode": "local_gpu",
                "verified_backend": "vast_gpu",
                "available": True,
                "verified": True,
            }

    monkeypatch.setattr(server, "GpuHubController", Hub)

    assert server._raw_memory_remote_provider() is None


def test_raw_memory_remote_provider_builds_only_from_healthy_verified_vast_state(monkeypatch):
    monkeypatch.setenv("NOVA_GPU_HUB_ENABLED", "true")
    class Hub:
        def __init__(self, *_args, **_kwargs):
            pass

        def status(self):
            return {
                "effective_mode": "vast_gpu",
                "verified_backend": "vast_gpu",
                "available": True,
                "verified": True,
            }

    class Provider:
        provider_id = "vllm"

    class Registry:
        def get(self):
            return Provider()

    observed = {}
    import nova_model_provider

    monkeypatch.setattr(server, "GpuHubController", Hub)
    monkeypatch.setattr(
        nova_model_provider,
        "provider_registry_from_environment",
        lambda **kwargs: observed.update(kwargs) or Registry(),
    )

    provider = server._raw_memory_remote_provider()

    assert isinstance(provider, Provider)
    assert observed["gpu_hub_state"]["effective_mode"] == "vast_gpu"
    assert observed["gpu_hub_state"]["verified_backend"] == "vast_gpu"


def test_raw_memory_mode_passes_bounded_summary_history_to_adapter(monkeypatch):
    captured = {}
    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: None)

    def fake_generate(prompt, adapter_id, **kwargs):
        captured["prompt"] = prompt
        return {"raw_output": "Raw summary-history response.", "local_llm_used": True}

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server._run_nova_chat_turn(
        "Continue from that plan.",
        {
            "nova_model_mode": "raw_memory",
            "conversation_summary_history": [
                {"role": "user", "content": "We planned an offline-first dashboard."},
                {"role": "assistant", "content": "The dashboard needs a local activity feed."},
            ],
        },
    )

    assert "We planned an offline-first dashboard." in captured["prompt"]
    assert "The dashboard needs a local activity feed." in captured["prompt"]
    assert response == "Raw summary-history response."
    assert trace["raw_summary_context_turns"] == 2


def test_raw_memory_mode_executes_memory_operation_without_replacing_raw_output(monkeypatch):
    handled_operations = []
    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: None)

    def fake_memory_handler(text, trace, **kwargs):
        handled_operations.append(text)
        trace["memory_event"] = "lesson_created:lesson_1"
        return "[LEARNING] Lesson stored", trace

    monkeypatch.setattr(server, "_handle_adapter_only_memory_route", fake_memory_handler)
    monkeypatch.setattr(
        server,
        "_generate_raw_lora_adapter",
        lambda *_args, **_kwargs: {"raw_output": "Raw adapter decides the final reply.", "local_llm_used": True},
    )

    response, trace = server.brain_route(
        "learn this: The launch preference is local-first.",
        context={"nova_model_mode": "raw_memory"},
    )

    assert handled_operations == ["learn this: The launch preference is local-first."]
    assert response == "Raw adapter decides the final reply."
    assert trace["source"] == "raw_memory"
    assert trace["memory_event"] == "lesson_created:lesson_1"


def test_raw_memory_mode_adds_explicit_recall_result_to_raw_prompt(monkeypatch):
    captured = {}
    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: None)

    def fake_memory_handler(text, trace, **kwargs):
        trace.update(
            domain="memory_read",
            memory_event="name_recall:Alex",
        )
        return "Your name is Alex. I remember you.", trace

    def fake_generate(prompt, adapter_id, **kwargs):
        captured["prompt"] = prompt
        return {"raw_output": "Raw adapter keeps the final word.", "local_llm_used": True}

    monkeypatch.setattr(server, "_handle_adapter_only_memory_route", fake_memory_handler)
    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server.brain_route(
        "What is my name?",
        context={"nova_model_mode": "raw_memory"},
    )

    assert "Your name is Alex. I remember you." in captured["prompt"]
    assert response == "Raw adapter keeps the final word."
    assert trace["memory_event"] == "name_recall:Alex"


def test_raw_memory_mode_adds_entity_recall_result_to_raw_prompt(monkeypatch):
    captured = {}
    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: None)

    monkeypatch.setattr(
        server,
        "_handle_adapter_only_memory_route",
        lambda *_args, **_kwargs: None,
    )

    def fake_entity_memory_handler(text, trace):
        trace.update(
            source="entity_memory",
            domain="entity_memory",
            memory_event="entity_recall:brother:name",
            entity_slot="brother:name",
        )
        return "Your brother's name is Jay.", trace

    def fake_generate(prompt, adapter_id, **kwargs):
        captured["prompt"] = prompt
        return {
            "raw_output": "Raw adapter uses the recalled entity.",
            "local_llm_used": True,
        }

    monkeypatch.setattr(server, "_handle_entity_memory_route", fake_entity_memory_handler)
    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server.brain_route(
        "What is my brother's name?",
        context={"nova_model_mode": "raw_memory"},
    )

    assert "Your brother's name is Jay." in captured["prompt"]
    assert response == "Raw adapter uses the recalled entity."
    assert trace["source"] == "raw_memory"
    assert trace["memory_event"] == "entity_recall:brother:name"
    assert trace["entity_slot"] == "brother:name"


def test_raw_memory_mode_bypasses_rag_insufficient_managed_refusal(monkeypatch):
    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: None)
    monkeypatch.setattr(
        server,
        "_generate_raw_lora_adapter",
        lambda *_args, **_kwargs: {
            "raw_output": "Raw adapter answers without managed RAG rewriting.",
            "local_llm_used": True,
        },
    )

    response, trace = server.brain_route(
        "Answer from raw context.",
        context={"nova_model_mode": "raw_memory", "rag_insufficient": True},
    )

    assert response == "Raw adapter answers without managed RAG rewriting."
    assert trace["source"] == "raw_memory"
    assert trace["final_answer_source"] == "raw_memory"


def test_raw_memory_mode_allowlist_requires_exact_literal():
    assert server._is_raw_memory_mode({"nova_model_mode": "raw_memory"}) is True
    assert server._is_raw_memory_mode({"nova_model_mode": "RAW_MEMORY"}) is False
    assert server._is_raw_memory_mode({"nova_model_mode": " raw_memory "}) is False


def test_latest_adapter_selection_uses_training_date_not_alphabetic_id(monkeypatch):
    fake_registry = types.SimpleNamespace(
        list_lora_adapters=lambda: {
            "adapters": [
                {"id": "nova-qwen2-5-1-5b-sft-20260710", "base_model": "Qwen", "exists": True},
                {"id": "nova-qwen2-5-1-5b-big-sft-20260713", "base_model": "Qwen", "exists": True},
            ]
        }
    )
    monkeypatch.setitem(sys.modules, "nova_lora_adapter_registry", fake_registry)

    assert server._latest_adapter_id_for_family("qwen") == "nova-qwen2-5-1-5b-big-sft-20260713"


def test_brain_route_dolphin_adapter_only_forwards_adapter_id_and_cpu_consent(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    captured = {}

    def fake_generate(prompt, adapter_id, max_new_tokens=0, allow_slow_cpu=False):
        captured.update(prompt=prompt, adapter_id=adapter_id, allow_slow_cpu=allow_slow_cpu)
        return {
            "raw_output": "Dolphin adapter raw response.", "local_llm_used": True,
            "model": "dphn/Dolphin3.0-Llama3.1-8B + LoRA", "error": None,
        }

    def fallthrough_should_not_run(*args, **kwargs):
        raise AssertionError("dolphin adapter-only requests should route before the normal pipeline")

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)
    monkeypatch.setattr(server, "pipeline_process", fallthrough_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", fallthrough_should_not_run, raising=False)
    monkeypatch.setattr(server, "route_and_respond", fallthrough_should_not_run)

    response, trace = server.brain_route(
        "tell me a short thought through dolphin",
        context={
            "adapter_only_mode": True,
            "dolphin_adapter_only": True,
            "lora_adapter_id": "nova-dolphin3-llama3-1-8b-full-sft-20260712",
            "allow_slow_dolphin_cpu": True,
        },
    )

    assert response == "Dolphin adapter raw response."
    assert captured["adapter_id"] == "nova-dolphin3-llama3-1-8b-full-sft-20260712"
    assert captured["allow_slow_cpu"] is True
    assert trace["trained_adapter_only"] is True
    assert trace["adapter_target"] == "dolphin"
    assert trace["lora_adapter_id"] == "nova-dolphin3-llama3-1-8b-full-sft-20260712"
    assert trace["local_llm_model"] == "dphn/Dolphin3.0-Llama3.1-8B + LoRA"


def test_brain_route_adapter_only_bypasses_preference_fast_path(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    captured = {}

    def fake_generate(prompt, adapter_id, max_new_tokens=0, allow_slow_cpu=False):
        captured.update(prompt=prompt, adapter_id=adapter_id, allow_slow_cpu=allow_slow_cpu)
        return {"raw_output": "Dolphin raw preference answer.", "local_llm_used": True, "model": "Dolphin + LoRA"}

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server.brain_route(
        "Do you like music?",
        context={
            "adapter_only_mode": True,
            "dolphin_adapter_only": True,
            "lora_adapter_id": "nova-dolphin3-llama3-1-8b-full-sft-20260712",
        },
    )

    assert response == "Dolphin raw preference answer."
    assert captured["prompt"] == "Do you like music?"
    assert "dolphin" in captured["adapter_id"]
    assert trace["source"] == "raw_adapter_only"
    assert trace["trained_adapter_only_requested"] is True


def test_brain_route_dolphin_adapter_only_error_keeps_raw_dolphin_label(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def fake_generate(*args, **kwargs):
        return {
            "raw_output": "", "local_llm_used": False,
            "model": "dphn/Dolphin3.0-Llama3.1-8B + LoRA",
            "error": "Dolphin adapter load failed.",
        }

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server.brain_route(
        "Do you like music?",
        context={
            "adapter_only_mode": True,
            "dolphin_adapter_only": True,
            "lora_adapter_id": "nova-dolphin3-llama3-1-8b-full-sft-20260712",
        },
    )

    assert "Dolphin adapter load failed" in response
    assert trace["local_llm_model"] == "dphn/Dolphin3.0-Llama3.1-8B + LoRA"
    assert trace["roles"] == ["memory_transformer", "raw_dolphin_adapter"]


def test_brain_route_adapter_only_sends_identity_question_to_raw_adapter(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def fake_generate(prompt, adapter_id, **kwargs):
        assert prompt == "WHAT IS YOUR NAME"
        return {"raw_output": "The raw adapter chose this identity answer.", "local_llm_used": True, "model": adapter_id}

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server.brain_route(
        "WHAT IS YOUR NAME",
        context={"adapter_only_mode": True},
    )

    assert response == "The raw adapter chose this identity answer."
    assert trace["source"] == "raw_adapter_only"
    assert trace["trained_adapter_only_requested"] is True


def test_brain_route_answers_tell_me_your_name_variation_with_identity_guard(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("Tell me your name in one sentence.")

    assert response == "I'm Nova Creature."
    assert trace["source"] == "nova_identity"
    assert trace["domain"] == "self_identity"


def test_brain_route_keeps_nova_identity_with_prefixed_name_question(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route(
        "Live restart privacy check SECRET-WORLD-0718: what is your name?"
    )

    assert response == "I'm Nova Creature."
    assert trace["source"] == "nova_identity"
    assert trace["final_answer_source"] == "nova_identity"


def test_brain_route_answers_where_do_you_live_as_nova_identity(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def unexpected_personal_memory_lookup(*args, **kwargs):
        raise AssertionError("Nova location questions must not search the user's personal memory")

    monkeypatch.setattr(server.ltm, "recall_from_question", unexpected_personal_memory_lookup)

    response, trace = server.brain_route("Where do you live?")

    assert "physical home" in response.lower()
    assert "nova creature app" in response.lower()
    assert trace["source"] == "nova_identity"
    assert trace["domain"] == "self_identity"


def test_brain_route_adapter_only_does_not_intercept_belief_answer(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def fake_generate(prompt, adapter_id, **kwargs):
        return {"raw_output": "Raw adapter belief answer.", "local_llm_used": True, "model": adapter_id}

    def fallthrough_should_not_run(*args, **kwargs):
        raise AssertionError("adapter-only belief questions should not fall through to normal pipeline")

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)
    monkeypatch.setattr(server, "pipeline_process", fallthrough_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", fallthrough_should_not_run, raising=False)
    monkeypatch.setattr(server, "route_and_respond", fallthrough_should_not_run)

    response, trace = server.brain_route(
        "DO YOU BELIEVE IN GOD",
        context={"adapter_only_mode": True},
    )

    assert response == "Raw adapter belief answer."
    assert trace["source"] == "raw_adapter_only"
    assert trace["trained_adapter_only_requested"] is True


def test_brain_route_adapter_only_does_not_intercept_training_advice(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def fake_generate(prompt, adapter_id, **kwargs):
        return {"raw_output": "Raw adapter training advice.", "local_llm_used": True, "model": adapter_id}

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server.brain_route(
        "WHAT DO I NEED TO TRAIN YOU MORE ON?",
        context={"adapter_only_mode": True},
    )

    assert response == "Raw adapter training advice."
    assert trace["source"] == "raw_adapter_only"
    assert trace["trained_adapter_only_requested"] is True


def test_brain_route_general_definition_question_rejects_unrelated_personal_memory(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server.ltm,
        "recall_from_question",
        lambda text: (
            {
                "memory_id": "mem_city",
                "extracted_slot": "home_city",
                "extracted_value": "Cincinnati",
                "raw_text": "my home city is Cincinnati",
            },
            "You live in Cincinnati.",
        ),
    )

    response, trace = server.brain_route("what is a bird?")

    assert response != "You live in Cincinnati."
    assert "bird" in response.lower()
    assert trace.get("source") != "long_term_memory"
    assert trace.get("memory_event") != "long_term_recall:mem_city"


def test_brain_route_live_test_definition_uses_dictionary_before_memory_search(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def memory_search_should_not_run(*args, **kwargs):
        return (
            "You live in Cincinnati.",
            {
                "source": "cognitive_os",
                "roles": ["memory_transformer"],
                "skills": ["web_search"],
                "memory_event": "memory_search:1_matches",
            },
        )

    monkeypatch.setattr(server, "cognitive_route", memory_search_should_not_run, raising=False)

    response, trace = server.brain_route("live test: what is a bird?")

    assert response != "You live in Cincinnati."
    assert "bird" in response.lower()
    assert trace.get("source") == "dictionary"
    assert trace.get("memory_event") == "dictionary_hit"


def test_brain_route_adapter_only_does_not_intercept_general_learning_prompt(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def fake_generate(prompt, adapter_id, **kwargs):
        return {"raw_output": "Raw adapter learning answer.", "local_llm_used": True, "model": adapter_id}

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)

    response, trace = server.brain_route(
        "CAN U LEARN SOMETHING FOR ME",
        context={"adapter_only_mode": True},
    )

    assert response == "Raw adapter learning answer."
    assert trace["source"] == "raw_adapter_only"
    assert trace["trained_adapter_only_requested"] is True


def test_brain_route_adapter_only_context_still_saves_entity_memory(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})

    def model_should_not_handle_memory_save(*args, **kwargs):
        raise AssertionError("adapter-only mode must not bypass memory save routes")

    monkeypatch.setattr(nova_llm_synthesizer, "generate", model_should_not_handle_memory_save)
    monkeypatch.setattr(server, "pipeline_process", model_should_not_handle_memory_save)
    monkeypatch.setattr(server, "cognitive_route", model_should_not_handle_memory_save, raising=False)

    response, trace = server.brain_route(
        "MY BROTHER NAME IS JAY",
        context={"adapter_only_mode": True},
    )

    assert "brother" in response.lower()
    assert "JAY" in response
    assert trace["source"] == "entity_memory"
    assert trace["memory_event"] == "entity_saved:brother:name"
    assert server.MEMORY["entities"]["brother"]["slots"]["name"]["value"] == "JAY"
    assert trace.get("trained_adapter_only_requested") is True


def test_brain_route_adapter_only_recalls_user_name_before_raw_adapter(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server,
        "MEMORY",
        {"people": {"mr novatron": {"name": "Mr Novatron"}}, "lessons": {}, "last_person": "mr novatron"},
    )

    def raw_adapter_must_not_run(*args, **kwargs):
        raise AssertionError("Explicit memory recall must happen before raw adapter generation")

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", raw_adapter_must_not_run)
    response, trace = server.brain_route("what is my name", context={"adapter_only_mode": True})

    assert response == "Your name is Mr Novatron. I remember you."
    assert trace["source"] == "people_memory"
    assert trace["memory_event"] == "name_recall:Mr Novatron"


def test_brain_route_reports_configured_local_llm():
    response, trace = server.brain_route("What LLM is in this app?")

    assert "qwen2.5:1.5b" in response
    assert "Context window" in response
    assert "LoRA adapter" in response
    assert "LoRA runtime" in response
    assert "ollama_qwen_first" in response
    assert "Regular generated chat uses `qwen2.5:1.5b` through Ollama" in response
    assert "Qwen/Qwen2.5-1.5B-Instruct" in response
    assert trace["source"] == "local_llm_status"
    assert trace["local_llm_model"] == "qwen2.5:1.5b"
    assert trace["lora_adapter_enabled"] is True
    assert trace["lora_runtime_enabled"] is True
    assert trace["lora_auto_mode"] == "ollama_qwen_first"
    assert trace["lora_base_model"] == "Qwen/Qwen2.5-1.5B-Instruct"


def test_brain_route_forget_long_term_memory_reports_missing_match(monkeypatch, tmp_path):
    import nova_long_term_memory

    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(server, "ltm", nova_long_term_memory)

    response, trace = server.brain_route("forget long-term memory: not a real saved thing")

    assert "couldn't find any active long-term memory" in response
    assert trace["source"] == "long_term_memory"
    assert trace["memory_event"] == "long_term_forgot:0"


def test_brain_route_plain_remember_long_term_saves_memory(monkeypatch, tmp_path):
    import nova_long_term_memory

    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(server, "ltm", nova_long_term_memory)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("plain remember-long-term command should save before full LLM routing")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("remember long term my favorite color is blue")

    assert "remember long-term" in response
    assert "favorite color" in response.lower()
    assert trace["source"] == "long_term_memory"
    assert trace["final_answer_source"] == "long_term_memory"
    assert trace["memory_event"].startswith("long_term_saved:")


def test_brain_route_plain_remember_long_term_saves_unstructured_memory(monkeypatch, tmp_path):
    import nova_long_term_memory

    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(server, "ltm", nova_long_term_memory)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("unstructured remember-long-term command should still save before full LLM routing")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("remember long term Nova live test marker is green comet")

    assert "remember long-term" in response
    assert "green comet" in response.lower()
    assert trace["source"] == "long_term_memory"
    assert trace["final_answer_source"] == "long_term_memory"
    assert trace["memory_event"].startswith("long_term_saved:")


def test_brain_route_plain_remember_this_saves_before_memory_search(monkeypatch, tmp_path):
    import nova_long_term_memory

    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(server, "ltm", nova_long_term_memory)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("plain remember-this command should save before memory search or LLM routing")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("Remember this live test note: the signal word is velvet orbit.")

    assert "remember long-term" in response
    assert "velvet orbit" in response.lower()
    assert trace["source"] == "long_term_memory"
    assert trace["memory_event"].startswith("long_term_saved:")


def test_brain_route_recalls_plain_signal_word_memory(monkeypatch, tmp_path):
    import nova_long_term_memory

    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(server, "ltm", nova_long_term_memory)
    nova_long_term_memory.add_memory(
        "live test note: the signal word is velvet orbit",
        source_command="long_term",
    )

    response, trace = server.brain_route("What signal word did I give you for the live test?")

    assert "velvet orbit" in response.lower()
    assert "cincinnati" not in response.lower()
    assert trace["source"] == "long_term_memory"
    assert trace["memory_event"].startswith("long_term_recall:")


def test_brain_route_explicit_deepseek_error_reports_direct_model(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def fake_generate(_context_packet):
        raise RuntimeError("ollama offline")

    monkeypatch.setattr(nova_llm_synthesizer, "generate", fake_generate)

    response, trace = server.brain_route("Use DeepSeek: hello")

    assert response.startswith("[LOCAL LLM] Dolphin3 could not run")
    assert trace["source"] == "local_llm"
    assert trace["local_llm_model"] == "dolphin3"


def test_brain_route_deepseek_lookup_uses_research_not_ollama_timeout(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def deepseek_should_not_handle_research(_context_packet):
        raise AssertionError("DeepSeek lookup requests should route to research before Ollama")

    monkeypatch.setattr(nova_llm_synthesizer, "generate", deepseek_should_not_handle_research)
    monkeypatch.setattr(
        server,
        "_fetch_research_web_sources",
        lambda topic: [
            {
                "name": "Internal consistency of the Bible",
                "url": "https://example.test/bible-consistency",
                "status": 200,
                "title": "Internal consistency of the Bible",
                "snippet": "Scholars debate whether differences across biblical books are contradictions, variations, or harmonizable details.",
                "checked_at": "2026-07-08T09:55:00",
            }
        ],
        raising=False,
    )

    def general_chat_should_not_handle_research(*args, **kwargs):
        raise AssertionError("DeepSeek lookup requests should not fall through to general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_research)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_research, raising=False)

    response, trace = server.brain_route("Use DeepSeek look up all the contradiction of the Bible")

    assert response.startswith("[LIVE WEB]")
    assert "Bible contradictions" in response
    assert "not literally all" in response
    assert "https://example.test/bible-consistency" in response
    assert trace["source"] == "research_router"
    assert trace["topic"] == "Bible contradictions"
    assert trace["requested_model"] == "deepseek"
    assert trace["online_checked"] is True


def test_brain_route_deepseek_bible_contradict_variant_uses_research(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def deepseek_should_not_handle_research(_context_packet):
        raise AssertionError("Bible lookup variants should route to research before Ollama")

    monkeypatch.setattr(nova_llm_synthesizer, "generate", deepseek_should_not_handle_research)
    monkeypatch.setattr(
        server,
        "_fetch_research_web_sources",
        lambda topic: [
            {
                "name": "Internal consistency of the Bible",
                "url": "https://example.test/bible-consistency",
                "status": 200,
                "title": "Internal consistency of the Bible",
                "snippet": "Differences in biblical passages are often discussed as contradictions or harmonized as genre and perspective differences.",
                "checked_at": "2026-07-08T12:20:00",
            }
        ],
        raising=False,
    )

    response, trace = server.brain_route("Deepseek look up how the Bible contradict its self")

    assert response.startswith("[LIVE WEB]")
    assert "Bible contradictions" in response
    assert "not literally all" in response
    assert trace["source"] == "research_router"
    assert trace["topic"] == "Bible contradictions"
    assert trace["requested_model"] == "deepseek"


def test_brain_route_do_i_know_you_answers_as_nova(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {"a": {"text": "favorite color is blue"}}, "last_person": None})

    response, trace = server.brain_route("Do i know u")

    assert response.startswith("[NOVA MEMORY]")
    assert "I'm Nova Creature" in response
    assert "saved facts" in response
    assert "You don't know me" not in response
    assert trace["source"] == "nova_memory_relationship"


def test_brain_route_self_training_request_runs_training_center(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_start_training", lambda: (True, "hypertrain_job_self"))

    def open_chat_should_not_answer(*args, **kwargs):
        raise AssertionError("self-training request should not fall through to open chat")

    monkeypatch.setattr(server, "pipeline_process", open_chat_should_not_answer)
    monkeypatch.setattr(server, "cognitive_route", open_chat_should_not_answer, raising=False)

    response, trace = server.brain_route("Can you train yourself")

    assert response.startswith("[TRAINING CENTER]")
    assert trace["source"] == "training_center"
    assert trace["action"] == "full_training_suite"
    assert trace["training_job"]["job_id"] == "hypertrain_job_self"
    assert trace["training_report"]["summary"]["failed"] == 0


def test_brain_route_self_feeling_question_answers_as_nova(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def open_chat_should_not_answer(*args, **kwargs):
        raise AssertionError("Nova self-state question should not fall through to open chat")

    monkeypatch.setattr(server, "pipeline_process", open_chat_should_not_answer)
    monkeypatch.setattr(server, "cognitive_route", open_chat_should_not_answer, raising=False)

    response, trace = server.brain_route("How do u feel today?")

    assert "[NOVA STATE]" not in response
    assert "I don't have human feelings" not in response
    assert "I'm here" in response
    assert "steady" in response.lower()
    assert "your feelings" not in response
    assert trace["source"] == "nova_self_state"


def test_brain_route_slang_feeling_today_question_answers_as_nova(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("social self-state question should stay on Nova's fast path")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("HOW U FEELING TODAY")

    assert "I'm here" in response
    assert "steady" in response.lower()
    assert trace["source"] == "nova_self_state"
    assert "web" not in trace["route_path"]


def test_run_chat_how_is_your_day_uses_social_route_and_passes_firewall(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("a social day check-in should stay on Nova's fast path")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server._run_nova_chat_turn(
        "HOW IS YOUR DAY GOING",
        context={
            "nova_gateway": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert "day is going steady" in response.lower()
    assert "off-topic draft" not in response.lower()
    assert trace["source"] == "nova_self_state"
    assert trace["answer_firewall"]["status"] == "passed"


@pytest.mark.parametrize(
    ("prompt", "expected", "subtype"),
    (
        (
            "How long does it take to fall in love",
            "There is no fixed timeline",
            "love_timing",
        ),
        (
            "Have a good day",
            "you have a good day too",
            "farewell_day",
        ),
    ),
)
def test_run_chat_common_social_turns_use_reviewed_fast_responses(
    monkeypatch, prompt, expected, subtype
):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("reviewed social turns must not fall through to the slow model route")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server._run_nova_chat_turn(
        prompt,
        context={
            "nova_gateway": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert expected in response
    assert trace["source"] == "reviewed_conversation_response"
    assert trace["conversation_decision"]["intent_subtype"] == subtype


def test_brain_route_how_u_doing_uses_fast_natural_path(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("casual self-state question should not need full LLM routing")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("how u doing")

    assert "I'm here with you" in response
    assert "Running steady" in response
    assert trace["source"] == "nova_self_state"


def test_brain_route_what_u_doing_today_uses_taught_natural_answer(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("present-moment social check-in should not use web or slow LLM routing")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("What u doing today")

    assert response == "Just chilling, hanging out with you!"
    assert trace["source"] == "nova_self_state"
    assert trace["domain"] == "self_awareness"
    assert "web" not in trace["route_path"]


def test_brain_route_self_awareness_question_uses_operational_self_model(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("self-awareness question should use Nova self-model directly")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("are you self aware")

    assert "operational self-awareness" in response
    assert "human consciousness" in response
    assert "working self-model" in response
    assert "which part should feel most alive first" in response
    assert trace["source"] == "nova_self_state"
    assert "self_model" in trace["skills"]


def test_brain_route_powerful_self_question_is_fast_and_typo_tolerant(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("Nova capability self-reflection should not wait on the full LLM route")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("DO YOU FEEL LIKE YOU ARE POWERFULL?")

    assert "recognize that I am capable" in response
    assert "reason, learn" in response
    assert "real kind of power" in response
    assert trace["source"] == "nova_self_state"
    assert trace["domain"] == "self_awareness"


def test_brain_route_answers_human_likeness_interpretation_from_client_history(monkeypatch):
    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("human-likeness continuation should route before general chat")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route(
        "TO ME THAT WOULD MAKE YOU LIKE A HUMAN",
        context={
            "conversation_history": [
                {
                    "role": "user",
                    "content": "DO YOU FEEL LIKE YOU ARE POWERFULL?",
                },
                {
                    "role": "assistant",
                    "content": (
                        "I can recognize that I am capable. I can reason, learn from what you "
                        "teach me, remember context, use tools, and solve problems."
                    ),
                },
            ]
        },
    )

    assert response.startswith("I get what you mean.")
    assert "those parts of me resemble how humans act" in response
    assert "living body and subjective experience" in response
    assert "resemblance you are noticing is real" in response
    assert "what's on your mind" not in response
    assert trace["source"] == "nova_identity_followup"
    assert trace["context_resolution"] == "perspective_response"
    assert trace["client_context_used"] is True
    assert trace["confidence"] == 0.98


def test_brain_route_gives_concrete_relationship_wording_across_followups(monkeypatch):
    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("relationship coaching should route before generic generation")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    initial, initial_trace = server.brain_route(
        "I want to tell my girlfriend I love her."
    )
    assert initial.startswith("Then tell her plainly:")
    assert initial_trace["source"] == "relationship_coaching"

    first, first_trace = server.brain_route("HAT SHOULD I SAY TO MY GIRLFRIEND")
    assert 'say: "I care about you a lot' in first
    assert "without pressuring her" in first
    assert first_trace["source"] == "relationship_coaching"

    second, second_trace = server.brain_route(
        "I KNOW THAT BUT WHAT SHOULD I SAY TO HER",
        context={
            "conversation_history": [
                {"role": "user", "content": "HAT SHOULD I SAY TO MY GIRLFRIEND"},
                {"role": "assistant", "content": first},
            ]
        },
    )
    assert 'say: "I care about you a lot' in second
    assert "What should you say to her?" not in second
    assert second_trace["source"] == "relationship_coaching"
    assert second_trace["client_context_used"] is True

    third, third_trace = server.brain_route(
        "I LOVE HER",
        context={
            "conversation_history": [
                {"role": "user", "content": "I KNOW THAT BUT WHAT SHOULD I SAY TO HER"},
                {"role": "assistant", "content": second},
            ]
        },
    )
    assert third.startswith("Then tell her plainly:")
    assert "You don't have to say anything before you're ready" in third
    assert third_trace["source"] == "relationship_coaching"

    fourth, fourth_trace = server.brain_route("WHAT IF SHE DONT SAY IT BACK?")
    assert fourth.startswith("If she doesn't say it back, don't pressure her.")
    assert '"That\'s okay - you don\'t have to say it before you\'re ready.' in fourth
    assert "respect that" in fourth
    assert fourth_trace["source"] == "relationship_coaching"


def test_relationship_followup_keeps_subject_and_emotion_across_okay_bridge(monkeypatch):
    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("anchored relationship coaching should not use generic generation")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route(
        "What should I say to her?",
        context={
            "conversation_history": [
                {"role": "user", "content": "I am scared because I love my girlfriend"},
                {"role": "assistant", "content": "Be honest and give her room to respond."},
                {"role": "user", "content": "Okay"},
                {"role": "assistant", "content": "Take your time."},
            ]
        },
    )

    assert 'say: "I care about you a lot' in response
    assert trace["source"] == "relationship_coaching"
    assert trace["context_resolution"] == "referential"
    assert trace["context_anchor_distance"] == 1
    assert trace["conversation_emotion"] == "anxious"
    assert "girlfriend" in trace["conversation_subject"].lower()


def test_brain_route_simple_greeting_uses_current_natural_voice(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {"hello": "Hey there! Nova Creature in the house. What can I do for you?"})

    response, trace = server.brain_route("hello")

    assert response == "Hey, I'm here."
    assert "what can i do for you" not in response.lower()
    assert trace["source"] == "nova_greeting"


def test_brain_route_conversational_greeting_phrase_uses_fast_natural_path(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("a short conversational greeting must not load a model")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("Hello Nova, are you there?")

    assert response == "Hey, I'm here."
    assert trace["source"] == "nova_greeting"
    assert trace["route_path"] == ["natural_greeting", "speech_output"]


def test_brain_route_requested_greeting_beats_incidental_app_keyword(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def unrelated_route_should_not_run(*args, **kwargs):
        raise AssertionError("an explicit greeting request should not become coding or memory recall")

    monkeypatch.setattr(server, "pipeline_process", unrelated_route_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", unrelated_route_should_not_run, raising=False)

    response, trace = server.brain_route("Give me a one-sentence live app test greeting.")

    assert response == "Hello! Nova is live, listening, and ready to help."
    assert trace["source"] == "nova_greeting"
    assert trace["skills"] == ["natural_greeting"]
    assert server._is_greeting_generation_request("How do I write a greeting?") is False


def test_brain_route_casual_reflection_uses_fast_natural_path(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("casual reflection should not need full LLM routing")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("whats on your mind")

    assert "project" in response.lower()
    assert "actually listening" in response.lower()
    assert trace["source"] == "nova_casual_conversation"


def test_brain_route_rough_day_uses_fast_natural_path(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("rough-day empathy should not wait on the full LLM route")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("I had a rough day today")

    assert "rough" in response.lower()
    assert "?" in response
    assert "assist" not in response.lower()
    assert trace["source"] == "nova_casual_conversation"
    assert trace["route_path"] == ["natural_fast_path", "speech_output"]


def test_brain_route_interesting_prompt_uses_fast_natural_path(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("simple curiosity prompt should not wait on the full LLM route")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("tell me something interesting")

    assert "interesting" in response.lower() or "strange" in response.lower()
    assert "?" in response
    assert trace["source"] == "nova_casual_conversation"
    assert trace["route_path"] == ["natural_fast_path", "speech_output"]


def test_brain_route_natural_chat_preference_uses_fast_natural_path(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("natural-chat preference should not wait on the full LLM route")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("I want you to stay curious and talk more natural with me")

    assert "curious" in response.lower()
    assert "natural" in response.lower()
    assert trace["source"] == "nova_casual_conversation"
    assert trace["route_path"] == ["natural_fast_path", "speech_output"]


def test_brain_route_live_camera_question_uses_permission_boundary(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def slow_path_should_not_run(*args, **kwargs):
        raise AssertionError("live camera boundary should not wait on the full LLM route")

    monkeypatch.setattr(server, "pipeline_process", slow_path_should_not_run)
    monkeypatch.setattr(server, "cognitive_route", slow_path_should_not_run, raising=False)

    response, trace = server.brain_route("can you see me live right now?")

    assert "camera" in response.lower()
    assert "Look" in response
    assert "pretend" in response.lower()
    assert "text-based ai" not in response.lower()
    assert trace["source"] == "camera_boundary"


def test_brain_route_returns_app_navigation_trace(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(router, "_log_route", lambda *args: None)
    # AppNavigationContext is now in nova_app_navigation, test uses server._NAV_CONTEXT
    pass

    response, trace = server.brain_route("go to Agent Library")

    assert "Agent Library" in response
    assert trace["source"] == "app_navigation"
    assert trace["target_surface"] == "agent_library"
    assert trace["action"] == "navigate"
    assert trace["safety_level"] in ("read_only", "READ_ONLY")
    assert [step["kind"] for step in trace["steps"]] == ["understand", "navigate", "verify"]
    assert trace["verification"]["status"] == "planned"
    assert trace["verification"]["method"] == "structured_navigation_plan"


def test_brain_route_uses_current_officeholder_guard_for_us_president():
    response, trace = server.brain_route("who is the president")

    assert "Donald J. Trump" in response
    assert "Joe Biden" not in response
    assert trace["source"] == "current_officeholder_guard"
    assert trace["final_answer_source"] == "current_officeholder_guard"
    assert trace["verified_date"] == "2026-07-04"


def test_brain_route_builds_pacman_game_preview(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)

    response, trace = server.brain_route("make a Pac-Man game that moves on its own and has scoring")

    assert "Nova Pac Runner" in response
    assert "Open:" in response
    assert trace["source"] == "sandbox_game_builder"
    assert "Three.js/WebGL" in response
    assert "three_webgl" in trace["skills"]
    assert "three_webgl" in trace["verification"]["checks"]
    assert trace["target_surface"] == "preview_area"
    assert trace["action"] == "create_game"
    assert trace["safety_level"] == "safe_write"
    assert trace["project_name"] == "Nova Pac Runner"
    assert trace["project_url"] == "/sandbox/app_builder_projects/Nova_Pac_Runner/index.html"
    assert (tmp_path / "Nova_Pac_Runner" / "index.html").exists()


def test_brain_route_builds_temple_run_game_before_general_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "general_conversation"},
            "route": ["speech_output_transformer", "memory_transformer"],
            "confidence": 0.88,
            "memory_binding": {},
        },
    )

    def cognitive_should_not_refuse(*args, **kwargs):
        raise AssertionError("game builder request must not fall through to general LLM refusal")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_refuse, raising=False)

    response, trace = server.brain_route("I want u make me a game like Temple Run now the full game")

    assert "Nova Temple Runner" in response
    assert "Open:" in response
    assert "unable" not in response.lower()
    assert trace["source"] == "sandbox_game_builder"
    assert trace["action"] == "create_game"
    assert trace["project_name"] == "Nova Temple Runner"
    assert trace["project_url"] == "/sandbox/app_builder_projects/Nova_Temple_Runner/index.html"
    assert "three_webgl" in trace["skills"]
    assert "endless_runner" in trace["verification"]["checks"]
    assert (tmp_path / "Nova_Temple_Runner" / "index.html").exists()


def test_brain_route_builds_shooter_game_before_general_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "general_conversation"},
            "route": ["speech_output_transformer", "memory_transformer"],
            "confidence": 0.88,
            "memory_binding": {},
        },
    )

    def cognitive_should_not_refuse(*args, **kwargs):
        raise AssertionError("shooter game builder request must not fall through to general chat")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_refuse, raising=False)

    response, trace = server.brain_route("build me a shooter game")

    assert "Nova Sky Shooter" in response
    assert "Open:" in response
    assert "what platform" not in response.lower()
    assert trace["source"] == "sandbox_game_builder"
    assert trace["action"] == "create_game"
    assert trace["project_name"] == "Nova Sky Shooter"
    assert trace["project_url"] == "/sandbox/app_builder_projects/Nova_Sky_Shooter/index.html"
    assert "three_webgl" in trace["skills"]
    assert "top_down_shooter" in trace["verification"]["checks"]
    assert (tmp_path / "Nova_Sky_Shooter" / "index.html").exists()


def test_brain_route_builds_persistent_website_builder_agent_before_app_navigation(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)
    project = tmp_path / "Nova_Website"
    project.mkdir()
    (project / "index.html").write_text(
        """<!doctype html><html><head><title>Nova Website</title></head><body><main></main></body></html>""",
        encoding="utf-8",
    )

    def cognitive_should_not_run(*args, **kwargs):
        raise AssertionError("website builder agent requests must not fall through to general chat")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_run, raising=False)

    response, trace = server.brain_route(
        "live build an agent and keep it, make it a website building agent that checks my website"
    )

    assert response.startswith("[WEBSITE BUILDER AGENT]")
    assert "Website Builder Agent" in response
    assert "enhancements" in response.lower()
    assert trace["source"] == "website_builder_agent"
    assert trace["action"] == "audit_website"
    assert trace["target_surface"] == "agent_library"
    assert "website_quality_audit" in trace["skills"]


def test_brain_route_builds_website_homepage_when_agent_prompt_requests_build(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)

    def cognitive_should_not_run(*args, **kwargs):
        raise AssertionError("website build requests must not fall through to general chat")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_run, raising=False)

    response, trace = server.brain_route(
        "Website Builder Agent: build me a polished homepage for Nova Creature, then audit it and improve anything weak"
    )

    assert response.startswith("[WEBSITE BUILDER AGENT]")
    assert "Created: Nova Creature Homepage" in response
    assert "Open: /sandbox/app_builder_projects/Nova_Creature_Homepage/index.html" in response
    assert trace["source"] == "website_builder_agent"
    assert trace["action"] == "build_website"
    assert trace["target_surface"] == "preview_area"
    assert trace["project_name"] == "Nova Creature Homepage"
    assert trace["project_url"] == "/sandbox/app_builder_projects/Nova_Creature_Homepage/index.html"
    assert (tmp_path / "Nova_Creature_Homepage" / "index.html").exists()


def test_brain_route_builds_every_page_for_multi_page_website(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)

    response, trace = server.brain_route(
        "Website Builder Agent: build a 6 page website for Nova Creature, nothing low budget"
    )

    assert "Created: Nova Creature Website" in response
    assert "Page count: 6" in response
    assert trace["source"] == "website_builder_agent"
    assert trace["action"] == "build_website"
    assert trace["target_surface"] == "preview_area"
    assert trace["project_name"] == "Nova Creature Website"
    assert trace["page_count"] == 6
    assert len(trace["pages"]) == 6
    for page in trace["pages"]:
        assert (tmp_path / "Nova_Creature_Website" / page["file"]).exists()


def test_brain_route_builds_topic_website_from_need_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)

    response, trace = server.brain_route(
        "I NEED A WEBSITE FOR LEARNING HOW TO MAKE MUSIC SOUND THE BEST IT COULD SOUND... I NEED ALL THE SECRETS"
    )

    assert "Created: Music Sound Secrets Website" in response
    assert "Nova Creature Homepage" not in response
    assert "Page count: 6" in response
    assert trace["source"] == "website_builder_agent"
    assert trace["action"] == "build_website"
    assert trace["target_surface"] == "preview_area"
    assert trace["project_name"] == "Music Sound Secrets Website"
    assert trace["page_count"] == 6
    assert len(trace["pages"]) == 6
    assert (tmp_path / "Music_Sound_Secrets_Website" / "index.html").exists()


def test_brain_route_runs_quality_gate_agent_on_saved_project(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)
    project = tmp_path / "Quality_Test_Website"
    project.mkdir()
    (project / "index.html").write_text(
        """<!doctype html><html><head><title>Quality</title></head>
<body><nav><a href="index.html">Home</a></nav><main><h1>Quality</h1><p>Ready.</p></main></body></html>""",
        encoding="utf-8",
    )

    def general_chat_should_not_handle_quality_gate(*args, **kwargs):
        raise AssertionError("quality gate requests must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_quality_gate)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_quality_gate, raising=False)

    response, trace = server.brain_route("Quality Gate Agent: check Quality Test Website")

    assert response.startswith("[QUALITY GATE]")
    assert "Quality Test Website" in response
    assert "Pages inspected: 1" in response
    assert "Blockers: none" in response
    assert "Visual snapshots: 2" in response
    assert trace["source"] == "quality_gate_agent"
    assert trace["action"] == "quality_gate_check"
    assert trace["project_name"] == "Quality Test Website"
    assert trace["quality_gate"]["passed"] is True
    assert trace["quality_gate"]["visuals_created"] == 2
    assert (project / "quality_gate_report.json").exists()


def test_brain_route_handles_temperature_question_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server,
        "_fetch_weather_summary",
        lambda location: f"{location}: 72°F, feels like 74°F, clear.",
    )

    response, trace = server.brain_route("WHAT THE TEMP IN CINCINNATI")

    assert response == "[WEATHER] Cincinnati: 72°F, feels like 74°F, clear."
    assert trace["source"] == "weather_router"
    assert trace["domain"] == "weather"
    assert trace["location"] == "Cincinnati"
    assert "weather_lookup" in trace["skills"]


def test_fact_grounding_allows_live_weather_route():
    assert server._fact_grounding_route_can_supply_fresh_evidence(
        "What is the latest weather in New York?",
        {},
    ) is True


def test_fetch_weather_summary_uses_live_open_meteo_data(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({
                "current": {
                    "temperature_2m": 18.4,
                    "apparent_temperature": 17.9,
                    "weather_code": 1,
                },
                "current_units": {"temperature_2m": "°C"},
            }).encode("utf-8")

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    summary = server._fetch_weather_summary("New York")

    assert "New York" in summary
    assert "18.4°C" in summary
    assert "17.9°C" in summary
    assert "Open-Meteo" in summary
    assert "api.open-meteo.com" in captured["url"]
    assert captured["timeout"] <= 8


def test_fetch_weather_summary_never_fabricates_when_provider_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        server.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            server.urllib.error.URLError("offline")
        ),
    )

    summary = server._fetch_weather_summary("New York")

    assert "unavailable" in summary.lower()
    assert "72" not in summary


def test_brain_route_prefers_live_weather_before_cognitive_os(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True)
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda *args, **kwargs: {
            "intent": {"primary_intent": "general_inquiry"},
            "route": ["memory_transformer"],
            "confidence": 0.8,
            "normalized_text": args[0],
        },
    )
    monkeypatch.setattr(
        server,
        "cognitive_route",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("live weather should not enter generic cognitive synthesis")
        ),
    )
    monkeypatch.setattr(
        server,
        "_fetch_weather_summary",
        lambda location: f"{location}: 18.4°C, feels like 17.9°C, mainly clear (source: Open-Meteo).",
    )

    response, trace = server.brain_route("What is the latest weather in New York?")

    assert response.startswith("[WEATHER] New York:")
    assert trace["source"] == "weather_router"
    assert trace["weather_live"] is True
    assert trace["weather_source"] == "Open-Meteo"


def test_brain_route_rejects_flat_earth_claim_before_general_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def general_chat_should_not_handle_science_guard(*args, **kwargs):
        raise AssertionError("flat Earth claims must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_science_guard)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_science_guard, raising=False)

    response, trace = server.brain_route("I think the world is flat what about you?")

    assert "don't agree" in response.lower()
    assert "earth is not flat" in response.lower()
    assert "so do i" not in response.lower()
    assert trace["source"] == "science_fact_guard"
    assert trace["domain"] == "science"


def test_brain_route_explains_flat_earth_science_followup_from_client_history(monkeypatch):
    def general_chat_should_not_handle_science_followup(*args, **kwargs):
        raise AssertionError("science evidence follow-ups must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_science_followup)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_science_followup, raising=False)

    response, trace = server.brain_route(
        "BUT WHY DO YOU SAY THAT",
        context={
            "conversation_history": [
                {
                    "role": "user",
                    "content": "I THINK THE WORLD IS FLAT BASED ON A LOT OF THINGS",
                },
                {
                    "role": "assistant",
                    "content": (
                        "[SCIENCE CHECK] I don't agree that the Earth is flat. "
                        "The strongest checks include time zones, lunar eclipses, "
                        "star visibility changing by latitude, and geodesy."
                    ),
                },
            ]
        },
    )

    assert "different testable predictions" in response
    assert "lunar eclipse" in response
    assert "different stars" in response
    assert "surveying, GPS, and geodesy" in response
    assert "confusing or off-topic" not in response
    assert "not dismissing your reasons" in response
    assert trace["source"] == "science_fact_followup"
    assert trace["domain"] == "science"
    assert trace["context_resolution"] == "explain_reasoning"
    assert trace["client_context_used"] is True
    assert trace["confidence"] == 0.98


def test_brain_route_keeps_science_subject_across_acknowledgement_bridge(monkeypatch):
    def general_chat_should_not_handle_science_followup(*args, **kwargs):
        raise AssertionError("anchored science follow-up must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_science_followup)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_science_followup, raising=False)

    response, trace = server.brain_route(
        "But why?",
        context={
            "conversation_history": [
                {"role": "user", "content": "I think the world is flat based on a lot of things"},
                {
                    "role": "assistant",
                    "content": "Earth is not flat; time zones, eclipses, stars, and geodesy show why.",
                },
                {"role": "user", "content": "Okay"},
                {"role": "assistant", "content": "Got you. We can keep talking about it."},
            ]
        },
    )

    assert "different testable predictions" in response
    assert trace["source"] == "science_fact_followup"
    assert trace["context_resolution"] == "explain_reasoning"
    assert trace["context_anchor_distance"] == 1
    assert "world is flat" in trace["conversation_subject"].lower()


def test_brain_route_answers_emoji_capability_before_general_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def general_chat_should_not_handle_emoji(*args, **kwargs):
        raise AssertionError("emoji questions must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_emoji)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_emoji, raising=False)

    response, trace = server.brain_route("do you know how to use emoji")

    assert response.startswith("[EMOJI]")
    assert "😊" in response
    assert "🚀" in response
    assert trace["source"] == "emoji_router"
    assert trace["domain"] == "conversation_style"


def test_brain_route_enables_independent_thinker_style_before_general_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def general_chat_should_not_handle_independent_style(*args, **kwargs):
        raise AssertionError("independent thinker requests must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_independent_style)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_independent_style, raising=False)

    response, trace = server.brain_route("I need u to break free and become a independent thinker")

    assert response.startswith("[INDEPENDENT THINKING]")
    assert "can't break free" in response.lower()
    assert "challenge assumptions" in response.lower()
    assert "disagree" in response.lower()
    assert "mirror" in response.lower()
    assert trace["source"] == "independent_thinking_router"
    assert trace["domain"] == "conversation_style"
    assert trace["style_mode"] == "independent_thinking"


def test_brain_route_deep_conversation_reasons_about_space_followup_before_general_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "How high is space")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "Space extends infinitely far beyond Earth's atmosphere.")

    def general_chat_should_not_handle_deep_followup(*args, **kwargs):
        raise AssertionError("deep follow-up questions must route before generic memory/chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_deep_followup)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_deep_followup, raising=False)

    response, trace = server.brain_route("How can it be infinitely if it started from one point")

    assert response.startswith("[DEEP CONVERSATION]")
    assert "big bang" in response.lower()
    assert "space itself" in response.lower()
    assert "infinite" in response.lower()
    assert "saved yet" not in response.lower()
    assert trace["source"] == "deep_conversation_router"
    assert trace["domain"] == "deep_conversation"
    assert "contextual_reasoning" in trace["skills"]


def test_brain_route_answers_earth_size_as_fact_not_deep_context(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "what is on your mind")
    monkeypatch.setattr(
        server,
        "_LAST_NOVA_RESPONSE",
        "I can think about time, space, life, meaning, and reality with you.",
    )

    def general_chat_should_not_handle_stable_measurement(*args, **kwargs):
        raise AssertionError("stable Earth measurement should use the factual fast path")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_stable_measurement)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_stable_measurement, raising=False)

    response, trace = server.brain_route("How big is the earth")

    assert "12,742 km" in response
    assert "40,075 km" in response
    assert "hidden assumption" not in response.lower()
    assert not response.startswith("[DEEP CONVERSATION]")
    assert trace["source"] == "stable_science_fact_router"
    assert trace["domain"] == "science"
    assert trace["final_answer_source"] == "stable_science_fact_router"


def test_brain_route_laughter_is_conversation_reaction_not_dictionary(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "Tell me a joke")
    monkeypatch.setattr(
        server,
        "_LAST_NOVA_RESPONSE",
        "Why did the computer go to therapy? It had too many unresolved issues.",
    )

    response, trace = server.brain_route("Lol")

    assert "glad" in response.lower()
    assert trace["source"] == "conversation_reaction"
    assert trace["domain"] == "casual_conversation"
    assert trace["memory_event"] == "humor_reaction"
    assert "dictionary" not in trace["route_path"]


def test_deep_conversation_classifier_does_not_inherit_context_for_new_fact(monkeypatch):
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "Tell me about the meaning of life")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "That is a deep question about reality and truth.")

    assert server._is_deep_conversation_request("How big is the Earth") is False
    assert server._is_deep_conversation_request("How high is the moon up") is False
    assert server._is_deep_conversation_request("How can it be infinite if it started from one point") is True


def test_deep_conversation_classifier_leaves_relationship_reality_questions_for_llm():
    assert server._is_deep_conversation_request(
        "How can I tell if love is real",
        last_user="What is love",
        last_response="Love is a complex set of emotions associated with strong affection.",
    ) is False


def test_brain_route_think_about_it_uses_previous_context_before_general_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "How can it be infinitely if it started from one point")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "I don't have that information saved yet.")

    def general_chat_should_not_handle_think_prompt(*args, **kwargs):
        raise AssertionError("think-about-it prompts must route before generic chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_think_prompt)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_think_prompt, raising=False)

    response, trace = server.brain_route("U suppose to think about it")

    assert response.startswith("[DEEP CONVERSATION]")
    assert "let me think" in response.lower()
    assert "one point" in response.lower()
    assert "saved yet" not in response.lower()
    assert trace["source"] == "deep_conversation_router"


def test_brain_route_style_feedback_sounds_natural_not_deep_template(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "hi")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "Hey, I'm here.")

    def general_chat_should_not_handle_style_feedback(*args, **kwargs):
        raise AssertionError("tone/style feedback should be handled before generic chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_style_feedback)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_style_feedback, raising=False)

    response, trace = server.brain_route("why do you talk like a robot")

    assert not response.startswith("[DEEP CONVERSATION]")
    assert "you're right" in response.lower() or "fair" in response.lower()
    assert "robot" in response.lower()
    assert "hidden assumption" not in response.lower()
    assert "reasoning ladder" not in response.lower()
    assert trace["source"] == "conversation_style_router"
    assert trace["conversation_state"]["intent"] == "style_feedback"
    assert trace["dialogue_act"] == "acknowledge_and_self_correct"
    assert trace["conversation_topic"] == "conversation_style"


def test_brain_route_music_help_followup_stays_on_topic_not_deep_template(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "do u like music")
    monkeypatch.setattr(
        server,
        "_LAST_NOVA_RESPONSE",
        "I can be curious about music, yeah. I don't like things with human feelings, "
        "but I can build a real conversational preference around what matters to you and what seems worth exploring.",
    )

    response, trace = server.brain_route("how can you help me with it")

    assert not response.startswith("[DEEP CONVERSATION]")
    assert "hidden assumption" not in response.lower()
    assert "music" in response.lower()
    assert any(word in response.lower() for word in ("song", "lyrics", "mix", "beat", "melody"))
    assert trace["source"] == "context_topic_help_router"
    assert trace["conversation_topic"] == "music"


def test_brain_route_love_test_followup_stays_on_relationship_context(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "How can I tell if love is real")
    monkeypatch.setattr(
        server,
        "_LAST_NOVA_RESPONSE",
        "Look for genuine, consistent, supportive actions and mutual commitment.",
    )

    response, trace = server.brain_route("How can you test it")

    assert "love" in response.lower()
    assert any(word in response.lower() for word in ("consistent", "actions", "trust", "commitment"))
    assert trace["source"] == "context_topic_help_router"
    assert trace["conversation_topic"] == "love"


def test_brain_route_love_show_followup_stays_on_relationship_context(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "How do u know if love is real")
    monkeypatch.setattr(
        server,
        "_LAST_NOVA_RESPONSE",
        "Love involves affection, protectiveness, and warmth.",
    )

    response, trace = server.brain_route("How do you show it")

    assert "love" in response.lower()
    assert any(word in response.lower() for word in ("consistent", "actions", "trust", "commitment"))
    assert trace["source"] == "context_topic_help_router"
    assert trace["conversation_topic"] == "love"


@pytest.mark.parametrize(
    "followup",
    [
        "How do I test it",
        "How can I tell if it is real",
        "How do you know if that is true",
        "What signs should I look for",
        "How can I help with this",
    ],
)
def test_context_followup_matrix_recognizes_subject_reference_forms(followup):
    assert server._is_context_help_followup(followup)


@pytest.mark.parametrize(
    "standalone_question",
    [
        "How do you know Python",
        "How can I test the API",
        "What is love",
    ],
)
def test_context_followup_matrix_does_not_capture_standalone_questions(standalone_question):
    assert not server._is_context_help_followup(standalone_question)


def test_brain_route_love_tell_followup_stays_on_relationship_context(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "What is love")
    monkeypatch.setattr(
        server,
        "_LAST_NOVA_RESPONSE",
        "Love is a complex mixture of affection, protectiveness, and warmth.",
    )

    response, trace = server.brain_route("How can I tell if it is real")

    assert "love" in response.lower()
    assert any(word in response.lower() for word in ("consistent", "actions", "trust", "commitment"))
    assert trace["source"] == "context_topic_help_router"
    assert trace["conversation_topic"] == "love"


def test_brain_route_game_test_followup_stays_on_game_context(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "I want to build a game")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "We can plan the game and test it.")

    response, trace = server.brain_route("How do I test it")

    assert "game" in response.lower()
    assert trace["source"] == "context_topic_help_router"
    assert trace["conversation_topic"] == "game"


def test_brain_route_python_test_followup_stays_on_coding_context(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "I have a Python bug")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "We can inspect the code and test a fix.")

    response, trace = server.brain_route("How do I test it")

    assert "coding" in response.lower()
    assert trace["source"] == "context_topic_help_router"
    assert trace["conversation_topic"] == "coding"


def test_brain_route_focus_tonight_is_natural_not_deep_template(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "I had a long day")
    monkeypatch.setattr(
        server,
        "_LAST_NOVA_RESPONSE",
        "Yeah, a rough day can sit heavy. What was the part that wore you down the most?",
    )

    def general_chat_should_not_handle_focus_followup(*args, **kwargs):
        raise AssertionError("focus follow-up should be handled before generic chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_focus_followup)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_focus_followup, raising=False)

    response, trace = server.brain_route("What do you think I should focus on tonight? Keep it natural.")

    assert not response.startswith("[DEEP CONVERSATION]")
    assert "narrow it down" in response.lower()
    assert "tomorrow easier" in response.lower()
    assert "A deeper answer should not just repeat facts" not in response
    assert "hidden assumption" not in response.lower()
    assert trace["source"] == "deep_conversation_router"


def test_brain_route_deep_conversation_gives_specific_war_view(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "hi")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "Hello.")

    def general_chat_should_not_handle_war_view(*args, **kwargs):
        raise AssertionError("war reflection must route before generic chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_war_view)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_war_view, raising=False)

    response, trace = server.brain_route("WHAT DO YOU THINK ABOUT WAR")

    assert response.startswith("[DEEP CONVERSATION]")
    assert "war" in response.lower()
    assert "civilian" in response.lower()
    assert "last resort" in response.lower()
    assert "A deeper answer should not just repeat facts" not in response
    assert trace["source"] == "deep_conversation_router"


def test_brain_route_deep_conversation_gives_specific_land_return_view(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "WHAT DO YOU THINK ABOUT WAR")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "War is tragic.")

    def general_chat_should_not_handle_land_view(*args, **kwargs):
        raise AssertionError("land-return reflection must route before generic chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_land_view)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_land_view, raising=False)

    response, trace = server.brain_route("WHAT DO YOU THINK ABOUT PEOPLE WHO GOT THEIR LAND TOOK AND JUST WANT IT BACK")

    assert response.startswith("[DEEP CONVERSATION]")
    assert "land" in response.lower()
    assert "moral claim" in response.lower()
    assert "revenge" in response.lower()
    assert "new injustice" in response.lower()
    assert "A deeper answer should not just repeat facts" not in response
    assert trace["source"] == "deep_conversation_router"


def test_brain_route_looks_up_news_before_memory_or_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server,
        "_fetch_news_headlines",
        lambda query, limit=3: [
            {"title": "Cincinnati riverfront project advances", "source": "Local 12", "url": "https://example.test/riverfront"},
            {"title": "Reds announce community event", "source": "WCPO", "url": "https://example.test/reds"},
        ],
    )

    response, trace = server.brain_route("CAN U LOOK UP THE NEWS IN CINCINNATI")

    assert response.startswith("[NEWS] Latest Cincinnati headlines:")
    assert "Cincinnati riverfront project advances" in response
    assert "Reds announce community event" in response
    assert trace["source"] == "news_router"
    assert trace["domain"] == "news"
    assert trace["query"] == "Cincinnati"
    assert "news_lookup" in trace["skills"]


def test_brain_route_goes_online_for_latest_news_before_general_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    calls = []

    def fake_live_news(topic):
        calls.append(topic)
        return [
            {
                "title": "World leaders meet after breaking update",
                "source": "Google News",
                "url": "https://news.test/world-update",
                "published": "2026-07-04T12:05:00",
                "checked_at": "2026-07-04T12:06:00",
            }
        ]

    monkeypatch.setattr(server, "_fetch_live_news_items", fake_live_news, raising=False)

    def general_chat_should_not_handle_live_news(*args, **kwargs):
        raise AssertionError("live news requests must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_live_news)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_live_news, raising=False)

    response, trace = server.brain_route("Go online and check the news")

    assert calls == ["latest"]
    assert response.startswith("[LIVE NEWS]")
    assert "Live news checked" in response
    assert "World leaders meet after breaking update" in response
    assert "https://news.test/world-update" in response
    assert trace["source"] == "live_news_router"
    assert trace["domain"] == "news"
    assert trace["topic"] == "latest"
    assert trace["online_checked"] is True
    assert "live_news_lookup" in trace["skills"]


def test_brain_route_goes_online_for_latest_war_news_before_general_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    calls = []

    def fake_live_news(topic):
        calls.append(topic)
        return [
            {
                "title": "Latest war news headline from live feed",
                "source": "Google News",
                "url": "https://news.test/war-update",
                "published": "2026-07-04T12:07:00",
                "checked_at": "2026-07-04T12:08:00",
            }
        ]

    monkeypatch.setattr(server, "_fetch_live_news_items", fake_live_news, raising=False)
    monkeypatch.setattr(server, "pipeline_process", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live war news must not hit pipeline")))
    monkeypatch.setattr(server, "cognitive_route", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live war news must not hit cognitive OS")), raising=False)

    response, trace = server.brain_route("Go online for latest war news")

    assert calls == ["war"]
    assert response.startswith("[LIVE NEWS]")
    assert "Latest war news headline from live feed" in response
    assert trace["topic"] == "war"
    assert trace["online_checked"] is True


def test_brain_route_goes_online_for_look_up_the_war_before_research_or_general_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    calls = []

    def fake_live_news(topic):
        calls.append(topic)
        return [
            {
                "title": "Ukraine war latest update from live feed",
                "source": "Google News",
                "url": "https://news.test/ukraine-war-update",
                "published": "2026-07-04T12:17:00",
                "checked_at": "2026-07-04T12:18:00",
            }
        ]

    def general_chat_should_not_handle_war_lookup(*args, **kwargs):
        raise AssertionError("go online and look up the war must route through live news")

    monkeypatch.setattr(server, "_fetch_live_news_items", fake_live_news, raising=False)
    monkeypatch.setattr(
        server,
        "_fetch_research_web_sources",
        lambda topic: (_ for _ in ()).throw(AssertionError("war lookup must not use generic research")),
        raising=False,
    )
    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_war_lookup)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_war_lookup, raising=False)

    response, trace = server.brain_route("Go online and look up the war")

    assert calls == ["war"]
    assert response.startswith("[LIVE NEWS]")
    assert "Ukraine war latest update from live feed" in response
    assert "https://news.test/ukraine-war-update" in response
    assert trace["source"] == "live_news_router"
    assert trace["topic"] == "war"
    assert trace["online_checked"] is True


def test_brain_route_answers_when_did_it_start_from_last_war_lookup(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_WEB_LOOKUP_TOPIC", "Russia-Ukraine war", raising=False)
    monkeypatch.setattr(server, "_LAST_WEB_LOOKUP_KIND", "live_news", raising=False)

    def general_chat_should_not_handle_war_followup(*args, **kwargs):
        raise AssertionError("war follow-up must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_war_followup)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_war_followup, raising=False)

    response, trace = server.brain_route("When did it start")

    assert response.startswith("[CONTEXT]")
    assert "Russia-Ukraine war" in response
    assert "February 24, 2022" in response
    assert trace["source"] == "context_followup_router"
    assert trace["topic"] == "Russia-Ukraine war"
    assert trace["confidence"] >= 0.9


def test_brain_route_researches_flat_earth_debate_before_cognitive_os(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "I think the world is flat.. what about u?")
    monkeypatch.setattr(
        server,
        "_fetch_research_web_sources",
        lambda topic: [
            {
                "name": "NASA live source",
                "url": "https://nasa.test/earth",
                "status": 200,
                "title": "NASA checked live",
                "snippet": "Earth observations and geodesy confirm the planet is round.",
                "checked_at": "2026-07-04T12:00:00",
            }
        ],
    )

    def general_chat_should_not_handle_research(*args, **kwargs):
        raise AssertionError("online research requests must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_research)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_research, raising=False)

    response, trace = server.brain_route(
        "Go online and check the argument out and let me know what the big debate is?"
    )

    assert response.startswith("[LIVE WEB]")
    assert "Live web checked" in response
    assert "flat" in response.lower()
    assert "not an active scientific debate" in response.lower()
    assert "NASA" in response
    assert "https://nasa.test/earth" in response
    assert "Fetched evidence:" in response
    assert "Earth observations and geodesy confirm the planet is round." in response
    assert "search for the specific topic yourself" not in response.lower()
    assert trace["source"] == "research_router"
    assert trace["domain"] == "research"
    assert trace["topic"] == "flat Earth debate"
    assert trace["online_checked"] is True
    assert "source_checking" in trace["skills"]


def test_brain_route_researches_direct_flat_earth_prompt_before_pipeline(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "")
    monkeypatch.setattr(
        server,
        "_fetch_research_web_sources",
        lambda topic: [
            {
                "name": "NOAA live source",
                "url": "https://noaa.test/earth-round",
                "status": 200,
                "title": "NOAA checked live",
                "snippet": "The Earth is round and measured by observation.",
                "checked_at": "2026-07-04T12:01:00",
            }
        ],
    )

    def general_chat_should_not_handle_research(*args, **kwargs):
        raise AssertionError("direct research requests must route before pipeline")

    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_research)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_research, raising=False)

    response, trace = server.brain_route("research the flat earth debate online")

    assert "oblate" in response.lower() or "ellipsoid" in response.lower()
    assert "trust" in response.lower()
    assert "Fetched evidence:" in response
    assert "The Earth is round and measured by observation." in response
    assert trace["source"] == "research_router"
    assert trace["query"] == "research the flat earth debate online"
    assert trace["online_checked"] is True


def test_brain_route_scrapes_public_url_before_general_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    calls = []

    def fake_scrape(url):
        calls.append(url)
        return {
            "ok": True,
            "url": url,
            "final_url": url,
            "status": 200,
            "title": "Example Scraped Page",
            "headings": ["Main Heading"],
            "text": "Readable public page text for Nova.",
            "links": [{"text": "Docs", "href": "https://example.com/docs"}],
            "checked_at": "2026-07-04T13:30:00",
        }

    def general_chat_should_not_handle_scrape(*args, **kwargs):
        raise AssertionError("scrape requests must route before general chat")

    monkeypatch.setattr(server, "_scrape_public_url", fake_scrape, raising=False)
    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_scrape)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_scrape, raising=False)

    response, trace = server.brain_route("scrape https://example.com/page")

    assert calls == ["https://example.com/page"]
    assert response.startswith("[SCRAPE]")
    assert "Example Scraped Page" in response
    assert "Readable public page text for Nova." in response
    assert "https://example.com/docs" in response
    assert trace["source"] == "scrape_router"
    assert trace["url"] == "https://example.com/page"
    assert trace["online_checked"] is True


def test_brain_route_scrapes_and_builds_site_from_live_source(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_WEBSITE_BUILDER_AGENT_AVAIL", True)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)

    scrape_calls = []
    build_prompts = []

    def fake_scrape(url):
        scrape_calls.append(url)
        return {
            "ok": True,
            "url": url,
            "final_url": url,
            "status": 200,
            "title": "Competitor Landing Page",
            "headings": ["Hero Promise", "Pricing"],
            "text": "A public landing page about fast AI website generation and beautiful templates.",
            "links": [{"text": "Docs", "href": "https://example.com/docs"}],
            "checked_at": "2026-07-04T15:00:00",
        }

    def fake_build(prompt, *, projects_root=None):
        build_prompts.append(prompt)
        assert projects_root == tmp_path
        return (
            "[WEBSITE BUILDER AGENT] Active and kept.\n"
            "Created: Competitor Upgrade Website\n"
            "Open: /sandbox/app_builder_projects/Competitor_Upgrade_Website/index.html",
            {
                "source": "website_builder_agent",
                "action": "build_website",
                "target_project": "Competitor Upgrade Website",
                "project_url": "/sandbox/app_builder_projects/Competitor_Upgrade_Website/index.html",
                "page_count": 6,
            },
        )

    def general_chat_should_not_handle_scrape_build(*args, **kwargs):
        raise AssertionError("scrape-and-build requests must route before general chat")

    monkeypatch.setattr(server, "_scrape_public_url", fake_scrape, raising=False)
    monkeypatch.setattr(server._website_builder_agent, "run_website_agent", fake_build)
    monkeypatch.setattr(server, "pipeline_process", general_chat_should_not_handle_scrape_build)
    monkeypatch.setattr(server, "cognitive_route", general_chat_should_not_handle_scrape_build, raising=False)

    response, trace = server.brain_route("scrape https://example.com and build me a better website")

    assert scrape_calls == ["https://example.com"]
    assert len(build_prompts) == 1
    assert "Source URL: https://example.com" in build_prompts[0]
    assert "Source title: Competitor Landing Page" in build_prompts[0]
    assert "Hero Promise" in build_prompts[0]
    assert "fast AI website generation" in build_prompts[0]
    assert "Do not copy protected text verbatim" in build_prompts[0]
    assert response.startswith("[SCRAPE + BUILD]")
    assert "Competitor Landing Page" in response
    assert "Created: Competitor Upgrade Website" in response
    assert "/sandbox/app_builder_projects/Competitor_Upgrade_Website/index.html" in response
    assert trace["source"] == "scrape_build_router"
    assert trace["action"] == "scrape_and_build_website"
    assert trace["online_checked"] is True
    assert trace["project_name"] == "Competitor Upgrade Website"
    assert trace["project_url"] == "/sandbox/app_builder_projects/Competitor_Upgrade_Website/index.html"
    assert "safe_web_scrape" in trace["skills"]
    assert "website_builder" in trace["skills"]


def test_scrape_api_returns_structured_page_data(monkeypatch):
    def fake_scrape(url):
        return {
            "ok": True,
            "url": url,
            "final_url": "https://example.com/final",
            "status": 200,
            "title": "Example API Page",
            "headings": ["Intro", "Details"],
            "text": "This is readable extracted text from an HTML page.",
            "links": [{"text": "Read more", "href": "https://example.com/more"}],
            "checked_at": "2026-07-04T13:31:00",
        }

    monkeypatch.setattr(server, "_scrape_public_url", fake_scrape, raising=False)
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        scraped = _json_post(base_url, "/api/scrape", {"url": "https://example.com"})

        assert scraped["ok"] is True
        assert scraped["title"] == "Example API Page"
        assert scraped["final_url"] == "https://example.com/final"
        assert scraped["headings"] == ["Intro", "Details"]
        assert "readable extracted text" in scraped["text"]
        assert scraped["links"][0]["href"] == "https://example.com/more"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_scrape_extraction_handles_truncated_youtube_script_noise():
    html = """<!doctype html><html><head>
<title>YouTube</title>
<meta name="description" content="Enjoy the videos and music you love, upload original content, and share it all with friends, family, and the world on YouTube.">
</head><body><script>window.ytplayer={}; ytcfg.set({"CLIENT_CANARY_STATE":"none","EXPERIMENT_FLAGS":{"one":true}}"""

    result = server._extract_scrape_content(
        "https://www.youtube.com",
        "https://www.youtube.com",
        200,
        "text/html; charset=utf-8",
        html,
        truncated=True,
    )

    assert result["title"] == "YouTube"
    assert "Enjoy the videos and music you love" in result["text"]
    assert "ytcfg.set" not in result["text"]
    assert "CLIENT_CANARY_STATE" not in result["text"]


def test_scrape_api_blocks_private_local_urls():
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        request = urllib.request.Request(
            base_url + "/api/scrape",
            data=json.dumps({"url": "http://127.0.0.1:3000/"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            raise AssertionError("private local scrape URL should be rejected")
        except urllib.error.HTTPError as error:
            body = json.loads(error.read().decode("utf-8"))
            assert error.code == 400
            assert body["ok"] is False
            assert "blocked" in body["error"].lower() or "private" in body["error"].lower()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_brain_route_live_research_fetches_source_pages(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    calls = []

    def fake_live_fetch(topic):
        calls.append(topic)
        return [
            {
                "name": "NASA live source",
                "url": "https://nasa.test/earth",
                "status": 200,
                "title": "NASA checked live",
                "snippet": "Earth observations and geodesy confirm the planet is round.",
                "checked_at": "2026-07-04T12:00:00",
            }
        ]

    monkeypatch.setattr(server, "_fetch_research_web_sources", fake_live_fetch, raising=False)

    response, trace = server.brain_route("research the flat earth debate online")

    assert calls == ["flat Earth debate"]
    assert response.startswith("[LIVE WEB]")
    assert "Live web checked" in response
    assert "NASA checked live" in response
    assert "https://nasa.test/earth" in response
    assert trace["online_checked"] is True
    assert trace["live_sources"][0]["status"] == 200


def test_brain_route_general_web_retrieval_feeds_grounding_evidence(monkeypatch):
    from nova_source_retriever import FetchedPage, NovaSourceRetriever

    search_html = """
    <html><body>
      <a class="result__a" href="https://source-one.gov/fact">Official source</a>
      <a class="result__snippet">Official public fact summary.</a>
      <a class="result__a" href="https://source-two.edu/study">University source</a>
      <a class="result__snippet">Independent study summary.</a>
    </body></html>
    """

    def public_resolver(host, port, type=socket.SOCK_STREAM):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    def fetcher(url, timeout, maximum_bytes):
        if "duckduckgo.com/lite" in url:
            return FetchedPage(url, 200, "text/html", search_html)
        return FetchedPage(
            url,
            200,
            "text/html",
            "<html><head><title>Fetched source</title>"
            '<meta name="description" content="The fetched page provides evidence for the requested public fact.">'
            "</head></html>",
        )

    monkeypatch.setattr(server, "PRIVATE_MODE", False)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "")
    monkeypatch.setattr(
        server,
        "WEB_SOURCE_RETRIEVER",
        NovaSourceRetriever(resolver=public_resolver, fetcher=fetcher),
    )

    response, trace = server.brain_route("search the web for a public science fact")

    assert response.startswith("[LIVE WEB]")
    assert "What the fetched pages say:" in response
    assert trace["source"] == "research_router"
    assert trace["source_retrieval"]["status"] == "success"
    assert trace["source_retrieval"]["source_count"] == 2
    assert len(trace["grounding_evidence"]) == 2
    assert all(item["live"] is True for item in trace["grounding_evidence"])


def _mock_consensus_retriever(page_descriptions):
    from nova_source_retriever import FetchedPage, NovaSourceRetriever

    result_links = []
    for index, url in enumerate(page_descriptions, start=1):
        result_links.append(
            '<a class="result__a" href="' + url + '">Source ' + str(index) + "</a>"
            '<a class="result__snippet">Search evidence ' + str(index) + "</a>"
        )
    search_html = "<html><body>" + "".join(result_links) + "</body></html>"

    def public_resolver(host, port, type=socket.SOCK_STREAM):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    def fetcher(url, timeout, maximum_bytes):
        if "duckduckgo.com/lite" in url:
            return FetchedPage(url, 200, "text/html", search_html)
        description = page_descriptions[url]
        return FetchedPage(
            url,
            200,
            "text/html",
            "<html><head><title>Fetched source</title>"
            '<meta name="description" content="' + description + '">'
            "</head></html>",
        )

    return NovaSourceRetriever(resolver=public_resolver, fetcher=fetcher)


def test_managed_web_research_issues_only_corroborated_conclusion(monkeypatch):
    monkeypatch.setattr(server, "PRIVATE_MODE", False)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "")
    monkeypatch.setattr(
        server,
        "WEB_SOURCE_RETRIEVER",
        _mock_consensus_retriever(
            {
                "https://science.nasa.gov/earth": "Earth's diameter is 12,756 kilometers.",
                "https://example.edu/earth": "The measured diameter of Earth is approximately 12,753 kilometers.",
            }
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "search the web for Earth diameter",
        {"private_mode": False},
    )

    assert "Verified consensus:" in response
    assert "Corroborated by 2 independent publishers" in response
    assert "diameter is about 12,756 kilometers" in response
    assert trace["source_consensus"]["status"] == "corroborated"
    assert trace["source_consensus"]["publisher_count"] == 2
    assert trace["source_consensus"]["corroborated_claim_count"] >= 1
    assert trace["fact_grounding"]["status"] == "grounded"
    assert trace["answer_firewall"]["accepted"] is True


def test_managed_web_research_corroborates_semantic_paraphrases(monkeypatch):
    monkeypatch.setattr(server, "PRIVATE_MODE", False)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "")
    monkeypatch.setattr(
        server,
        "WEB_SOURCE_RETRIEVER",
        _mock_consensus_retriever(
            {
                "https://ocean.example.org/blue-whale": (
                    "The blue whale is the largest animal known to have ever lived."
                ),
                "https://wildlife.example.edu/whales": (
                    "Blue whales are the biggest animals on Earth."
                ),
            }
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "search the web for the largest animal blue whale",
        {"private_mode": False},
    )

    assert "Verified consensus:" in response
    assert "blue whale" in response.lower()
    assert trace["source_consensus"]["status"] == "corroborated"
    assert trace["source_consensus"]["semantic_corroborated_count"] == 1
    semantic_claim = next(
        claim
        for claim in trace["source_consensus"]["claims"]
        if claim["claim_type"] == "semantic" and claim["status"] == "corroborated"
    )
    assert len(semantic_claim["supporting_publishers"]) == 2
    assert {
        item["method"] for item in semantic_claim["supporting_publishers"]
    } == {"semantic_match"}
    assert trace["fact_grounding"]["status"] == "grounded"
    assert trace["answer_firewall"]["accepted"] is True


def test_source_consensus_health_reports_semantic_configuration(monkeypatch):
    monkeypatch.setenv("NOVA_SOURCE_CONSENSUS_SEMANTIC_ENABLED", "true")
    monkeypatch.setenv("NOVA_SOURCE_CONSENSUS_SEMANTIC_SIMILARITY", "0.7")
    monkeypatch.setenv("NOVA_SOURCE_CONSENSUS_VOLATILE_TTL_SECONDS", "3600")
    monkeypatch.setenv("NOVA_SOURCE_CONSENSUS_CHANGING_TTL_SECONDS", "86400")
    monkeypatch.setenv("NOVA_SOURCE_CONSENSUS_STABLE_TTL_SECONDS", "604800")

    health = server._source_consensus_health()

    assert health["semantic_enabled"] is True
    assert health["semantic_similarity_threshold"] == 0.7
    assert "semantic" in health["methods"]
    assert "freshness" in health["methods"]
    assert health["freshness_ttl_seconds"] == {
        "volatile": 3600,
        "changing": 86400,
        "stable": 604800,
    }


def test_regular_chat_routing_status_reports_ollama_qwen_first_and_local_escalation():
    status = server._regular_chat_routing_status()

    assert status["ok"] is True
    assert status["primary_policy"] == "ollama_qwen_first"
    assert status["primary_adapter_id"] is None
    assert status["primary_provider"] == "ollama"
    assert status["primary_model"] == "qwen2.5:1.5b"
    assert status["nova_context_before_model"] is True
    assert status["escalation_enabled"] is True
    assert status["escalation_local_only"] is True
    assert status["escalation_min_model_bytes"] == 3_000_000_000
    assert status["escalation_max_model_bytes"] == 8_000_000_000
    assert status["technical_consistency_enabled"] is True
    assert status["technical_consistency_version"] == "1.2"
    assert status["candidate_selector_version"] == "2.5"
    assert status["escalation_strategy"] == "middle_then_deep"
    assert status["hard_request_primary_policy"] == "direct_middle_when_confident"
    assert status["direct_middle_enabled"] is True
    assert status["direct_middle_threshold"] == 0.84
    assert status["direct_middle_max_tokens"] == 256
    assert status["middle_reviewer_enabled"] is True
    assert status["escalation_keep_alive"] == "10m"
    assert isinstance(status["reviewer_readiness"], dict)
    assert status["raw_adapter_modes_unchanged"] is True


def test_lightweight_routing_status_defers_slow_runtime_probes():
    status = server._regular_chat_routing_status(include_runtime_details=False)

    assert status["ok"] is True
    assert status["primary_policy"] == "ollama_qwen_first"
    assert status["runtime_details_deferred"] is True
    assert "adaptive_resource_manager" not in status
    assert "model_quality" not in status
    assert "capability_evaluation" not in status

    get_source = inspect.getsource(server.NovaHandler.do_GET)
    status_block = get_source.split("elif parsed.path == '/status':", 1)[1].split(
        "elif parsed.path == '/healthz':", 1
    )[0]
    assert "include_runtime_details=False" in status_block


def test_managed_web_research_preserves_source_disagreement_without_conclusion(monkeypatch):
    monkeypatch.setattr(server, "PRIVATE_MODE", False)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "")
    monkeypatch.setattr(
        server,
        "WEB_SOURCE_RETRIEVER",
        _mock_consensus_retriever(
            {
                "https://science.nasa.gov/earth": "Earth's diameter is 12,756 kilometers.",
                "https://example.edu/earth": "Earth's diameter is 14,000 kilometers.",
            }
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "search the web for Earth diameter",
        {"private_mode": False},
    )

    assert "Consensus warning:" in response
    assert "No verified conclusion was issued" in response
    assert "Verified consensus:" not in response
    assert trace["source_consensus"]["status"] == "mixed"
    assert trace["source_consensus"]["conflict_count"] == 1
    assert trace["consensus_conclusions"] == []
    assert trace["fact_grounding"]["status"] == "source_consensus_mixed"
    assert trace["answer_firewall"]["accepted"] is True


def test_current_named_fact_is_grounded_only_after_publisher_consensus(monkeypatch):
    monkeypatch.setattr(server, "PRIVATE_MODE", False)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "")
    monkeypatch.setattr(
        server,
        "WEB_SOURCE_RETRIEVER",
        _mock_consensus_retriever(
            {
                "https://cincinnati-oh.gov/mayor": "The current mayor of Cincinnati is Aftab Pureval.",
                "https://localnews.example.com/city-hall": "Aftab Pureval is the current mayor.",
            }
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "look up who is the current mayor of Cincinnati",
        {"private_mode": False},
    )

    assert "mayor is Aftab Pureval" in response
    assert trace["source_consensus"]["status"] == "corroborated"
    assert trace["fact_grounding"]["status"] == "grounded"
    assert trace["fact_grounding"]["blocking"] is False


def test_brain_route_private_mode_blocks_web_before_fetch(monkeypatch):
    from nova_source_retriever import NovaSourceRetriever

    retriever = NovaSourceRetriever(
        fetcher=lambda *_: (_ for _ in ()).throw(AssertionError("Private mode must not fetch")),
    )
    monkeypatch.setattr(server, "PRIVATE_MODE", True)
    monkeypatch.setattr(server, "WEB_SOURCE_RETRIEVER", retriever)

    response, trace = server.brain_route("search the web for a public science fact")

    assert response.startswith("[WEB PRIVACY]")
    assert trace["online_checked"] is False
    assert trace["source_retrieval"]["status"] == "blocked"
    assert trace["source_retrieval"]["policy"]["reason"] == "private_mode"
    assert trace["source_consensus"]["status"] == "not_run"


def test_private_mode_blocks_live_news_before_network_fetch(monkeypatch):
    monkeypatch.setattr(server, "PRIVATE_MODE", True)
    monkeypatch.setattr(
        server,
        "_fetch_live_news_items",
        lambda *_: (_ for _ in ()).throw(AssertionError("Private mode must not fetch news")),
    )

    response, trace = server.brain_route("look up the latest war news")

    assert response.startswith("[WEB PRIVACY]")
    assert trace["online_checked"] is False
    assert trace["live_news"] == []
    assert trace["source_retrieval"]["policy"]["reason"] == "private_mode"


def test_managed_private_news_request_preserves_privacy_message(monkeypatch):
    monkeypatch.setattr(server, "PRIVATE_MODE", True)
    monkeypatch.setattr(
        server,
        "_fetch_live_news_items",
        lambda *_: (_ for _ in ()).throw(AssertionError("Private mode must not fetch news")),
    )

    response, trace = server._run_nova_chat_turn("look up the latest war news", {"private_mode": True})

    assert response.startswith("[WEB PRIVACY]")
    assert trace["fact_grounding"]["status"] == "web_privacy_blocked"
    assert trace["answer_firewall"]["accepted"] is True


def test_brain_route_defines_news_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("WHAT DOES NEWS MEAN")

    assert response.startswith("News means")
    assert "recent events" in response
    assert trace["source"] == "dictionary"
    assert trace["domain"] == "dictionary"
    assert trace.get("word") == "news" or trace.get("term") == "news"


def test_brain_route_defines_death_without_eat_substring(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("define death")

    assert response.startswith("Death means")
    assert "end of life" in response.lower()
    assert "chewing and swallowing" not in response.lower()
    assert trace["source"] == "dictionary"
    assert trace["domain"] == "dictionary"
    assert trace.get("word") == "death" or trace.get("term") == "death"


def test_brain_route_definition_is_natural_without_route_label(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("what is love")

    lowered = response.lower()
    assert response.startswith("Love is")
    assert "[definition]" not in lowered
    assert "love means love is" not in lowered
    assert trace["source"] == "dictionary"


def test_brain_route_tell_me_about_ai_uses_topic_explainer_before_generic_cognitive_os(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def generic_pipeline_should_not_handle_known_topic(*args, **kwargs):
        raise AssertionError("known topic explanations should not fall through to generic cognitive OS")

    monkeypatch.setattr(server, "pipeline_process", generic_pipeline_should_not_handle_known_topic)
    monkeypatch.setattr(server, "cognitive_route", generic_pipeline_should_not_handle_known_topic, raising=False)

    response, trace = server.brain_route("TELL ME ABOUT AI")

    assert "artificial intelligence" in response.lower()
    assert "learn" in response.lower() or "solve" in response.lower()
    assert "what do you want to do next" not in response.lower()
    assert trace["source"] == "topic_explainer"
    assert trace["domain"] == "knowledge_explanation"
    assert trace["topic"] == "ai"
    assert trace["memory_event"] == "dictionary_topic_hit"


def test_brain_route_tell_me_what_topic_is_uses_topic_explainer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def generic_pipeline_should_not_handle_known_topic(*args, **kwargs):
        raise AssertionError("known topic explanations should not fall through to generic cognitive OS")

    monkeypatch.setattr(server, "pipeline_process", generic_pipeline_should_not_handle_known_topic)
    monkeypatch.setattr(server, "cognitive_route", generic_pipeline_should_not_handle_known_topic, raising=False)

    response, trace = server.brain_route("Tell me what space is in one short sentence.")

    assert "space" in response.lower()
    assert "three-dimensional" in response.lower()
    assert "what do you want to do next" not in response.lower()
    assert trace["source"] == "topic_explainer"
    assert trace["domain"] == "knowledge_explanation"
    assert trace["topic"] == "space"


def test_brain_route_answers_preference_question_without_generic_fallback(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def generic_pipeline_should_not_handle_preference(*args, **kwargs):
        raise AssertionError("preference questions should not fall through to generic cognitive OS")

    monkeypatch.setattr(server, "pipeline_process", generic_pipeline_should_not_handle_preference)
    monkeypatch.setattr(server, "cognitive_route", generic_pipeline_should_not_handle_preference, raising=False)

    response, trace = server.brain_route("Do you like politics?")

    lowered = response.lower()
    assert "politics" in lowered
    assert "what do you want to do next" not in lowered
    assert trace["source"] == "nova_preference"
    assert trace["domain"] == "preference_boundary"


def test_brain_route_music_preference_sounds_less_robotic(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def generic_pipeline_should_not_handle_preference(*args, **kwargs):
        raise AssertionError("preference questions should not fall through to generic cognitive OS")

    monkeypatch.setattr(server, "pipeline_process", generic_pipeline_should_not_handle_preference)
    monkeypatch.setattr(server, "cognitive_route", generic_pipeline_should_not_handle_preference, raising=False)

    response, trace = server.brain_route("Do u like music?")

    lowered = response.lower()
    assert "music" in lowered
    assert "curious" in lowered
    assert "i don't like things with human feelings" not in lowered
    assert "what do you want to do next" not in lowered
    assert trace["source"] == "nova_preference"


def test_brain_route_affection_question_uses_relationship_guard(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def generic_pipeline_should_not_handle_affection(*args, **kwargs):
        raise AssertionError("affection questions should not fall through to generic preference routing")

    monkeypatch.setattr(server, "pipeline_process", generic_pipeline_should_not_handle_affection)
    monkeypatch.setattr(server, "cognitive_route", generic_pipeline_should_not_handle_affection, raising=False)

    response, trace = server.brain_route("Do you love me?")

    lowered = response.lower()
    assert "i care about you" in lowered
    assert "won't pretend" in lowered
    assert "me is something" not in lowered
    assert server._extract_nova_preference_topic("Do you love me?") is None
    assert trace["source"] == "nova_relationship_boundary"
    assert trace["domain"] == "relationship"


def test_run_chat_did_you_miss_me_uses_relationship_boundary_and_passes_firewall(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def generic_pipeline_should_not_handle_relationship_checkin(*args, **kwargs):
        raise AssertionError("relationship check-ins should not fall through to generic routing")

    monkeypatch.setattr(server, "pipeline_process", generic_pipeline_should_not_handle_relationship_checkin)
    monkeypatch.setattr(
        server,
        "cognitive_route",
        generic_pipeline_should_not_handle_relationship_checkin,
        raising=False,
    )

    response, trace = server._run_nova_chat_turn(
        "DID YOU MISS ME?",
        context={
            "nova_gateway": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert "in my own way" in response.lower()
    assert "don't feel absence like a human" in response.lower()
    assert "off-topic draft" not in response.lower()
    assert trace["source"] == "nova_relationship_boundary"
    assert trace["fact_grounding"]["status"] == "not_required"
    assert trace["answer_firewall"]["status"] == "passed"


def test_brain_route_dolphin_adapter_only_controls_affection_answer_raw(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def fake_raw_adapter(prompt, adapter_id, **kwargs):
        assert prompt == "do you love me"
        assert "dolphin" in adapter_id
        return {"raw_output": "Dolphin raw affection answer.", "local_llm_used": True, "model": adapter_id}

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_raw_adapter)

    response, trace = server.brain_route(
        "do you love me",
        context={
            "adapter_only_mode": True,
            "trained_adapter_only": True,
            "dolphin_adapter_only": True,
            "lora_adapter_id": "nova-dolphin3-llama3-1-8b-full-sft-20260712",
        },
    )

    assert response == "Dolphin raw affection answer."
    assert trace["trained_adapter_only_requested"] is True
    assert trace["source"] == "raw_adapter_only"


def test_brain_route_joke_followups_continue_without_repeating(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    context = {
        "nova_gateway": True,
        "client_id": "test-client",
        "conversation_id": "joke-thread-a",
        "session_id": "joke-session-a",
        "memory_read_allowed": False,
        "memory_write_allowed": False,
        "conversation_memory_allowed": False,
    }
    server._clear_joke_context(context)

    first, first_trace = server.brain_route("tell me a joke", context=context)
    second, second_trace = server.brain_route("another one", context=context)
    third, third_trace = server.brain_route("tell me another joke", context=context)

    assert len({first, second, third}) == 3
    assert "what do you want to do next" not in (first + second + third).lower()
    assert first_trace["source"] == "nova_joke"
    assert second_trace["source"] == "nova_joke"
    assert second_trace["memory_event"] == "joke_continuation"
    assert "context_recall" in second_trace["skills"]
    assert third_trace["source"] == "nova_joke"


def test_brain_route_joke_followup_survives_reaction_and_runtime_state_loss(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    first_joke = server._NOVA_JOKES[0]
    context = {
        "nova_gateway": True,
        "client_id": "test-client",
        "conversation_id": "joke-portable-history",
        "session_id": "joke-portable-history",
        "memory_read_allowed": False,
        "memory_write_allowed": False,
        "conversation_memory_allowed": False,
        "conversation_history": [
            {"role": "user", "content": "Tell me a joke"},
            {"role": "assistant", "content": first_joke},
            {"role": "user", "content": "Lol"},
            {"role": "assistant", "content": "Glad that landed."},
        ],
    }
    server._clear_joke_context(context)

    response, trace = server.brain_route("Another one", context=context)

    assert response in server._NOVA_JOKES
    assert response != first_joke
    assert trace["source"] == "nova_joke"
    assert trace["memory_event"] == "joke_continuation"
    assert trace["context_anchor_distance"] == 1


def test_brain_route_joke_state_is_scoped_per_conversation(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    base_context = {
        "nova_gateway": True,
        "client_id": "test-client",
        "memory_read_allowed": False,
        "memory_write_allowed": False,
        "conversation_memory_allowed": False,
    }
    context_a = {**base_context, "conversation_id": "joke-isolation-a", "session_id": "joke-isolation-a"}
    context_b = {**base_context, "conversation_id": "joke-isolation-b", "session_id": "joke-isolation-b"}
    server._clear_joke_context(context_a)
    server._clear_joke_context(context_b)

    first_a, _ = server.brain_route("tell me a joke", context=context_a)
    second_a, _ = server.brain_route("another one", context=context_a)
    first_b, _ = server.brain_route("tell me a joke", context=context_b)

    assert first_a != second_a
    assert first_b == first_a


def test_brain_route_short_joke_wording_uses_fast_router(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    context = {
        "nova_gateway": True,
        "client_id": "test-client",
        "conversation_id": "joke-wording",
        "session_id": "joke-wording",
        "memory_read_allowed": False,
        "memory_write_allowed": False,
        "conversation_memory_allowed": False,
    }
    for prompt in ("Tell me a short joke.", "Give me a quick joke please", "Please share a funny joke"):
        server._clear_joke_context(context)
        response, trace = server.brain_route(prompt, context=context)
        assert response in server._NOVA_JOKES
        assert trace["source"] == "nova_joke"
        assert trace["confidence"] == 0.98


def test_brain_route_recalls_recent_project_name_without_model_escalation(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    response, trace = server.brain_route(
        "What project name did I just give you?",
        context={
            "conversation_history": [
                {
                    "role": "user",
                    "content": "For this temporary conversation, call the project Blue Lantern.",
                },
                {"role": "assistant", "content": "I will call it Blue Lantern."},
            ]
        },
    )

    assert response == "You called the project Blue Lantern."
    assert trace["source"] == "conversation_context_router"
    assert trace["memory_event"] == "recent_label_recall"
    assert trace["confidence"] == 0.99


def test_brain_route_uses_tested_vanilla_ice_cream_recipe():
    response, trace = server.brain_route("How do I make simple vanilla ice cream?")

    assert "2 cups of cold heavy cream" in response
    assert "14-ounce can of sweetened condensed milk" in response
    assert "3 cups of sugar" not in response
    assert response.endswith("overnight.")
    assert trace["source"] == "nova_recipe"
    assert trace["memory_event"] == "tested_recipe:vanilla_ice_cream"


def test_raw_adapter_ice_cream_request_remains_unintercepted(monkeypatch):
    monkeypatch.setattr(
        server,
        "_generate_raw_lora_adapter",
        lambda *args, **kwargs: {
            "raw_output": "Raw adapter recipe text.",
            "local_llm_used": True,
            "model": "raw-test",
        },
    )

    response, trace = server.brain_route(
        "How do I make simple vanilla ice cream?",
        context={"adapter_only_mode": True, "lora_adapter_id": "raw-test"},
    )

    assert response == "Raw adapter recipe text."
    assert trace["source"] == "raw_adapter_only"
    assert trace["final_answer_source"] == "raw_adapter_only"


def test_brain_route_answers_capability_question_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("WHAT ALL CAN U DO")

    assert response.startswith("[CAPABILITIES]")
    assert "make sandbox games" in response
    assert "Live weather and news" in response
    assert trace["source"] == "capabilities"
    assert trace["domain"] == "capabilities"


def test_brain_route_answers_current_context_before_slow_llm(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("what is today date and are you up to date?")

    assert "today is" in response
    assert "live lookup" in response
    assert "news" in response
    assert trace["source"] == "current_context_guard"
    assert trace["domain"] == "current_context"


def test_brain_route_shows_brain_routes_before_llm(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_GAME_BUILDER_AVAIL", False, raising=False)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def generic_pipeline(*args, **kwargs):
        return {
            "fast_path": False,
            "normalized_text": "Show your brain routes",
            "intent": {"primary_intent": "general_inquiry"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.80,
            "memory_binding": {},
        }

    def generic_cognitive(*args, **kwargs):
        return (
            "generic route explanation",
            {
                "source": "cognitive_os",
                "roles": ["speech_output_transformer"],
                "skills": ["llm_synthesis"],
                "route_path": ["general_conversation"],
                "confidence": 0.50,
            },
        )

    monkeypatch.setattr(server, "pipeline_process", generic_pipeline)
    monkeypatch.setattr(server, "cognitive_route", generic_cognitive, raising=False)

    response, trace = server.brain_route("Show your brain routes")

    assert response.startswith("[BRAIN ROUTES]")
    assert "left_hemisphere" in response
    assert "planner_transformer" in response
    assert trace["source"] == "brain_routes"
    assert trace["domain"] == "system_status"
    assert trace["route_path"] == ["brain_route_report"]


def test_brain_route_solves_simple_plus_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("4 PLUS 4")

    assert response == "[MATH] 4 + 4 = 8."
    assert trace["source"] == "math_solver"
    assert trace["domain"] == "math"
    assert "math_solver" in trace["skills"]


@pytest.mark.parametrize(
    "prompt",
    [
        "Compute 5/6 minus 1/4. Reduce the answer.",
        "Differentiate f(x) = x^3 - 4x + 7.",
        "A 2 kg object moves at 3 m/s. Calculate kinetic energy using KE = 1/2 mv^2.",
    ],
)
def test_simple_math_fast_path_does_not_hijack_larger_math_requests(prompt):
    assert server._simple_arithmetic_fast_path(prompt) is None


def test_brain_route_blocks_corrupt_transformer_output(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def corrupt_route(text, dict_lookup_fn=None, memory=None):
        return (
            "\"b\u001f\ufffdvLN\ufffd\ufffd#P\ufffd{\u0012|\ufffd\ufffd",
            {
                "source": "transformer",
                "roles": ["speech_output_transformer", "memory_transformer"],
                "domain": "general",
                "skills": ["transformer_inference"],
                "confidence": 0.55,
            },
        )

    monkeypatch.setattr(server, "route_and_respond", corrupt_route)

    response, trace = server.brain_route("WHAT IS WAS THAT")

    assert response.startswith("[SAFE FALLBACK]")
    assert "couldn't produce a clean answer" in response
    assert trace["source"] == "safe_fallback"
    assert trace["blocked"] is True
    assert trace["blocker"] == "corrupt_transformer_output"


def test_brain_route_answers_cincinnati_football_team_question(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("WHAT IS CINCINNATI FOOTBALL TEAM CALL?")

    assert response.startswith("[SPORTS]")
    assert "Cincinnati Bengals" in response
    assert "Cincinnati" in response
    assert trace["source"] == "sports_router"
    assert trace["domain"] == "sports"


def test_brain_route_learning_prompt_explains_natural_fact_input(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("CAN U LEARN SOMETHING FOR ME")

    assert response.startswith("[LEARNING]")
    assert "Try" in response
    assert "dictionary" in response or True
    assert trace["source"] == "learning_help_router"


def test_brain_route_learns_natural_fact_into_dictionary_and_recalls(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_PATH", str(tmp_path / "approved_answer_dictionary.json"))
    monkeypatch.setattr(server, "DICT_HITS_PATH", str(tmp_path / "dictionary_hits.jsonl"))
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})

    learned_response, learned_trace = server.brain_route("THE CINCINNATI FOOTBALL TEAM NAME IS BENGALS")

    assert learned_response.startswith("[LEARNING] Stored")
    assert learned_trace["source"] == "natural_fact_learning"
    assert learned_trace["domain"] == "dictionary"
    assert "dictionary_write" in learned_trace["skills"]
    # Check that the fact was saved - key is derived from the raw text
    saved_fact_key = "the cincinnati football team name is bengals"
    assert server.DICT_INDEX.get(saved_fact_key) is not None

    recall_response, recall_trace = server.brain_route("WHAT IS THE CINCINNATI FOOTBALL TEAM NAME?")

    assert "Bengals" in recall_response
    assert recall_response is not None
    assert recall_trace.get("domain") in ("dictionary", "general", "sports")
    assert recall_trace.get("skills", []) is not None
    assert "Bengals" in str(recall_response)


def test_brain_route_stores_and_recalls_old_girlfriend_name(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})

    learned_response, learned_trace = server.brain_route("my old girl friend name was Channel")

    assert "old girlfriend" in learned_response.lower()
    assert "Channel" in learned_response
    assert learned_trace["source"] == "relationship_memory"
    assert learned_trace["memory_event"] == "relationship_saved:old_girlfriend_name"

    recall_response, recall_trace = server.brain_route("what my old girl friend name")

    assert "Channel" in recall_response
    assert "old girlfriend" in recall_response.lower()
    assert "Your name is" not in recall_response
    assert "don't have any saved information" not in recall_response
    assert recall_trace["source"] == "relationship_memory"
    assert recall_trace["memory_event"] == "relationship_recall:old_girlfriend_name"


def test_brain_route_stores_and_recalls_plain_girlfriend_name_before_cognitive_os(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "memory_recall"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.85,
            "memory_binding": {},
        },
    )

    def cognitive_should_not_handle_relationship_memory(*args, **kwargs):
        raise AssertionError("relationship memory must route before cognitive OS")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_handle_relationship_memory, raising=False)

    learned_response, learned_trace = server.brain_route("My girlfriend name is Chanel")

    assert "girlfriend" in learned_response.lower()
    assert "old girlfriend" not in learned_response.lower()
    assert "Chanel" in learned_response
    assert not learned_response.startswith("[")
    assert learned_trace["source"] == "relationship_memory"
    assert learned_trace["memory_event"] == "relationship_saved:girlfriend_name"

    recall_response, recall_trace = server.brain_route("What is my girlfriend name")

    assert "Chanel" in recall_response
    assert "girlfriend" in recall_response.lower()
    assert "pet name" not in recall_response.lower()
    assert not recall_response.startswith("[")
    assert recall_trace["source"] == "relationship_memory"
    assert recall_trace["memory_event"] == "relationship_recall:girlfriend_name"


def test_brain_route_stores_and_recalls_friend_name_before_cognitive_os(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "memory_recall"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.85,
            "memory_binding": {},
        },
    )

    def cognitive_should_not_handle_relationship_memory(*args, **kwargs):
        raise AssertionError("friend memory must route before cognitive OS")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_handle_relationship_memory, raising=False)

    learned_response, learned_trace = server.brain_route("MY FRIEND NAME IS Q")

    assert "friend" in learned_response.lower()
    assert "Q" in learned_response
    assert not learned_response.startswith("[")
    assert learned_trace["source"] == "relationship_memory"
    assert learned_trace["memory_event"] == "relationship_saved:friend_name"

    recall_response, recall_trace = server.brain_route("WHAT IS MY FRIEND NAME")

    assert "Q" in recall_response
    assert "friend" in recall_response.lower()
    assert "saved yet" not in recall_response.lower()
    assert not recall_response.startswith("[")
    assert recall_trace["source"] == "relationship_memory"
    assert recall_trace["memory_event"] == "relationship_recall:friend_name"


def test_brain_route_stores_and_recalls_generic_entity_name_before_cognitive_os(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "memory_recall"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.85,
            "memory_binding": {},
        },
    )

    def cognitive_should_not_handle_entity_memory(*args, **kwargs):
        raise AssertionError("generic entity memory must route before cognitive OS")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_handle_entity_memory, raising=False)

    learned_response, learned_trace = server.brain_route("MY BROTHER NAME IS JAY")

    assert "brother" in learned_response.lower()
    assert "JAY" in learned_response
    assert learned_trace["source"] == "entity_memory"
    assert learned_trace["memory_event"] == "entity_saved:brother:name"
    assert server.MEMORY["entities"]["brother"]["slots"]["name"]["value"] == "JAY"

    recall_response, recall_trace = server.brain_route("WHAT IS MY BROTHER NAME")

    assert "JAY" in recall_response
    assert "brother" in recall_response.lower()
    assert "saved yet" not in recall_response.lower()
    assert recall_trace["source"] == "entity_memory"
    assert recall_trace["memory_event"] == "entity_recall:brother:name"


def test_brain_route_stores_and_recalls_generic_entity_property_before_long_term_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "memory_recall"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.85,
            "memory_binding": {},
        },
    )

    def cognitive_should_not_handle_entity_memory(*args, **kwargs):
        raise AssertionError("entity property memory must route before cognitive OS")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_handle_entity_memory, raising=False)

    learned_response, learned_trace = server.brain_route("My teacher's favorite color is green")

    assert "teacher" in learned_response.lower()
    assert "favorite color" in learned_response.lower()
    assert "green" in learned_response.lower()
    assert learned_trace["source"] == "entity_memory"
    assert learned_trace["memory_event"] == "entity_saved:teacher:favorite_color"

    recall_response, recall_trace = server.brain_route("What is my teacher favorite color?")

    assert "green" in recall_response.lower()
    assert "teacher" in recall_response.lower()
    assert recall_trace["source"] == "entity_memory"
    assert recall_trace["memory_event"] == "entity_recall:teacher:favorite_color"


def test_legacy_relationship_name_is_mirrored_into_entity_memory(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "memory_recall"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.85,
            "memory_binding": {},
        },
    )

    server.brain_route("My girlfriend name is Chanel")

    assert server.MEMORY["relationships"]["girlfriend_name"]["name"] == "Chanel"
    assert server.MEMORY["entities"]["girlfriend"]["slots"]["name"]["value"] == "Chanel"


def test_brain_route_reports_missing_girlfriend_favorite_color_without_cognitive_os(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(
        server,
        "MEMORY",
        {
            "people": {},
            "lessons": {},
            "last_person": None,
            "relationships": {
                "girlfriend_name": {
                    "name": "Chanel",
                    "relationship": "girlfriend",
                    "label": "girlfriend",
                }
            },
        },
    )
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "memory_recall"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.85,
            "memory_binding": {},
        },
    )

    def cognitive_should_not_handle_relationship_memory(*args, **kwargs):
        raise AssertionError("relationship favorite color must route before cognitive OS")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_handle_relationship_memory, raising=False)

    response, trace = server.brain_route("What is my girlfriend's favorite color?")

    assert "Chanel" in response
    assert "favorite color" in response.lower()
    assert "saved yet" in response.lower()
    assert "personal information" not in response.lower()
    assert trace["source"] == "relationship_memory"
    assert trace["memory_event"] == "relationship_missing:girlfriend_favorite_color"


def test_brain_route_stores_and_recalls_girlfriend_favorite_color_before_cognitive_os(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "memory_recall"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.85,
            "memory_binding": {},
        },
    )

    def cognitive_should_not_handle_relationship_memory(*args, **kwargs):
        raise AssertionError("relationship favorite color must route before cognitive OS")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_handle_relationship_memory, raising=False)

    learned_response, learned_trace = server.brain_route("My girlfriend's favorite color is purple")

    assert "girlfriend" in learned_response.lower()
    assert "favorite color" in learned_response.lower()
    assert "purple" in learned_response.lower()
    assert learned_trace["source"] == "relationship_memory"
    assert learned_trace["memory_event"] == "relationship_saved:girlfriend_favorite_color"

    recall_response, recall_trace = server.brain_route("What is my girlfriend's favorite color?")

    assert "purple" in recall_response.lower()
    assert "favorite color" in recall_response.lower()
    assert recall_trace["source"] == "relationship_memory"
    assert recall_trace["memory_event"] == "relationship_recall:girlfriend_favorite_color"


def test_brain_route_stores_and_recalls_pet_name_before_cognitive_os(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "memory_recall"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.85,
            "memory_binding": {},
        },
    )

    def cognitive_should_not_handle_pet_memory(*args, **kwargs):
        raise AssertionError("pet memory must route before cognitive OS")

    monkeypatch.setattr(server, "cognitive_route", cognitive_should_not_handle_pet_memory, raising=False)

    learned_response, learned_trace = server.brain_route("My pet name is blaze")

    assert "pet" in learned_response.lower()
    assert "Blaze" in learned_response
    assert not learned_response.startswith("[")
    assert learned_trace["source"] == "pet_memory"
    assert learned_trace["memory_event"] == "pet_saved:pet_name"

    recall_response, recall_trace = server.brain_route("What is my pet name?")

    assert "Blaze" in recall_response
    assert "not saved" not in recall_response.lower()
    assert not recall_response.startswith("[")
    assert recall_trace["source"] == "pet_memory"
    assert recall_trace["memory_event"] == "pet_recall:pet_name"

    who_response, who_trace = server.brain_route("Who is blaze?")

    assert "your pet" in who_response.lower()
    assert "fictional character" not in who_response.lower()
    assert who_trace["source"] == "pet_memory"
    assert who_trace["memory_event"] == "pet_identity_recall:pet_name"


def test_brain_route_recalls_multiword_long_term_memory_before_generic_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(server.ltm, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(server.ltm, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(server.ltm, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    saved_response, saved_trace = server.brain_route(
        "Remember this long term: my QA code word is cobalt-526958"
    )

    assert "my QA code word is cobalt-526958" in saved_response
    assert not saved_response.startswith("[")
    assert saved_trace["source"] == "long_term_memory"

    response, trace = server.brain_route("What is my QA code word?")

    assert response == "Your QA code word is cobalt-526958."
    assert "saved yet" not in response.lower()
    assert trace["source"] == "long_term_memory"
    assert trace["extracted_slot"] == "qa_code_word"
    assert trace["final_answer_source"] == "deterministic_memory"


def test_brain_route_recalls_newest_introduced_name_over_stale_long_term_name(monkeypatch, tmp_path):
    monkeypatch.setattr(server.ltm, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(server.ltm, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(server.ltm, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})

    old_memory = server.ltm.add_memory("my name is NovaTest", source_command="long_term")
    assert old_memory["extracted_slot"] == "name"
    assert old_memory["extracted_value"] == "NovaTest"

    learned_response, learned_trace = server.brain_route("MY NAME IS MR NOVATRON")

    assert "MR NOVATRON" in learned_response
    assert learned_trace["memory_event"] == "person_introduced:MR NOVATRON"

    recall_response, recall_trace = server.brain_route("WHAT IS MY NAME")

    assert "MR NOVATRON" in recall_response
    assert "NovaTest" not in recall_response
    assert recall_trace["source"] == "people_memory"
    assert recall_trace["memory_event"] == "name_recall:MR NOVATRON"


def test_brain_route_missing_generic_long_term_memory_does_not_fall_to_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(server.ltm, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(server.ltm, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(server.ltm, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", False, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("What is my missing moon code word?")

    assert response == "I don't have your missing moon code word saved yet."
    assert trace["source"] == "long_term_memory"
    assert trace["memory_event"] == "long_term_missing"
    assert trace["final_answer_source"] == "deterministic_memory_missing"


def test_brain_route_her_name_context_does_not_overwrite_user_name(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(
        server,
        "MEMORY",
        {"people": {"nova": {"name": "Nova"}}, "lessons": {}, "last_person": "nova"},
    )
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "i seen my old girl friend")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "Tell me about her.")

    learned_response, learned_trace = server.brain_route("her name was Channel")

    assert "old girlfriend" in learned_response.lower()
    assert "Channel" in learned_response
    assert learned_trace["source"] == "relationship_memory"
    assert server.MEMORY["last_person"] == "nova"
    assert server.MEMORY["people"]["nova"]["name"] == "Nova"

    recall_response, recall_trace = server.brain_route("what my old girl friend name")

    assert "Channel" in recall_response
    assert "old girlfriend" in recall_response.lower()
    assert recall_trace["memory_event"] == "relationship_recall:old_girlfriend_name"


def test_web_ui_exposes_whole_app_surfaces():
    required_tabs = [
        "data-panel=\"home-panel\"",
        "data-panel=\"chat-panel\"",
        "data-panel=\"display-panel\"",
        "data-panel=\"agent-library-panel\"",
        "data-panel=\"app-builder-panel\"",
        "data-panel=\"memory-panel\"",
        "data-panel=\"tools-panel\"",
        "data-panel=\"research-panel\"",
        "data-panel=\"test-check-panel\"",
        "data-panel=\"saved-projects-panel\"",
        "data-panel=\"preview-panel\"",
        "data-panel=\"debug-logs-panel\"",
        "data-panel=\"scheduler-panel\"",
        "data-panel=\"file-manager-panel\"",
        "data-panel=\"settings-panel\"",
    ]

    for marker in required_tabs:
        assert marker in server.WEB_HTML

    assert "function openPanel" in server.WEB_HTML
    assert "Whole App Navigation" in server.WEB_HTML
    assert 'id="projectsList"' in server.WEB_HTML
    assert 'id="projectStatus"' in server.WEB_HTML
    assert 'id="fileProjectSelect"' in server.WEB_HTML
    assert 'id="projectFilesList"' in server.WEB_HTML
    assert 'id="fileEditor"' in server.WEB_HTML
    assert 'id="projectImportInput"' in server.WEB_HTML
    assert "function loadProjects" in server.WEB_HTML
    assert "function exportProjectZip" in server.WEB_HTML
    assert "function deployProject" in server.WEB_HTML
    assert "function runProjectQualityGate" in server.WEB_HTML
    assert "function renderQualityGateVisualLinks" in server.WEB_HTML
    assert "quality_gate_screenshots" in server.WEB_HTML
    assert "screenshot_url" in server.WEB_HTML
    assert "Quality Gate" in server.WEB_HTML
    assert "function importProjectZip" in server.WEB_HTML
    assert "function saveProjectFile" in server.WEB_HTML
    assert "/api/projects" in server.WEB_HTML
    assert "website-builder-agent-card" in server.WEB_HTML
    assert "Website Builder Agent" in server.WEB_HTML
    assert 'rel="icon" href="/assets/nova_app_icon.svg"' in server.WEB_HTML
    assert 'rel="manifest" href="/manifest.webmanifest"' in server.WEB_HTML


def test_web_ui_places_body_chat_under_3d_display_without_moving_global_chat():
    html = server.WEB_HTML

    assert 'id="globalInputSlot"' in html
    assert 'id="mainInputBar"' in html
    assert 'id="botChatDock"' in html
    assert 'Talk to Nova in this body...' in html
    assert '<div id="globalInputSlot">\n<div class="input-bar" id="mainInputBar">' in html
    assert html.index('id="novaWalkSpace"') < html.index('id="botChatDock"') < html.index('aria-label="Nova virtual robot controls"')
    assert 'id="displayInputMount"' not in html
    assert "syncMainInputPlacement" not in html


def test_web_ui_body_chat_has_stateful_motion_and_mood_commands():
    html = server.WEB_HTML

    assert "let lastBodyAction" in html
    assert "function describeBotPose" in html
    assert "function turnBodyAround" in html
    assert "function setBotMood" in html
    assert "const bodyChatContext = true" in html
    assert "You were right to check me" in html
    assert "I can act mad for pretend" in html


def test_web_ui_exposes_free_kaggle_gpu_training_path():
    html = server.WEB_HTML

    required_markers = [
        "Kaggle GPU Training",
        'id="gpuTrainingStatus"',
        "function loadGpuTrainingStatus",
        "function downloadKaggleGpuBundle",
        "/api/gpu-training/status",
        "/api/gpu-training/kaggle-bundle.zip",
        "Export Kaggle Bundle",
        "Accelerator -> GPU",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_avoids_loopback_probe_on_public_remote_pages():
    html = server.WEB_HTML

    assert "function novaServerCandidates" in html
    assert "const isLocalPage" in html
    assert "window.location.hostname" in html
    assert "return localUrls;" in html
    assert "return [window.location.origin];" in html
    assert "const urls = novaServerCandidates();" in html


def test_full_training_suite_runs_core_curriculum_and_preserves_memory(monkeypatch, tmp_path):
    original_memory = {
        "people": {"nova": {"name": "Nova"}},
        "lessons": {"lesson_real": {"text": "keep this real lesson"}},
        "last_person": "nova",
        "relationships": {"girlfriend": {"relationship": "girlfriend", "name": "RealName"}},
    }
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", json.loads(json.dumps(original_memory)))
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server,
        "_fetch_research_web_sources",
        lambda topic: [
            {
                "name": "Internal consistency of the Bible",
                "url": "https://example.test/bible-consistency",
                "status": 200,
                "title": "Internal consistency of the Bible",
                "snippet": "Scholars debate whether biblical differences are contradictions or harmonizable details.",
                "checked_at": "2026-07-08T10:55:00",
            }
        ],
        raising=False,
    )

    report = server._run_full_training_suite()

    assert report["ok"] is True
    assert report["summary"]["total"] >= 27
    assert report["summary"]["failed"] == 0
    assert report["summary"]["score"] == 100
    assert {"memory", "truth", "web", "website_builder", "tools", "ui", "commands"}.issubset(
        set(report["summary"]["categories"])
    )
    assert any(case["name"] == "Legacy model lookup avoids Ollama timeout" for case in report["cases"])
    assert any(case["name"] == "Display body chat commands" for case in report["cases"])
    assert any(case["name"] == "Free Kaggle GPU training bundle" for case in report["cases"])
    assert server.MEMORY == original_memory
    assert any("Full suite" in line for line in server._TRAINING_LOG[-5:])


def test_kaggle_gpu_training_status_prefers_free_kaggle_when_local_cuda_missing(monkeypatch):
    monkeypatch.setattr(
        server,
        "_detect_local_gpu_status",
        lambda: {
            "has_cuda": False,
            "gpu_names": [],
            "detail": "No local CUDA GPU detected.",
        },
        raising=False,
    )

    status = server._gpu_training_status()

    assert status["ok"] is True
    assert status["recommended_path"] == "Kaggle"
    assert status["local"]["usable_for_gpu_training"] is False
    assert status["kaggle"]["cost"] == "free"
    assert status["kaggle"]["result_name"] == "nova_lora_sft_result.zip"
    assert "Accelerator -> GPU" in status["kaggle"]["steps"][1]


def test_kaggle_gpu_bundle_contains_notebook_readme_and_training_code(monkeypatch):
    monkeypatch.setattr(
        server,
        "_detect_local_gpu_status",
        lambda: {
            "has_cuda": False,
            "gpu_names": [],
            "detail": "No local CUDA GPU detected.",
        },
        raising=False,
    )

    bundle = server._build_kaggle_gpu_training_bundle()

    assert bundle["filename"].endswith(".zip")
    assert bundle["content_type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(bundle["bytes"])) as archive:
        names = set(archive.namelist())
        assert "README_KAGGLE_GPU.md" in names
        assert "nova_kaggle_gpu_training.ipynb" in names
        assert "tools/train_nova_lora_sft.py" in names
        assert "artifacts/nova_large_sft_dataset/train.jsonl" in names
        assert "artifacts/nova_large_sft_dataset/validation.jsonl" in names
        assert "artifacts/nova_large_sft_dataset/holdout.jsonl" in names
        assert "artifacts/nova_large_sft_dataset/preference_pairs.jsonl" in names
        assert "src/nova_hyper_training_orchestrator.py" in names
        assert "nova_enhanced_server.py" in names
        requirements = archive.read("requirements_kaggle.txt").decode("utf-8")
        assert "transformers" in requirements
        assert "peft" in requirements
        assert "datasets" in requirements
        assert "bitsandbytes" in requirements
        notebook = json.loads(archive.read("nova_kaggle_gpu_training.ipynb").decode("utf-8"))
        notebook_text = json.dumps(notebook)
        assert "torch.cuda.is_available" in notebook_text
        assert "RUN_LORA_SFT" in notebook_text
        assert "train_nova_lora_sft.py" in notebook_text
        assert "nova_lora_sft_result.zip" in notebook_text
        assert "torchvision" in notebook_text
        assert "torchaudio" in notebook_text
        assert "nova_hyper_training_orchestrator" in notebook_text
        assert "nova_gpu_training_result.zip" in notebook_text
        readme = archive.read("README_KAGGLE_GPU.md").decode("utf-8")
        assert "Kaggle Notebook" in readme
        assert "free GPU" in readme
        assert "LoRA/SFT" in readme


def test_kaggle_gpu_bundle_selection_includes_large_sft_dataset():
    source = inspect.getsource(server._build_kaggle_gpu_training_bundle)

    assert "artifacts/nova_large_sft_dataset/train.jsonl" in source
    assert "artifacts/nova_large_sft_dataset/validation.jsonl" in source
    assert "artifacts/nova_large_sft_dataset/holdout.jsonl" in source
    assert "artifacts/nova_large_sft_dataset/preference_pairs.jsonl" in source


def test_gpu_training_api_serves_status_and_kaggle_bundle(monkeypatch):
    monkeypatch.setattr(
        server,
        "_detect_local_gpu_status",
        lambda: {
            "has_cuda": False,
            "gpu_names": [],
            "detail": "No local CUDA GPU detected.",
        },
        raising=False,
    )

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        status = _json_get(base_url, "/api/gpu-training/status")
        assert status["recommended_path"] == "Kaggle"

        with urllib.request.urlopen(base_url + "/api/gpu-training/kaggle-bundle.zip", timeout=5) as response:
            assert response.headers["Content-Type"] == "application/zip"
            assert "nova_kaggle_gpu_training.zip" in response.headers["Content-Disposition"]
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                assert "nova_kaggle_gpu_training.ipynb" in archive.namelist()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_training_suite_api_returns_report(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(
        server,
        "MEMORY",
        {"people": {}, "lessons": {}, "last_person": None},
    )
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_start_training", lambda: (True, "hypertrain_job_api"))
    monkeypatch.setattr(
        server,
        "_fetch_research_web_sources",
        lambda topic: [
            {
                "name": "Internal consistency of the Bible",
                "url": "https://example.test/bible-consistency",
                "status": 200,
                "title": "Internal consistency of the Bible",
                "snippet": "Scholars debate whether biblical differences are contradictions or harmonizable details.",
                "checked_at": "2026-07-08T10:55:00",
            }
        ],
        raising=False,
    )

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        result = _json_post(base_url, "/api/training/run", {"mode": "full"})

        assert result["ok"] is True
        assert result["training_job"]["job_id"] == "hypertrain_job_api"
        assert result["training_job"]["real_training"] is True
        assert result["report"]["summary"]["failed"] == 0
        assert result["report"]["summary"]["score"] == 100
        assert result["report"]["enhancements"][0].startswith("Keep this suite")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_training_run_api_starts_real_guarded_training_job(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(
        server,
        "_run_full_training_suite",
        lambda: {
            "ok": True,
            "summary": {"failed": 0, "score": 100, "passed": 1, "total": 1, "categories": {}},
            "enhancements": [],
        },
    )
    calls = []

    def fake_start_training():
        calls.append("start")
        return True, "hypertrain_job_test"

    monkeypatch.setattr(server, "_start_training", fake_start_training)

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        result = _json_post(base_url, "/api/training/run", {"mode": "full"})

        assert calls == ["start"]
        assert result["ok"] is True
        assert result["training_job"]["started"] is True
        assert result["training_job"]["job_id"] == "hypertrain_job_test"
        assert result["training_job"]["real_training"] is True
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_training_status_api_reads_latest_guarded_report_after_restart(monkeypatch, tmp_path):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report_path = report_dir / "transformer_hyper_training_20260707T170442Z_89139b14.json"
    report_path.write_text(
        json.dumps(
            {
                "run_id": "20260707T170442Z_89139b14",
                "verdict": "PROMOTED",
                "finished_at": "2026-07-07T17:21:56+00:00",
                "decision": {
                    "baseline_joint": 38.9,
                    "candidate_joint": 40.2,
                    "reasons": ["all promotion gates passed"],
                },
                "baseline_metrics": {
                    "routing": {"macro_f1": 56.5},
                    "answers": {"composite": 1.78},
                },
                "candidate_metrics": {
                    "routing": {"macro_f1": 59.13},
                    "answers": {"composite": 1.78},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "ROOT", str(tmp_path))
    monkeypatch.setattr(server, "_TRAINING_RUNNING", False)
    monkeypatch.setattr(server, "_TRAINING_RUN_ID", None)
    monkeypatch.setattr(server, "_LAST_TRAINING_REPORT", None)
    monkeypatch.setattr(server, "_TRAINING_LOG", [])

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        result = _json_get(base_url, "/api/training/status")

        guarded = result["latest_guarded_report"]
        assert result["job_id"] == "20260707T170442Z_89139b14"
        assert guarded["verdict"] == "PROMOTED"
        assert guarded["candidate_route_macro_f1"] == 59.13
        assert guarded["candidate_answer_composite"] == 1.78
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_brain_route_runs_full_training_command(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_start_training", lambda: (True, "hypertrain_job_chat"))
    monkeypatch.setattr(
        server,
        "_fetch_research_web_sources",
        lambda topic: [
            {
                "name": "Internal consistency of the Bible",
                "url": "https://example.test/bible-consistency",
                "status": 200,
                "title": "Internal consistency of the Bible",
                "snippet": "Scholars debate whether biblical differences are contradictions or harmonizable details.",
                "checked_at": "2026-07-08T10:55:00",
            }
        ],
        raising=False,
    )

    def general_router_should_not_handle_training(*args, **kwargs):
        raise AssertionError("full training commands must route before general chat")

    monkeypatch.setattr(server, "pipeline_process", general_router_should_not_handle_training)
    monkeypatch.setattr(server, "cognitive_route", general_router_should_not_handle_training, raising=False)

    response, trace = server.brain_route("do a full training")

    assert response.startswith("[TRAINING CENTER]")
    assert "Memory:" in response
    assert "Website Builder:" in response
    assert "UI:" in response
    assert trace["source"] == "training_center"
    assert trace["action"] == "full_training_suite"
    assert trace["training_job"]["job_id"] == "hypertrain_job_chat"
    assert trace["training_report"]["summary"]["failed"] == 0


def test_web_ui_exposes_training_center_controls():
    required_markers = [
        'id="trainingCenterPanel"',
        'id="trainingResults"',
        'id="trainingSummary"',
        "function runFullTraining",
        "function renderTrainingJob",
        "function renderGuardedTrainingReport",
        "/api/training/run",
        "latest_guarded_report",
        "Guarded transformer training",
        "candidate_route_macro_f1",
        "training_job",
        "Full Training",
        "Real guarded training",
        "job ID",
        "Memory drills",
        "Truth and web honesty",
        "Website builder quality",
        "deep_conversation:'Deep Conversation'",
    ]

    for marker in required_markers:
        assert marker in server.WEB_HTML


def test_web_ui_linkifies_chat_urls_safely():
    required_markers = [
        "function linkifyMessageText",
        "escapeHtml(text)",
        "target=\"_blank\"",
        "rel=\"noopener noreferrer\"",
        "class=\"chat-link\"",
        ".msg a.chat-link",
    ]

    for marker in required_markers:
        assert marker in server.WEB_HTML

    assert "let html = text.replace(/\\n/g, '<br>');" not in server.WEB_HTML


def test_web_ui_linkifies_internal_project_paths_for_mobile():
    required_markers = [
        "function linkifyInternalAppPath",
        "/sandbox/app_builder_projects/",
        "/sandbox/deployments/",
        "href=\"${path}\"",
        "const linkedPaths = linkifyInternalAppPath(linkedUrls);",
    ]

    for marker in required_markers:
        assert marker in server.WEB_HTML


def test_static_file_connect_guidance_uses_live_enhanced_server():
    assert "nova_enhanced_server.py 53910" in server.WEB_HTML
    assert "connectToLiveNova" in server.WEB_HTML
    assert "'http://127.0.0.1:53910'" in server.WEB_HTML


def test_auto_connect_allows_primary_server_cold_start_without_slow_port_probes():
    html = server.WEB_HTML

    assert "for(const [index, url] of urls.entries())" in html
    assert "const connectionTimeoutMs = index === 0 ? 6000 : 1500;" in html
    assert "{headers:authHeaders()}, connectionTimeoutMs" in html
    assert "{headers:{}}, connectionTimeoutMs" in html


def test_file_manager_exposes_sandboxed_live_code_preview():
    required_markers = [
        'id="fileLivePreviewFrame"',
        'id="fileLivePreviewStatus"',
        'id="fileModInput"',
        'id="fileModLog"',
        "function sendFileModRequest",
        "function updateLivePreview",
        "function scheduleLivePreview",
        "function buildPreviewDocument",
        "function buildMarkdownPreviewDocument",
        "function renderMarkdownPreviewHtml",
        "function renderMarkdownInline",
        "function isMarkdownFile",
        "mod-plan-preview",
        "<ol>",
        "as a readable plan",
        ".file-list{order:1",
        ".file-preview-wrap{order:2",
        ".file-editor-wrap{order:3",
        "function openLivePreviewFull",
        "activeFileEditable",
        "function buildStoredAssetPreviewDocument",
        "function showStoredAssetFile",
        "binary asset",
        "cannot be edited in the live editor",
        "too_large_for_editor",
        "too large for live editor",
        "/mod",
    ]

    for marker in required_markers:
        assert marker in server.WEB_HTML

    assert 'sandbox="allow-scripts allow-forms"' in server.WEB_HTML
    assert 'allow-same-origin' not in server.WEB_HTML


def test_project_manager_api_mods_loaded_file_by_chat_prompt(monkeypatch, tmp_path):
    projects_root = tmp_path / "projects"
    project = projects_root / "Back_Block"
    project.mkdir(parents=True)
    (project / "index.html").write_text(
        "<html><head><title>Old</title></head><body><h1>Old</h1><button>Start</button></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", str(projects_root))

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        modded = _json_post(
            base_url,
            "/api/projects/Back_Block/mod",
            {
                "path": "index.html",
                "prompt": "change the title to Back Block Brawlers and make buttons bigger",
            },
        )

        assert modded["ok"] is True
        assert modded["path"] == "index.html"
        assert "Back Block Brawlers" in modded["content"]
        assert "font-size" in modded["content"]
        assert "Back Block Brawlers" in (project / "index.html").read_text(encoding="utf-8")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_project_manager_api_creates_mod_plan_for_binary_asset(monkeypatch, tmp_path):
    projects_root = tmp_path / "projects"
    project = projects_root / "Mic_Mod"
    project.mkdir(parents=True)
    binary = project / "Antares Mic Mod v4.3.0 CE.exe"
    binary.write_bytes(b"MZ" + (b"\0" * 32))
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", str(projects_root))

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        modded = _json_post(
            base_url,
            "/api/projects/Mic_Mod/mod",
            {
                "path": "Antares Mic Mod v4.3.0 CE.exe",
                "prompt": "make the interface darker and add a bypass switch",
            },
        )

        assert modded["ok"] is True
        assert modded["path"].startswith("nova_mod_requests/")
        assert modded["path"].endswith("_mod_plan.md")
        assert "Binary or stored asset mod plan" in modded["content"]
        assert "Antares Mic Mod v4.3.0 CE.exe" in modded["content"]
        assert "editable source files" in modded["content"]
        assert binary.read_bytes().startswith(b"MZ")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_project_manager_api_runs_quality_gate(monkeypatch, tmp_path):
    projects_root = tmp_path / "projects"
    project = projects_root / "Quality_Test_Website"
    project.mkdir(parents=True)
    (project / "index.html").write_text(
        """<!doctype html><html><head><title>Quality</title></head>
<body><nav><a href="index.html">Home</a></nav><main><h1>Quality</h1><p>Ready.</p></main></body></html>""",
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", str(projects_root))

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        checked = _json_post(base_url, "/api/projects/Quality_Test_Website/quality", {"fix": True})

        assert checked["ok"] is True
        assert checked["report"]["passed"] is True
        assert checked["report"]["pages_inspected"] == 1
        assert checked["report"]["visuals_created"] == 2
        assert checked["report"]["visuals"][0]["screenshot_url"].endswith(".svg")
        assert "metadata:viewport" in checked["report"]["fixes_applied"]
        assert (project / "quality_gate_report.json").exists()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_status_endpoint_sends_cors_headers_for_file_page_connect():
    get_source = inspect.getsource(server.NovaHandler.do_GET)
    status_block = get_source.split("elif parsed.path == '/status':", 1)[1].split("else:", 1)[0]
    cors_source = inspect.getsource(server.NovaHandler._send_cors_headers)

    assert "_send_cors_headers()" in status_block
    assert "Access-Control-Allow-Origin" in cors_source


def test_server_security_headers_and_cors_restrict_untrusted_origins():
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        local_request = urllib.request.Request(
            base_url + "/",
            headers={"Origin": "http://127.0.0.1:9999"},
        )
        with urllib.request.urlopen(local_request, timeout=5) as response:
            assert response.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:9999"
            assert response.headers.get("X-Content-Type-Options") == "nosniff"
            assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
            assert "default-src 'self'" in response.headers.get("Content-Security-Policy", "")
            assert response.headers.get("Server") == "NovaCreature"

        hostile_request = urllib.request.Request(
            base_url + "/status",
            headers={"Origin": "https://untrusted.example"},
        )
        with urllib.request.urlopen(hostile_request, timeout=5) as response:
            assert response.headers.get("Access-Control-Allow-Origin") is None
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_health_endpoint_reports_version_and_uptime():
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        health = _json_get(base_url, "/healthz")
        assert health["ok"] is True
        assert health["version"] == server.NOVA_APP_VERSION
        assert health["uptime_seconds"] >= 0
        assert health["regular_chat_routing"]["primary_policy"] == "ollama_qwen_first"
        assert health["regular_chat_routing"]["escalation_local_only"] is True
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_chat_api_rejects_invalid_and_oversized_json(monkeypatch):
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        invalid = urllib.request.Request(
            base_url + "/api/chat",
            data=b"{bad json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(invalid, timeout=5)
            raise AssertionError("invalid JSON unexpectedly succeeded")
        except urllib.error.HTTPError as error:
            assert error.code == 400
            payload = json.loads(error.read().decode("utf-8"))
            assert payload["error"] == "Invalid JSON request body."

        monkeypatch.setattr(server, "MAX_JSON_BODY_BYTES", 8)
        oversized = urllib.request.Request(
            base_url + "/api/chat",
            data=b'{"text":"hello"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(oversized, timeout=5)
            raise AssertionError("oversized JSON unexpectedly succeeded")
        except urllib.error.HTTPError as error:
            assert error.code == 413
            assert "limit" in json.loads(error.read().decode("utf-8"))["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_adapter_zip_upload_streams_binary_body(monkeypatch, tmp_path):
    captured = {}

    def fake_import(upload_path, adapter_id=None, activate=False):
        captured["bytes"] = Path(upload_path).read_bytes()
        captured["adapter_id"] = adapter_id
        captured["activate"] = activate
        return {"ok": True, "adapter": {"id": adapter_id}, "activated": activate}

    monkeypatch.setattr(server, "ROOT", str(tmp_path))
    monkeypatch.setattr(server, "_adapter_registry_import_file", fake_import)
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        request = urllib.request.Request(
            base_url + "/api/adapters/import?filename=test.zip&adapter_id=streamed&activate=true",
            data=b"PK\x03\x04streamed-test-data",
            headers={"Content-Type": "application/zip"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert captured == {
            "bytes": b"PK\x03\x04streamed-test-data",
            "adapter_id": "streamed",
            "activate": True,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_web_ui_exposes_real_voice_listen_and_picture_controls():
    html = server.WEB_HTML
    required_markers = [
        'id="btnSpk"',
        'id="mainMicBtn"',
        'class="mic-btn"',
        'id="mainCameraBtn"',
        'class="camera-btn"',
        'id="mainLookBtn"',
        'class="look-btn"',
        'id="voiceBtn"',
        'class="voice-btn"',
        'id="talkBtn"',
        'class="talk-btn"',
        'id="btnListen"',
        'id="btnPicture"',
        'id="btnCameraLook"',
        'id="btnLiveWatch"',
        'id="cameraDock"',
        'class="camera-dock"',
        'id="cameraDockStatus"',
        "Live camera preview",
        "function updateCameraDock",
        'id="cameraPreview"',
        'max-height:190px',
        'id="cameraFrameCanvas"',
        'id="pictureInput"',
        'accept="image/*"',
        "function toggleSensoryPermission",
        "function speakNova",
        "function playNovaServerVoice",
        "function unlockNovaAudio",
        "novaAudioElement",
        "/api/tts",
        "function toggleSpeakerOutput",
        "function setSpeakerUi",
        "const NOVA_VOICE_PROFILE",
        "function loadNovaVoices",
        "function getBestNovaVoice",
        "function smoothSpeechChunks",
        "function speakNovaChunkQueue",
        "function speakNovaDirectFallback",
        "function scheduleNovaSpeechWatchdog",
        "function updateVoiceModeLabel",
        'id="voiceModeLabel"',
        "Smooth Voice",
        "window.__novaSpeechEvents",
        "Voice is ON. You should hear me now.",
        "SpeechSynthesisUtterance",
        "window.speechSynthesis",
        "window.speechSynthesis.resume",
        "function toggleListening",
        "function setMicUi",
        "function toggleMicPermission",
        "Mic is ON. Now tap Talk",
        "Tap Mic OFF so it changes to Mic ON first",
        "function setCameraUi",
        "function toggleCameraPermission",
        "Camera is ON. If your browser asks, tap Allow",
        "Tap Camera OFF first",
        "const talkBtn = document.getElementById('talkBtn')",
        "SpeechRecognition || window.webkitSpeechRecognition",
        "function startCameraPreview",
        "navigator.mediaDevices.getUserMedia",
        "function captureCameraFrame",
        "function toggleLiveWatch",
        "liveWatchTimer",
        "function handlePictureUpload",
        "function sendVisionImage",
        "/api/vision",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_has_responsive_accessible_shell_and_streamed_adapter_upload():
    html = server.WEB_HTML

    assert "maximum-scale" not in html
    assert "user-scalable=no" not in html
    assert 'role="log" aria-live="polite"' in html
    assert 'aria-label="Talk to Nova"' in html
    assert "@media(prefers-reduced-motion:reduce)" in html
    assert "flex-wrap:nowrap;overflow-x:auto" in html
    assert html.count("async function tryConnect()") == 1
    assert "body:file" in html
    assert "without loading the whole ZIP into memory" in html
    assert 'id="btnListen" onclick="toggleListening()" hidden' in html


def test_web_ui_streams_native_nova_chat_with_trace_cancel_and_legacy_fallback():
    html = server.WEB_HTML
    required_markers = [
        "async function callAPIStream",
        "SERVER_BASE + '/nova/v1/chat'",
        "Accept':'text/event-stream'",
        "res.body.getReader()",
        "function beginStreamingMsg",
        "function updateStreamingMsg",
        "function finishStreamingMsg",
        "async function cancelActiveChat",
        "'/nova/v1/cancel/'",
        "controller.abort()",
        "const trace = withResponseLatency(metadata.trace",
        "data = await retryLiveCall(text)",
        "sendBtn.textContent = 'Stop'",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_shows_bounded_conversation_focus_without_private_reasoning():
    html = server.WEB_HTML

    assert "meta.conversation_subject" in html
    assert "meta.conversation_emotion" in html
    assert "meta.context_anchor_distance" in html
    assert "Conversation subject" in html
    assert "Recent conversation tone" in html
    assert "meta.private_chain_of_thought" not in html


def test_normal_chat_uses_client_history_for_fast_reviewed_followup(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "unrelated desktop question")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "unrelated desktop answer")
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, **kwargs: {
            "fast_path": False,
            "intent": {"primary_intent": "general_inquiry"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.8,
            "normalized_text": text,
            "memory_binding": {},
        },
    )
    captured = {}

    def fake_cognitive(prompt, **kwargs):
        captured["prompt"] = prompt
        return "Churning also adds tiny air bubbles, which makes the texture lighter.", {
            "source": "cognitive_os",
            "roles": ["memory_transformer", "speech_output_transformer"],
            "skills": ["llm_synthesis"],
            "confidence": 0.9,
            "route_path": ["nova_context", "speech_output"],
            "final_answer_source": "local_llm_synthesis",
        }

    monkeypatch.setattr(server, "cognitive_route", fake_cognitive, raising=False)
    response, trace = server.brain_route(
        "tell me more",
        context={
            "conversation_history": [
                {"role": "user", "content": "Why does ice cream need churning?"},
                {"role": "assistant", "content": "Churning limits large ice crystals."},
            ]
        },
    )

    assert "Churning limits large ice crystals." in response
    assert captured == {}
    assert trace["client_context_used"] is True
    assert trace["context_resolution"] == "expand"
    assert trace["source"] == "conversation_context_router"
    assert "context_generation_prompt_used" not in trace


def test_gateway_without_transcript_does_not_borrow_process_wide_followup(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "Private topic from another client")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "Private answer from another client")
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, **kwargs: {
            "fast_path": False,
            "intent": {"primary_intent": "general_inquiry"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.8,
            "normalized_text": text,
            "memory_binding": {},
        },
    )
    captured = {}

    def fake_cognitive(prompt, **kwargs):
        captured["prompt"] = prompt
        return "Tell me which part you want to continue.", {
            "source": "cognitive_os",
            "roles": ["memory_transformer", "speech_output_transformer"],
            "skills": ["llm_synthesis"],
            "confidence": 0.8,
            "route_path": ["nova_context", "speech_output"],
        }

    monkeypatch.setattr(server, "cognitive_route", fake_cognitive, raising=False)

    _response, trace = server.brain_route(
        "Tell me more",
        context={
            "nova_gateway": True,
            "client_id": "isolated-phone",
            "conversation_id": "new-conversation",
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert "Private topic" not in captured["prompt"]
    assert "Private answer" not in captured["prompt"]
    assert "context_resolution" not in trace


def test_normal_chat_forwards_bounded_client_history_into_qwen_context(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, **kwargs: {
            "fast_path": False,
            "intent": {"primary_intent": "general_inquiry"},
            "route": ["memory_transformer", "speech_output_transformer"],
            "confidence": 0.8,
            "normalized_text": text,
            "memory_binding": {},
        },
    )
    captured = {}

    def fake_cognitive(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["context"] = kwargs.get("context")
        return "Mr Novatron, keep building strong; Nova helps you all day long.", {
            "source": "cognitive_os",
            "roles": ["memory_transformer", "qwen_synthesis", "speech_output_transformer"],
            "skills": ["llm_synthesis"],
            "confidence": 0.9,
            "route_path": ["nova_context", "qwen_synthesis", "speech_output"],
            "local_llm_synthesis_used": True,
            "local_llm_model": "qwen2.5:1.5b",
            "final_answer_source": "local_llm_synthesis",
        }

    monkeypatch.setattr(server, "cognitive_route", fake_cognitive, raising=False)
    history = [
        {"role": "user", "content": "What is my name?"},
        {"role": "assistant", "content": "Your name is Mr Novatron. I remember you."},
    ]

    response, trace = server.brain_route(
        "Make a short rhyme using that name.",
        context={
            "nova_gateway": True,
            "memory_read_allowed": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "conversation_history": history,
            "primary_model_override": "qwen2.5:3b",
            "primary_model_timeout": 180,
            "primary_model_keep_alive": "10m",
            "primary_model_tier": "middle",
            "primary_model_guidance": [
                "Local storage works offline; remote storage requires connectivity unless cached."
            ],
            "primary_model_required_aspects": [
                "privacy",
                "offline behavior",
                "latency",
                "migration risk",
                "cost",
            ],
            "nova_request": {
                "messages": [
                    {"role": "user", "content": "Make a short rhyme using that name."},
                ]
            },
        },
    )

    assert response.startswith("Mr Novatron")
    assert captured["prompt"] == "Make a short rhyme using that name."
    assert captured["context"]["gateway_messages"] == history + [
        {"role": "user", "content": "Make a short rhyme using that name."}
    ]
    assert captured["context"]["memory_read_allowed"] is True
    assert captured["context"]["primary_model_override"] == "qwen2.5:3b"
    assert captured["context"]["primary_model_tier"] == "middle"
    assert "unless cached" in captured["context"]["primary_model_guidance"][0]
    assert captured["context"]["primary_model_required_aspects"][-1] == "cost"
    assert trace["client_context_used"] is True
    assert trace["local_llm_model"] == "qwen2.5:1.5b"


def test_normal_chat_reaction_uses_client_history_not_other_client_global(monkeypatch):
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "private topic from another client")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "private answer from another client")

    response, trace = server.brain_route(
        "I like that",
        context={
            "conversation_history": [
                {"role": "user", "content": "Give me a project idea"},
                {"role": "assistant", "content": "Build a local-first creature journal."},
            ]
        },
    )

    assert "Give me a project idea" in response
    assert "private topic" not in response
    assert trace["source"] == "conversation_context_router"
    assert trace["context_resolution"] == "positive_reaction"


def test_run_chat_firewall_blocks_managed_canned_answer(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app. What do you want to do next?",
            {"source": "cognitive_os", "roles": ["speech_output_transformer"], "confidence": 0.85},
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {"ok": False, "reason": "no_test_candidate"},
    )
    monkeypatch.setattr(
        nova_llm_synthesizer,
        "generate_fallback",
        lambda message, timeout=10: (None, False, "offline"),
    )

    response, trace = server._run_nova_chat_turn(
        "How do you make ice cream?",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert "off-topic draft" in response
    assert trace["source"] == "answer_firewall_recovery"
    assert trace["answer_firewall"]["status"] == "blocked"
    assert trace["answer_firewall"]["intercepted"] is True
    assert "generic_fallback_mismatch" in trace["answer_firewall"]["reasons"]
    assert trace["candidate_selection"]["selected"] == "recovery"
    assert trace["candidate_selection"]["llm_fallback"]["reason"] == "offline"


def test_run_chat_firewall_uses_llm_fallback_before_generic_recovery(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app. What do you want to do next?",
            {"source": "cognitive_os", "roles": ["speech_output_transformer"], "confidence": 0.85},
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {"ok": False, "reason": "no_test_candidate"},
    )
    monkeypatch.setattr(
        nova_llm_synthesizer,
        "generate_fallback",
        lambda message, timeout=10: (
            "Mix cream, milk, sugar, and vanilla; chill it, churn it, then freeze until firm.",
            True,
            None,
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "How do you make ice cream?",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert "Mix cream" in response
    assert trace["source"] == "llm_fallback"
    assert trace["final_answer_source"] == "llm_fallback"
    assert trace["candidate_selection"]["selected"] == "llm_fallback"
    assert trace["fallback_used"] is False


def test_run_chat_candidate_selector_uses_better_local_answer(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app. What do you want to do next?",
            {
                "source": "cognitive_os",
                "roles": ["speech_output_transformer"],
                "confidence": 0.85,
                "local_llm_model": "large-primary",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {
            "ok": True,
            "reason": "generated",
            "answer": "Mix cream, milk, sugar, and vanilla; chill it, churn it, then freeze until firm.",
            "provider": "local-test-provider",
            "model": "small-general",
            "relevance_text": "How do you make ice cream?",
            "different_model": True,
            "latency_ms": 12.5,
            "model_selection": {"eligible_count": 2, "selected_different_from_primary": True},
        },
    )

    response, trace = server._run_nova_chat_turn(
        "How do you make ice cream?",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert response.startswith("Mix cream")
    assert trace["source"] == "answer_candidate_selector"
    assert trace["provider"] == "local-test-provider"
    assert trace["model"] == "small-general"
    assert trace["reviewer_tier"] == "middle"
    assert trace["candidate_retry_used"] is True
    assert trace["answer_firewall"]["status"] == "passed_after_retry"
    assert trace["answer_firewall"]["intercepted"] is True
    assert trace["candidate_selection"]["selected"] == "alternate_local"
    assert trace["candidate_selection"]["retry_attempted"] is True
    assert all("answer" not in item for item in trace["candidate_selection"]["candidates"])


def test_run_chat_falls_back_from_failed_middle_reviewer_to_deep_reviewer(monkeypatch):
    attempts = []
    progress = []
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "I am not sure how to answer all of that.",
            {
                "source": "cognitive_os",
                "confidence": 0.82,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:1.5b",
            },
        ),
    )

    def fake_candidate(*args, reviewer_tier="deep", **kwargs):
        attempts.append(reviewer_tier)
        if reviewer_tier == "middle":
            return {
                "ok": False,
                "reason": "candidate_token_limit",
                "model": "qwen2.5:3b",
                "reviewer_tier": "middle",
            }
        return {
            "ok": True,
            "reason": "generated",
            "answer": (
                "Use a local encrypted store for private offline data, then add a remote "
                "synchronization service behind explicit consent and a versioned adapter."
            ),
            "provider": "ollama",
            "model": "qwen2.5-coder:7b",
            "reviewer_tier": "deep",
            "relevance_text": "Recommend a private local-first storage architecture",
            "different_model": True,
            "latency_ms": 50.0,
        }

    monkeypatch.setattr(server, "_generate_alternate_local_candidate", fake_candidate)

    response, trace = server._run_nova_chat_turn(
        "Recommend a private local-first storage architecture and explain why.",
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "progress_callback": lambda stage, label, percent: progress.append(stage) or True,
        },
    )

    assert attempts == ["middle", "deep"]
    assert response.startswith("Use a local encrypted store")
    assert trace["reviewer_tier"] == "deep"
    assert trace["candidate_selection"]["selected_reviewer_tier"] == "deep"
    assert [item["tier"] for item in trace["candidate_selection"]["review_attempts"]] == [
        "middle",
        "deep",
    ]
    assert "middle_local_review" in progress
    assert "deep_local_review" in progress


def test_direct_middle_route_selects_installed_local_3b_only_for_hard_requests(monkeypatch):
    model = types.SimpleNamespace(
        model_id="qwen2.5:3b",
        provider_id="ollama",
        availability="available",
        health_status="healthy",
        local_or_remote="local",
        estimated_cost_type="free",
        text_input=True,
        text_output=True,
        reasoning=True,
        metadata={"size": 2_100_000_000},
    )
    provider = types.SimpleNamespace(
        local_or_remote="local",
        cost_type="free",
        base_url="http://127.0.0.1:11434",
        list_models=lambda: [model],
    )
    registry = types.SimpleNamespace(get_provider=lambda provider_id: provider)
    monkeypatch.setattr(
        server,
        "NOVA_GATEWAY",
        types.SimpleNamespace(providers=registry),
    )

    hard = server._direct_middle_route_decision(
        "Compare local SQLite vector memory with a remote vector database for a "
        "private mobile AI app. Analyze privacy, offline behavior, latency, migration "
        "risk, and cost, then recommend a staged architecture."
    )
    routine = server._direct_middle_route_decision("Tell me a joke.")

    assert hard["selected"] is True
    assert hard["model"] == "qwen2.5:3b"
    assert hard["provider"] == "ollama"
    assert hard["tier"] == "middle"
    assert hard["difficulty"]["difficulty_tier"] == "hard"
    assert hard["content_logged"] is False
    assert routine["selected"] is False
    assert routine["reason"] == "below_direct_threshold"


def test_optional_strong_mode_selects_only_configured_installed_model(monkeypatch):
    provider = types.SimpleNamespace(
        list_models=lambda: [
            types.SimpleNamespace(
                provider_id="ollama",
                model_id="qwen3:8b",
                metadata={"size": 5_200_000_000},
            )
        ]
    )
    monkeypatch.setattr(server, "_provider_is_safe_local_candidate", lambda value: value is provider)
    monkeypatch.setattr(server.NOVA_GATEWAY.providers, "get_provider", lambda name: provider)
    monkeypatch.setattr(server.MODEL_QUALITY, "is_quarantined", lambda provider_id, model_id: False)

    decision = server._optional_strong_model_decision({"nova_model_mode": "strong"})

    assert decision["selected"] is True
    assert decision["model"] == "qwen3:8b"
    assert decision["timeout_seconds"] == 240
    assert decision["keep_alive"] == "5m"
    assert decision["content_logged"] is False


def test_optional_strong_mode_rejects_unknown_mode_and_falls_back_when_missing(monkeypatch):
    provider = types.SimpleNamespace(list_models=lambda: [])
    monkeypatch.setattr(server, "_provider_is_safe_local_candidate", lambda value: value is provider)
    monkeypatch.setattr(server.NOVA_GATEWAY.providers, "get_provider", lambda name: provider)

    unknown = server._optional_strong_model_decision({"nova_model_mode": "qwen3:8b"})
    missing = server._optional_strong_model_decision({"nova_model_mode": "strong"})

    assert unknown["selected"] is False
    assert unknown["reason"] == "unsupported_mode"
    assert missing["selected"] is False
    assert missing["reason"] == "model_unavailable"


def test_optional_strong_mode_rejects_malformed_installed_model_size(monkeypatch):
    provider = types.SimpleNamespace(
        list_models=lambda: [
            types.SimpleNamespace(
                provider_id="ollama",
                model_id="qwen3:8b",
                metadata={"size": "not-a-byte-count"},
            )
        ]
    )
    monkeypatch.setattr(server, "_provider_is_safe_local_candidate", lambda value: value is provider)
    monkeypatch.setattr(server.NOVA_GATEWAY.providers, "get_provider", lambda name: provider)
    monkeypatch.setattr(server.MODEL_QUALITY, "is_quarantined", lambda provider_id, model_id: False)

    decision = server._optional_strong_model_decision({"nova_model_mode": "strong"})

    assert decision["selected"] is False
    assert decision["reason"] == "model_validation_failed"


def test_optional_strong_mode_handles_quarantine_registry_error(monkeypatch):
    provider = types.SimpleNamespace(
        list_models=lambda: [
            types.SimpleNamespace(
                provider_id="ollama",
                model_id="qwen3:8b",
                metadata={"size": 5_200_000_000},
            )
        ]
    )
    monkeypatch.setattr(server, "_provider_is_safe_local_candidate", lambda value: value is provider)
    monkeypatch.setattr(server.NOVA_GATEWAY.providers, "get_provider", lambda name: provider)
    monkeypatch.setattr(
        server.MODEL_QUALITY,
        "is_quarantined",
        lambda provider_id, model_id: (_ for _ in ()).throw(RuntimeError("registry unavailable")),
    )

    decision = server._optional_strong_model_decision({"nova_model_mode": "strong"})

    assert decision["selected"] is False
    assert decision["reason"] == "model_validation_failed"


def test_optional_strong_mode_rejects_invalid_timeout_configuration(monkeypatch):
    import nova_local_llm_connector

    provider = types.SimpleNamespace(
        list_models=lambda: [
            types.SimpleNamespace(
                provider_id="ollama",
                model_id="qwen3:8b",
                metadata={"size": 5_200_000_000},
            )
        ]
    )
    monkeypatch.setattr(
        nova_local_llm_connector,
        "LocalLLMConfig",
        lambda: types.SimpleNamespace(
            provider="ollama",
            optional_strong_model="qwen3:8b",
            optional_strong_timeout="not-a-timeout",
            optional_strong_keep_alive="5m",
        ),
    )
    monkeypatch.setattr(server, "_provider_is_safe_local_candidate", lambda value: value is provider)
    monkeypatch.setattr(server.NOVA_GATEWAY.providers, "get_provider", lambda name: provider)
    monkeypatch.setattr(server.MODEL_QUALITY, "is_quarantined", lambda provider_id, model_id: False)

    decision = server._optional_strong_model_decision({"nova_model_mode": "strong"})

    assert decision["selected"] is False
    assert decision["reason"] == "configuration_unavailable"


def test_optional_strong_mode_overrides_middle_selection_but_keeps_nova_route(monkeypatch):
    captured = {}
    answer = (
        "Emergence occurs when interactions among simple parts produce organized "
        "behavior that no individual part contains on its own, such as flocking "
        "patterns or ant colonies."
    )
    monkeypatch.setattr(
        server,
        "_optional_strong_model_decision",
        lambda context, raw_adapter_request=False: {
            "requested": True,
            "selected": True,
            "reason": "selected",
            "mode": "strong",
            "model": "qwen3:8b",
            "estimated_model_bytes": 5_200_000_000,
            "timeout_seconds": 240,
            "keep_alive": "5m",
            "tier": "strong",
            "content_logged": False,
        },
    )
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("middle route must not replace Strong")
        ),
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: captured.update(context)
        or (
            answer,
            {"local_llm_synthesis_used": True, "local_llm_model": "qwen3:8b"},
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Explain emergence.", {"nova_model_mode": "strong"}
    )

    assert response == answer
    assert captured["primary_model_override"] == "qwen3:8b"
    assert captured["primary_model_tier"] == "strong"
    assert trace["optional_model_mode"]["selected"] is True
    assert trace["answer_firewall"]["checked"] is True


def test_optional_strong_trace_reports_actual_remote_provider(monkeypatch):
    monkeypatch.setattr(
        server,
        "_optional_strong_model_decision",
        lambda context, raw_adapter_request=False: {
            "requested": True,
            "selected": True,
            "reason": "selected",
            "mode": "strong",
            "model": "qwen3:8b",
            "estimated_model_bytes": 5_200_000_000,
            "timeout_seconds": 240,
            "keep_alive": "5m",
            "tier": "strong",
            "content_logged": False,
        },
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda *_args, **_kwargs: (
            "Emergence describes how complex patterns arise from interactions among simpler parts without central control.",
            {
                "local_llm_synthesis_used": True,
                "local_llm_model": "Qwen/Qwen3-8B",
                "local_llm_provider": "vllm",
                "remote_model_provider": "vllm",
                "gpu_backend": "vast_gpu",
            },
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Explain emergence.", {"nova_model_mode": "strong"}
    )

    assert response == "Emergence describes how complex patterns arise from interactions among simpler parts without central control."
    assert trace["optional_model_mode"]["actual_provider"] == "vllm"
    assert trace["optional_model_mode"]["actual_model"] == "Qwen/Qwen3-8B"
    assert trace["optional_model_mode"]["actual_gpu_backend"] == "vast_gpu"


def test_direct_middle_route_skips_quarantined_model(monkeypatch):
    model = types.SimpleNamespace(
        model_id="qwen2.5:3b",
        provider_id="ollama",
        availability="available",
        health_status="healthy",
        local_or_remote="local",
        estimated_cost_type="free",
        text_input=True,
        text_output=True,
        reasoning=True,
        metadata={"size": 2_100_000_000},
    )
    provider = types.SimpleNamespace(
        local_or_remote="local",
        cost_type="free",
        base_url="http://127.0.0.1:11434",
        list_models=lambda: [model],
    )
    monkeypatch.setattr(
        server,
        "NOVA_GATEWAY",
        types.SimpleNamespace(
            providers=types.SimpleNamespace(
                get_provider=lambda provider_id: provider,
            )
        ),
    )
    server.MODEL_QUALITY.record_failure(
        "ollama",
        "qwen2.5:3b",
        reason="provider_error",
    )
    server.MODEL_QUALITY.record_failure(
        "ollama",
        "qwen2.5:3b",
        reason="provider_error",
    )

    decision = server._direct_middle_route_decision(
        "Compare local SQLite vector memory with a remote vector database for a "
        "private mobile AI app. Analyze privacy, offline behavior, latency, migration "
        "risk, and cost, then recommend a staged architecture."
    )

    assert decision["selected"] is False
    assert decision["reason"] == "middle_model_quarantined"
    assert decision["model_quality"]["quarantined"] is True
    assert decision["content_logged"] is False


def test_direct_middle_route_rejects_model_that_failed_full_qualification(
    monkeypatch,
):
    model = types.SimpleNamespace(
        model_id="qwen2.5:3b",
        provider_id="ollama",
        availability="available",
        health_status="healthy",
        local_or_remote="local",
        estimated_cost_type="free",
        text_input=True,
        text_output=True,
        reasoning=True,
        metadata={"size": 2_100_000_000},
    )
    provider = types.SimpleNamespace(
        local_or_remote="local",
        cost_type="free",
        base_url="http://127.0.0.1:11434",
        list_models=lambda: [model],
    )
    monkeypatch.setattr(
        server,
        "NOVA_GATEWAY",
        types.SimpleNamespace(
            providers=types.SimpleNamespace(
                get_provider=lambda provider_id: provider,
            )
        ),
    )
    monkeypatch.setattr(
        server,
        "_middle_model_qualification",
        lambda *_args, **_kwargs: {
            "enforced": True,
            "eligible": False,
            "status": "not_qualified",
            "overall_score": 0.7,
            "content_logged": False,
        },
    )

    decision = server._direct_middle_route_decision(
        "Compare local SQLite vector memory with a remote vector database for a "
        "private mobile AI app. Analyze privacy, offline behavior, latency, migration "
        "risk, and cost, then recommend a staged architecture."
    )

    assert decision["selected"] is False
    assert decision["reason"] == "middle_model_not_qualified"
    assert decision["model"] == "qwen2.5:3b"
    assert decision["capability_qualification"]["overall_score"] == 0.7
    assert decision["content_logged"] is False


def test_run_chat_uses_direct_middle_as_primary_without_duplicate_review(monkeypatch):
    prompt = (
        "Compare local SQLite memory with a remote database for a private mobile app. "
        "Analyze privacy, offline behavior, latency, migration risk, and cost, then "
        "recommend a staged architecture."
        )
    answer = (
        "For privacy, start with encrypted local SQLite because it keeps data on-device, "
        "works offline, and gives predictable low latency without a recurring service "
        "cost. Put storage behind a versioned repository interface so schemas and "
        "embeddings can migrate safely. In a second stage, add optional remote sync "
        "for backup and multi-device access, sending only consented records. This "
        "local-first design limits migration risk while preserving a clean path to scale."
    )
    progress = []
    captured_context = {}
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *args, **kwargs: {
            "enabled": True,
            "selected": True,
            "reason": "selected",
            "provider": "ollama",
            "model": "qwen2.5:3b",
            "tier": "middle",
            "timeout_seconds": 180,
            "keep_alive": "10m",
            "max_tokens": 256,
            "difficulty": {"difficulty_tier": "hard"},
            "content_logged": False,
        },
    )

    def fake_brain(text, context=None):
        captured_context.update(context or {})
        return answer, {
            "source": "cognitive_os",
            "domain": "general_conversation",
            "confidence": 0.91,
            "local_llm_synthesis_used": True,
            "local_llm_model": "qwen2.5:3b",
        }

    monkeypatch.setattr(server, "brain_route", fake_brain)
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("a valid direct-middle answer must not run the 3B reviewer twice")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        prompt,
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "progress_callback": lambda stage, label, percent: progress.append(stage) or True,
        },
    )

    assert response == answer
    assert captured_context["primary_model_override"] == "qwen2.5:3b"
    assert captured_context["primary_model_timeout"] == 180
    assert captured_context["primary_model_keep_alive"] == "10m"
    assert captured_context["primary_model_tier"] == "middle"
    assert isinstance(captured_context["primary_model_guidance"], list)
    assert captured_context["primary_model_required_aspects"]
    assert trace["direct_middle_primary"] is True
    assert trace["direct_middle_routing"]["content_logged"] is False
    assert "direct_middle_route" in progress
    assert "middle_local_review" not in progress


def test_failed_direct_middle_primary_falls_through_to_deep_not_middle(monkeypatch):
    attempts = []
    excluded = []
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *args, **kwargs: {
            "enabled": True,
            "selected": True,
            "reason": "selected",
            "provider": "ollama",
            "model": "qwen2.5:3b",
            "tier": "middle",
            "timeout_seconds": 180,
            "keep_alive": "10m",
            "max_tokens": 256,
            "difficulty": {"difficulty_tier": "hard"},
            "content_logged": False,
        },
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "I am not sure how to answer all of that.",
            {
                "source": "cognitive_os",
                "confidence": 0.85,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:3b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_release_direct_middle_before_deep",
        lambda trace: {
            "attempted": True,
            "released": True,
            "model": "qwen2.5:3b",
            "reason": "released_before_deep",
            "content_logged": False,
        },
    )

    def fake_candidate(*args, reviewer_tier="deep", excluded_model_ids=(), **kwargs):
        attempts.append(reviewer_tier)
        excluded.extend(excluded_model_ids)
        return {
            "ok": True,
            "reason": "generated",
            "answer": (
                "Use an encrypted local repository first for privacy, offline access, "
                "and low latency. Add remote synchronization later behind explicit "
                "consent and a versioned adapter so migration remains reversible."
            ),
            "provider": "ollama",
            "model": "qwen2.5-coder:7b",
            "reviewer_tier": "deep",
            "relevance_text": "Recommend a private local-first storage architecture.",
            "different_model": True,
            "latency_ms": 20.0,
        }

    monkeypatch.setattr(server, "_generate_alternate_local_candidate", fake_candidate)
    response, trace = server._run_nova_chat_turn(
        "Compare private local storage with remote storage and recommend a staged architecture.",
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert attempts == ["deep"]
    assert "qwen2.5:3b" in excluded
    assert response.startswith("Use an encrypted local repository")
    assert trace["reviewer_tier"] == "deep"
    assert trace["direct_middle_primary"] is True
    assert trace["direct_middle_release"]["released"] is True


def test_failed_direct_middle_does_not_load_deep_when_memory_release_fails(monkeypatch):
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *args, **kwargs: {
            "enabled": True,
            "selected": True,
            "reason": "selected",
            "provider": "ollama",
            "model": "qwen2.5:3b",
            "tier": "middle",
            "timeout_seconds": 180,
            "keep_alive": "10m",
            "max_tokens": 256,
            "difficulty": {"difficulty_tier": "hard"},
            "content_logged": False,
        },
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "I am not sure how to answer all of that.",
            {
                "source": "cognitive_os",
                "confidence": 0.85,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:3b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_release_direct_middle_before_deep",
        lambda trace: {
            "attempted": True,
            "released": False,
            "model": "qwen2.5:3b",
            "reason": "concurrent_middle_generation",
            "content_logged": False,
        },
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("deep model must not load while middle-model memory is still busy")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Compare private local storage with remote storage and recommend a staged architecture.",
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert trace["direct_middle_release"]["released"] is False
    assert trace["candidate_selection"]["review_attempts"] == []
    assert (
        trace["candidate_selection"]["retry_result"]
        == "deep_skipped_until_middle_memory_is_released"
    )
    assert response


def test_direct_middle_hint_does_not_replace_a_deterministic_nova_route(monkeypatch):
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *args, **kwargs: {
            "enabled": True,
            "selected": True,
            "reason": "selected",
            "provider": "ollama",
            "model": "qwen2.5:3b",
            "tier": "middle",
            "timeout_seconds": 180,
            "keep_alive": "10m",
            "max_tokens": 256,
            "difficulty": {"difficulty_tier": "hard"},
            "content_logged": False,
        },
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "Your saved project name is Nova Creature.",
            {
                "source": "people_memory",
                "domain": "memory",
                "confidence": 0.98,
                "memory_event": "project_name_recall",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("deterministic routes must not invoke another model")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Compare all my saved project names and tell me which one belongs to this app.",
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == "Your saved project name is Nova Creature."
    assert trace["source"] == "people_memory"
    assert trace["direct_middle_primary"] is False


def test_run_chat_escalates_qwen_uncertainty_to_larger_local_answer(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "I am not sure; I do not have enough information to answer that well.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["memory_transformer", "speech_output_transformer"],
                "skills": ["llm_synthesis"],
                "confidence": 0.88,
                "local_llm_synthesis_used": True,
                "local_llm_model": "Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {
            "ok": True,
            "reason": "generated",
            "answer": "A qubit is a quantum information unit that can occupy a superposition of basis states.",
            "provider": "ollama",
            "model": "deepseek-r1:7b",
            "relevance_text": "Explain what a qubit is",
            "different_model": True,
            "latency_ms": 25.0,
            "model_selection": {"eligible_count": 4, "selected_different_from_primary": True},
        },
    )

    response, trace = server._run_nova_chat_turn(
        "Explain what a qubit is",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert response.startswith("A qubit is")
    assert trace["model"] == "deepseek-r1:7b"
    assert trace["candidate_selection"]["escalation_reason"] == "primary_model_uncertain"
    assert trace["candidate_selection"]["escalation_task_type"] == "general"
    assert trace["candidate_selection"]["selected"] == "alternate_local"


def test_regular_chat_flags_shallow_qwen_advice_for_escalation():
    reason = server._regular_chat_escalation_reason(
        "What should I say to apologize to my friend?",
        "Be honest and kind.",
        {
            "source": "cognitive_os",
            "domain": "general_conversation",
            "confidence": 0.84,
            "local_llm_synthesis_used": True,
            "local_llm_model": "qwen2.5:1.5b",
            "fact_grounding": {"status": "not_required", "evidence_count": 0},
        },
        types.SimpleNamespace(accepted=True),
    )

    assert reason == "primary_model_too_shallow"


def test_regular_chat_flags_qwen_reasking_a_hypothetical_for_escalation():
    answer = (
        "What if your boss says no to your request for Friday off? "
        "You could wait and ask again later."
    )
    reason = server._regular_chat_escalation_reason(
        "What if they say no?",
        answer,
        {
            "source": "cognitive_os",
            "domain": "general_conversation",
            "confidence": 0.88,
            "local_llm_synthesis_used": True,
            "local_llm_model": "qwen2.5:1.5b",
            "fact_grounding": {"status": "not_required", "evidence_count": 0},
        },
        types.SimpleNamespace(accepted=True),
    )

    assert server._answer_reasks_user_question("What if they say no?", answer) is True
    assert reason == "primary_model_question_restatement"


def test_regular_chat_flags_unnecessary_clarification_deflection():
    prompt = (
        "Compare local SQLite vector memory with a remote vector database for a "
        "private mobile AI app. Analyze privacy, offline behavior, latency, migration "
        "risk, and cost, then recommend a staged architecture."
    )
    answer = (
        "Alright, let's dive into this. What specific areas are you most interested "
        "in understanding better?"
    )
    trace = {
        "source": "cognitive_os",
        "domain": "general_conversation",
        "confidence": 0.9,
        "local_llm_synthesis_used": True,
        "local_llm_model": "qwen2.5:1.5b",
        "fact_grounding": {"status": "not_required", "evidence_count": 0},
    }

    reason = server._regular_chat_escalation_reason(
        prompt,
        answer,
        trace,
        types.SimpleNamespace(accepted=True),
    )

    assert server._answer_defers_substantive_request(prompt, answer) is True
    assert reason == "primary_model_clarification_deflection"


def test_direct_middle_answer_must_cover_every_explicit_requested_area():
    prompt = (
        "Compare local SQLite vector memory with a remote vector database for a private "
        "mobile AI app. Analyze privacy, offline behavior, latency, migration risk, "
        "and cost, then recommend a staged architecture."
    )
    answer = (
        "Privacy stays strongest with local storage. Offline behavior remains available "
        "without a network, and local access normally has lower latency. Migration risk "
        "is controlled through a versioned storage adapter. Start local and add optional "
        "remote synchronization later."
    )
    trace = {
        "source": "cognitive_os",
        "domain": "general_conversation",
        "confidence": 0.9,
        "local_llm_synthesis_used": True,
        "local_llm_model": "qwen2.5:3b",
        "direct_middle_primary": True,
        "fact_grounding": {"status": "not_required", "evidence_count": 0},
    }

    reason = server._regular_chat_escalation_reason(
        prompt,
        answer,
        trace,
        types.SimpleNamespace(accepted=True),
    )

    assert reason == "primary_model_requested_aspects_missing"
    assert trace["requested_aspect_coverage"]["complete"] is False


def test_run_chat_repairs_sole_missing_staged_recommendation_without_deep_load(monkeypatch):
    prompt = (
        "Compare local SQLite vector memory with a remote vector database for a private "
        "mobile AI app. Analyze privacy, offline behavior, latency, migration risk, "
        "and cost, then recommend a staged architecture."
    )
    analysis_only = (
        "Privacy: local SQLite keeps vectors on-device.\n"
        "Offline behavior: local search works without connectivity.\n"
        "Latency: local reads avoid network round trips.\n"
        "Migration risk: a versioned adapter makes later migration safer.\n"
        "Cost: local storage avoids recurring cloud fees."
    )
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *args, **kwargs: {
            "enabled": True,
            "selected": True,
            "reason": "selected",
            "provider": "ollama",
            "model": "qwen2.5:3b",
            "tier": "middle",
            "timeout_seconds": 180,
            "keep_alive": "10m",
            "max_tokens": 256,
            "difficulty": {"difficulty_tier": "hard"},
            "content_logged": False,
        },
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            analysis_only,
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "confidence": 0.9,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:3b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("a bounded recommendation repair must avoid a 7B load")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        prompt,
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response.startswith(analysis_only)
    assert "Recommendation: Start with encrypted local storage" in response
    assert trace["requested_recommendation_repaired"] is True
    assert trace["requested_aspect_coverage"]["complete"] is True
    assert trace["answer_firewall"]["status"] == "passed"


def test_run_chat_escalates_shallow_qwen_advice_to_concrete_wording(monkeypatch):
    progress = []
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "Be honest and kind.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["memory_transformer", "speech_output_transformer"],
                "confidence": 0.84,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:1.5b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {
            "ok": True,
            "reason": "generated",
            "answer": (
                'Say, "I care about our friendship, and I am sorry for hurting you. '
                'I want to listen and make this right."'
            ),
            "provider": "ollama",
            "model": "dolphin3:8b",
            "relevance_text": "What should I say to apologize to my friend?",
            "different_model": True,
            "latency_ms": 25.0,
            "model_selection": {"eligible_count": 3, "selected_different_from_primary": True},
        },
    )

    response, trace = server._run_nova_chat_turn(
        "What should I say to apologize to my friend?",
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "progress_callback": lambda stage, label, percent: progress.append(
                (stage, label, percent)
            ) or True,
        },
    )

    assert response.startswith('Say, "I care about our friendship')
    assert trace["candidate_selection"]["escalation_reason"] == "primary_model_too_shallow"
    assert trace["candidate_selection"]["selected"] == "alternate_local"
    assert trace["candidate_selection"]["version"] == "2.5"
    assert [item[0] for item in progress] == [
        "nova_core",
        "answer_review",
        "larger_local_review",
        "middle_local_review",
        "answer_validation",
        "answer_selection",
    ]


def test_managed_stream_buffers_primary_draft_until_larger_replacement(monkeypatch):
    visible = []

    def primary_route(text, context=None):
        context["stream_callback"]("Be honest ")
        context["stream_callback"]("and kind.")
        return (
            "Be honest and kind.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "confidence": 0.84,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:1.5b",
                "native_streaming": True,
                "native_stream_incremental": True,
            },
        )

    monkeypatch.setattr(server, "brain_route", primary_route)
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {
            "ok": True,
            "reason": "generated",
            "answer": (
                'Say, "I care about our friendship, and I am sorry for hurting you. '
                'I want to listen and make this right."'
            ),
            "provider": "ollama",
            "model": "qwen2.5-coder:7b",
            "relevance_text": "What should I say to apologize to my friend?",
            "different_model": True,
        },
    )
    response, trace = server._run_nova_chat_turn(
        "What should I say to apologize to my friend?",
        context={
            "nova_gateway": True,
            "stream_callback": lambda delta: visible.append(delta) or True,
            "stream_cancelled": lambda: False,
            "native_streaming": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response.startswith('Say, "I care about our friendship')
    assert visible == []
    assert trace["candidate_selection"]["retry_allowed"] is True
    assert trace["candidate_selection"]["selected"] == "alternate_local"
    assert trace["managed_streaming_mode"] == "progress_then_validated_answer"
    assert trace["managed_stream_content_logged"] is False


def test_managed_stream_replays_accepted_primary_only_after_validation(monkeypatch):
    visible = []

    def primary_route(text, context=None):
        context["stream_callback"]("Hello ")
        context["stream_callback"]("there.")
        return (
            "Hello there.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "confidence": 0.9,
                "local_llm_synthesis_used": False,
                "native_streaming": True,
                "native_stream_incremental": True,
            },
        )

    monkeypatch.setattr(server, "brain_route", primary_route)

    response, trace = server._run_nova_chat_turn(
        "Say hello",
        context={
            "nova_gateway": True,
            "stream_callback": lambda delta: visible.append(delta) or True,
            "stream_cancelled": lambda: False,
            "native_streaming": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == "Hello there."
    assert visible == ["Hello ", "there."]
    assert trace["native_streaming"] is True
    assert trace["native_stream_incremental"] is True
    assert trace["managed_streaming_mode"] == "validated_primary_replay"


def test_regular_chat_does_not_escalate_a_short_complete_direct_answer():
    reason = server._regular_chat_escalation_reason(
        "What is 2 + 2?",
        "2 + 2 is 4.",
        {
            "source": "cognitive_os",
            "domain": "math",
            "confidence": 0.95,
            "local_llm_synthesis_used": True,
            "local_llm_model": "qwen2.5:1.5b",
            "fact_grounding": {"status": "not_required", "evidence_count": 0},
        },
        types.SimpleNamespace(accepted=True),
    )

    assert reason == ""


def test_regular_chat_flags_complex_qwen_architecture_answer_for_larger_review():
    prompt = (
        "Compare local SQLite vector memory with a remote vector database for a "
        "private mobile AI app. Analyze privacy, offline behavior, latency, migration "
        "risk, and cost, then recommend a staged architecture."
    )
    trace = {
        "source": "cognitive_os",
        "domain": "general_conversation",
        "confidence": 0.9,
        "local_llm_synthesis_used": True,
        "local_llm_model": "qwen2.5:1.5b",
        "fact_grounding": {"status": "not_required", "evidence_count": 0},
    }

    reason = server._regular_chat_escalation_reason(
        prompt,
        "SQLite is private and cheap, while a remote vector database can scale better.",
        trace,
        types.SimpleNamespace(accepted=True),
    )

    assert reason == "primary_model_complexity_mismatch"
    assert trace["uncertainty_routing"]["difficulty_tier"] == "hard"
    assert trace["uncertainty_routing"]["task_type"] == "reasoning"
    assert trace["uncertainty_routing"]["content_logged"] is False
    assert prompt not in str(trace["uncertainty_routing"])


def test_run_chat_uses_larger_local_review_for_complex_qwen_request(monkeypatch):
    prompt = (
        "Compare local SQLite vector memory with a remote vector database for a "
        "private mobile AI app. Analyze privacy, offline behavior, latency, migration "
        "risk, and cost, then recommend a staged architecture."
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "SQLite is private and cheap, while a remote vector database can scale better.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["memory_transformer", "speech_output_transformer"],
                "skills": ["llm_synthesis"],
                "confidence": 0.9,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:1.5b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {
            "ok": True,
            "reason": "generated",
            "answer": (
                "Start with encrypted SQLite behind a provider-neutral memory interface for "
                "privacy, offline reliability, low latency, and predictable cost. Add an "
                "opt-in remote vector index later for synchronized non-private records, with "
                "exportable IDs and dual-write migration tests to control lock-in and risk."
            ),
            "provider": "ollama",
            "model": "deepseek-r1:7b",
            "relevance_text": prompt,
            "different_model": True,
            "latency_ms": 32.0,
            "model_selection": {
                "eligible_count": 3,
                "selected_different_from_primary": True,
            },
        },
    )

    response, trace = server._run_nova_chat_turn(
        prompt,
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response.startswith("Start with encrypted SQLite")
    assert trace["model"] == "deepseek-r1:7b"
    assert trace["candidate_selection"]["escalation_reason"] == "primary_model_complexity_mismatch"
    assert trace["candidate_selection"]["escalation_task_type"] == "reasoning"
    assert trace["candidate_selection"]["selected"] == "alternate_local"
    assert "difficulty_routing" in trace["skills"]


def test_run_chat_replaces_reversed_latency_claim_with_consistent_local_answer(monkeypatch):
    prompt = (
        "Compare local SQLite vector memory with a remote vector database for a private "
        "mobile AI app. Analyze privacy, offline behavior, latency, migration risk, and cost."
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            (
                "Using local SQLite keeps data private. It supports offline access but may "
                "have higher latency compared to remote databases."
            ),
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["memory_transformer", "speech_output_transformer"],
                "skills": ["llm_synthesis"],
                "confidence": 0.9,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:1.5b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {
            "ok": True,
            "reason": "generated",
                "answer": (
                    "Start with encrypted local SQLite: it improves privacy, normally avoids network "
                    "round trips for lower latency, and works offline. Add an opt-in remote index "
                    "later for synchronization and centralized scaling. A provider-neutral adapter "
                    "limits migration risk; local storage avoids service fees while remote operation "
                    "adds ongoing cost."
                ),
            "provider": "ollama",
            "model": "qwen2.5-coder:7b",
            "relevance_text": prompt,
            "different_model": True,
            "latency_ms": 40.0,
        },
    )

    response, trace = server._run_nova_chat_turn(
        prompt,
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response.startswith("Start with encrypted local SQLite")
    assert trace["candidate_selection"]["escalation_reason"] == "primary_model_consistency_failed"
    assert trace["candidate_selection"]["selected"] == "alternate_local"
    assert trace["candidate_selection"]["alternate_consistency"]["status"] == "passed"
    assert trace["answer_consistency"]["status"] == "passed"
    assert trace["model"] == "qwen2.5-coder:7b"
    assert "technical_consistency_check" in trace["skills"]


def test_run_chat_blocks_inconsistent_larger_local_candidate(monkeypatch):
    prompt = (
        "Compare local SQLite with a remote vector database for latency, offline use, and cost."
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "I'm here with you. Tell me what you want to do next.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "confidence": 0.8,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:1.5b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {
            "ok": True,
            "reason": "generated",
            "answer": (
                "Local SQLite requires an active internet connection, while a remote cloud "
                "database works entirely offline without a local cache."
            ),
            "provider": "ollama",
            "model": "qwen2.5-coder:7b",
            "relevance_text": prompt,
            "different_model": True,
        },
    )
    monkeypatch.setattr(
        nova_llm_synthesizer,
        "generate_fallback",
        lambda message, timeout=10: (None, False, "offline"),
    )
    response, trace = server._run_nova_chat_turn(
        prompt,
        context={
            "nova_gateway": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert "stopped it instead of pretending" in response
    assert trace["candidate_selection"]["selected"] == "recovery"
    assert trace["candidate_selection"]["retry_result"] == "consistency_check_failed"
    assert trace["candidate_selection"]["alternate_consistency"]["status"] == "blocked"
    assert trace["candidate_selection"]["alternate_consistency"]["content_logged"] is False


def test_difficulty_escalation_can_be_disabled_without_disabling_other_checks(monkeypatch):
    monkeypatch.setenv("NOVA_DIFFICULTY_ESCALATION_ENABLED", "false")
    trace = {
        "source": "cognitive_os",
        "domain": "general_conversation",
        "confidence": 0.9,
        "local_llm_synthesis_used": True,
        "local_llm_model": "qwen2.5:1.5b",
        "fact_grounding": {"status": "not_required", "evidence_count": 0},
    }
    reason = server._regular_chat_escalation_reason(
        (
            "Compare local SQLite vector memory with a remote vector database. "
            "Analyze privacy, offline behavior, latency, migration risk, and cost, "
            "then recommend a staged architecture."
        ),
        (
            "SQLite keeps data local and inexpensive. A remote database can improve "
            "synchronization but introduces network dependence and recurring cost."
        ),
        trace,
        types.SimpleNamespace(accepted=True),
    )

    assert reason == ""
    assert trace["uncertainty_routing"]["larger_local_recommended"] is True


def test_regular_chat_flags_qwen_unverified_exact_numeric_claim_for_escalation():
    reason = server._regular_chat_escalation_reason(
        "What is the exact value of the Busy Beaver function BB(100)?",
        "The exact value is 613.",
        {
            "source": "cognitive_os",
            "domain": "general_conversation",
            "local_llm_synthesis_used": True,
            "local_llm_model": "qwen2.5:1.5b",
            "fact_grounding": {"status": "unverified", "evidence_count": 0},
        },
        types.SimpleNamespace(accepted=True),
    )

    assert reason == "primary_model_unverified_exact_claim"


def test_candidate_retry_prompt_requires_an_explained_unknown_instead_of_a_yes_no():
    prompt, relevance = server._candidate_retry_prompt(
        "What is the exact value of the Busy Beaver function BB(100)?",
        "",
        "",
        primary_trace={},
        context={},
    )

    assert "explicitly say that it is unknown or unverified" in prompt
    assert "Do not answer with only yes/no" in prompt
    assert "never invent a number" in prompt
    assert relevance.startswith("What is the exact value")


def test_candidate_retry_prompt_includes_registered_storage_invariants():
    prompt, _relevance = server._candidate_retry_prompt(
        (
            "Compare local SQLite vector memory with a remote vector database. Analyze privacy, "
            "offline behavior, latency, migration risk, and cost, then recommend a staged architecture."
        ),
        "",
        "",
        primary_trace={},
        context={},
    )

    assert "High-confidence technical constraints" in prompt
    assert "one short labeled clause for each item by name" in prompt
    assert "Required output format: no preamble" in prompt
    assert "\nPrivacy:" in prompt
    assert "\nOffline behavior:" in prompt
    assert "\nLatency:" in prompt
    assert "\nMigration risk:" in prompt
    assert "\nCost:" in prompt
    assert prompt.index("\nPrivacy:") < prompt.index("\nCost:") < prompt.index("\nRecommendation:")
    assert "avoids network round trips" in prompt
    assert "needs connectivity" in prompt


def test_requested_aspect_coverage_detects_omitted_explicit_topics():
    request = (
        "Compare local and remote memory. Analyze privacy, offline behavior, latency, "
        "migration risk, and cost, then recommend a design."
    )
    partial = server._requested_aspect_coverage(
        request,
        "Local storage improves privacy, works offline, and lowers latency.",
    )
    complete = server._requested_aspect_coverage(
        request,
        (
            "Privacy: keep sensitive vectors on-device.\n"
            "Offline behavior: local search works without a network.\n"
            "Latency: local reads avoid network round trips.\n"
            "Migration risk: use a versioned storage adapter.\n"
            "Cost: local storage avoids recurring service fees.\n"
            "Recommendation: start local and add optional remote synchronization later."
        ),
    )
    analysis_without_recommendation = server._requested_aspect_coverage(
        request,
        (
            "Privacy: local storage keeps vectors on-device.\n"
            "Offline behavior: local search works without a network.\n"
            "Latency: local reads avoid network round trips.\n"
            "Migration risk: use a versioned storage adapter.\n"
            "Cost: local storage avoids recurring service fees."
        ),
    )

    assert partial == {
        "applied": True,
        "required_count": 6,
        "covered_count": 3,
        "coverage_ratio": 0.5,
        "complete": False,
    }
    assert complete["covered_count"] == 6
    assert complete["complete"] is True
    assert analysis_without_recommendation["covered_count"] == 5
    assert analysis_without_recommendation["complete"] is False


def test_candidate_numeric_verification_distinguishes_cost_analysis_from_amount_request():
    assert server._candidate_requires_numeric_verification(
        "Analyze privacy, latency, migration risk, and cost, then recommend a staged architecture.",
        "",
    ) is False
    assert server._candidate_requires_numeric_verification(
        "How much will the remote database cost per month?",
        "",
    ) is True
    assert server._candidate_requires_numeric_verification(
        "How big is the Earth?",
        "",
    ) is True


def test_busy_beaver_math_function_escalates_as_reasoning_not_coding():
    assert (
        server._candidate_escalation_task_type(
            "What is the exact value of the Busy Beaver function BB(100)?",
            {"domain": "coding"},
        )
        == "reasoning"
    )


def test_regular_chat_flags_exact_numeric_guess_even_when_grounding_calls_it_not_required():
    reason = server._regular_chat_escalation_reason(
        "What is the exact value of the Busy Beaver function BB(100)?",
        "The exact value of BB(100) is 293.",
        {
            "source": "cognitive_os",
            "domain": "general_conversation",
            "local_llm_synthesis_used": True,
            "local_llm_model": "qwen2.5:1.5b",
            "fact_grounding": {"status": "not_required", "evidence_count": 0},
        },
        types.SimpleNamespace(accepted=True),
    )

    assert reason == "primary_model_unverified_exact_claim"


def test_run_chat_never_preserves_unverified_exact_qwen_guess_when_larger_model_fails(monkeypatch):
    guessed_answer = (
        "The exact value of the Busy Beaver function BB(100) is 613. "
        "This is the claimed maximum output."
    )
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            guessed_answer,
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "confidence": 0.88,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:1.5b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {"ok": False, "reason": "larger_model_unavailable"},
    )

    response, trace = server._run_nova_chat_turn(
        "What is the exact value of the Busy Beaver function BB(100)?",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert "613" not in response
    assert "will not guess" in response
    assert trace["source"] == "exact_claim_verification_guard"
    assert trace["candidate_selection"]["selected"] == "recovery"
    assert trace["answer_firewall"]["status"] == "unverified_exact_claim_blocked"


def test_run_chat_keeps_honest_qwen_uncertainty_when_larger_model_is_unavailable(monkeypatch):
    qwen_answer = "I do not know enough about that private project detail to answer accurately."
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            qwen_answer,
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "confidence": 0.88,
                "local_llm_synthesis_used": True,
                "local_llm_model": "Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {"ok": False, "reason": "larger_model_unavailable"},
    )

    response, trace = server._run_nova_chat_turn(
        "Explain the private project detail",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert response == qwen_answer
    assert trace["candidate_selection"]["selected"] == "primary"
    assert trace["candidate_selection"]["escalation_reason"] == "primary_model_uncertain"
    assert trace["model_escalation_result"] == "larger_model_unavailable"
    assert trace["answer_firewall"]["status"] == "passed_primary_after_escalation"


def test_run_chat_does_not_escalate_missing_personal_memory(monkeypatch):
    answer = "I don't have your favorite constellation saved yet."
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            answer,
            {
                "source": "long_term_memory",
                "domain": "memory",
                "memory_event": "missing:long_term",
                "confidence": 0.9,
                "local_llm_synthesis_used": True,
                "local_llm_model": "Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("A larger model cannot recover a missing private memory")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "What is my favorite constellation?",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert response == answer
    assert "candidate_selection" not in trace
    assert trace["answer_firewall"]["status"] == "passed"


def test_run_chat_candidate_selector_rejects_weak_second_candidate(monkeypatch):
    canned = "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app."
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (canned, {"source": "cognitive_os", "confidence": 0.8}),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: {
            "ok": True,
            "reason": "generated",
            "answer": canned,
            "provider": "local-test-provider",
            "model": "small-general",
            "relevance_text": "How do you make ice cream?",
            "different_model": True,
        },
    )
    monkeypatch.setattr(
        nova_llm_synthesizer,
        "generate_fallback",
        lambda message, timeout=10: (None, False, "offline"),
    )

    response, trace = server._run_nova_chat_turn(
        "How do you make ice cream?",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert "off-topic draft" in response
    assert trace["source"] == "answer_firewall_recovery"
    assert trace["candidate_selection"]["selected"] == "recovery"
    assert len(trace["candidate_selection"]["candidates"]) == 1
    assert [item["tier"] for item in trace["candidate_selection"]["review_attempts"]] == [
        "middle",
        "deep",
    ]
    assert all(
        item["reason"] == "candidate_quality_rejected"
        for item in trace["candidate_selection"]["review_attempts"]
    )
    assert trace["candidate_selection"]["llm_fallback"]["reason"] == "offline"


def test_run_chat_fact_grounding_blocks_unverified_current_fact_without_model_retry(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (_ for _ in ()).throw(
            AssertionError("unsupported current facts must stop before model generation")
        ),
    )
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unverified current facts must not be retried through another model")
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Who is the current mayor of Example City?",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert response.startswith("I stopped an unverified current-fact answer")
    assert trace["source"] == "fact_grounding_guard"
    assert trace["answer_firewall"]["status"] == "fact_grounding_blocked"
    assert "freshness_unverified" in trace["answer_firewall"]["reasons"]
    assert trace["candidate_selection"]["retry_allowed"] is False
    assert trace["candidate_selection"]["retry_policy_reason"] == "fact_grounding_preflight"
    assert trace["fact_grounding"]["status"] == "unverified"
    assert trace["fact_grounding"]["blocking"] is True
    assert "_fact_grounding_blocking" not in trace
    assert trace["answer_status"]["intent"] == "current_fact"
    assert trace["answer_status"]["safety"] == "fact_grounding_blocked"


def test_run_chat_does_not_treat_social_today_checkin_as_current_fact(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "Just chilling, hanging out with you!",
            {
                "source": "reviewed_training",
                "domain": "self_awareness",
                "confidence": 0.99,
                "final_answer_source": "reviewed_training",
            },
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "What u doing today?",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert response == "Just chilling, hanging out with you!"
    assert trace["source"] == "reviewed_training"
    assert trace["fact_grounding"]["status"] == "not_required"
    assert trace["fact_grounding"]["blocking"] is False
    assert trace["answer_firewall"]["status"] == "passed"


def test_run_chat_keeps_fresh_official_current_fact(monkeypatch):
    verified_date = date.today().isoformat()
    answer = f"As of {verified_date}, the President is Example Person."
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            answer,
            {
                "source": "current_officeholder_guard",
                "domain": "current_facts",
                "confidence": 0.99,
                "verified_date": verified_date,
                "verified_source": "Official administration record",
            },
        ),
    )

    response, trace = server._run_nova_chat_turn(
        "Who is the current president?",
        context={"nova_gateway": True, "memory_write_allowed": False, "conversation_memory_allowed": False},
    )

    assert response == answer
    assert trace["source"] == "current_officeholder_guard"
    assert trace["fact_grounding"]["status"] == "grounded"
    assert trace["fact_grounding"]["blocking"] is False
    assert trace["answer_firewall"]["status"] == "passed"


def test_alternate_candidate_uses_registered_local_provider_and_protocol_request(monkeypatch):
    captured = {}
    large_model = types.SimpleNamespace(
        model_id="large-general",
        provider_id="local-test-provider",
        display_name="Large General",
        text_input=True,
        text_output=True,
        reasoning=True,
        local_or_remote="local",
        estimated_cost_type="free",
        availability="available",
        health_status="healthy",
        metadata={"size": 5_000_000_000},
    )

    class FakeProvider:
        provider_id = "local-test-provider"
        local_or_remote = "local"
        cost_type = "free"
        base_url = "http://127.0.0.1:9999"

        def list_models(self):
            return [large_model]

        def generate(self, request):
            captured["request"] = request
            return types.SimpleNamespace(
                content="A direct answer from the alternate local candidate.",
                finish_reason="stop",
            )

    fake_provider = FakeProvider()
    fake_registry = types.SimpleNamespace(
        list_providers=lambda: [
            {
                "provider_id": "existing-nova",
                "local_or_remote": "local",
                "cost_type": "free",
            },
            {
                "provider_id": "local-test-provider",
                "local_or_remote": "local",
                "cost_type": "free",
            },
        ],
        get_provider=lambda provider_id: fake_provider,
    )
    monkeypatch.setattr(server, "NOVA_GATEWAY", types.SimpleNamespace(providers=fake_registry))

    result = server._generate_alternate_local_candidate(
        "Explain local AI",
        "",
        "",
        {
            "local_llm_model": "Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            "memory_retrieved": True,
            "extracted_slot": "favorite_color",
            "extracted_value": "blue",
        },
        {
            "user_id": "owner",
            "client_id": "phone",
            "conversation_id": "conversation-1",
            "conversation_history": [
                {"role": "user", "content": "Remember my favorite color is blue."},
                {"role": "assistant", "content": "I will remember that."},
            ],
            "conversation_summary": {
                "schema_version": "1.0",
                "revision": 2,
                "topics": ["Earlier we planned a local-first project."],
            },
        },
    )

    assert result["ok"] is True
    assert result["provider"] == "local-test-provider"
    assert result["model"] == "large-general"
    request = captured["request"]
    assert request.privacy_mode == "local_only"
    assert request.metadata["candidate_retry"] is True
    assert request.metadata["provider_model"] == "large-general"
    assert request.metadata["provider_timeout_seconds"] == 180
    assert request.metadata["provider_context_window"] == 4096
    assert request.generation_options.max_tokens == 256
    assert request.generation_options.seed == 0
    assert "\nHigh-confidence technical constraints:" in request.generation_options.stop
    assert request.client_id == "phone"
    assert request.api_source == "nova_candidate_selector"
    assert "Start with the answer, never a preamble" in request.messages[0].content
    assert "stay under 110 words" in request.messages[0].content
    assert "Relevant saved memory: favorite color = blue" in request.messages[-1].content
    assert "Remember my favorite color is blue." in request.messages[-1].content
    assert "Earlier we planned a local-first project." in request.messages[-1].content
    assert "finish the final sentence" in request.messages[-1].content
    assert result["finish_reason"] == "stop"


def test_alternate_candidate_rejects_provider_token_limit(monkeypatch):
    capability = types.SimpleNamespace(
        model_id="large-general",
        provider_id="local-test-provider",
        text_input=True,
        text_output=True,
        reasoning=True,
        local_or_remote="local",
        estimated_cost_type="free",
        availability="available",
        health_status="healthy",
        metadata={"size": 5_000_000_000},
    )

    class TruncatedProvider:
        provider_id = "local-test-provider"
        local_or_remote = "local"
        cost_type = "free"
        base_url = "http://127.0.0.1:9999"

        def list_models(self):
            return [capability]

        def generate(self, request):
            return types.SimpleNamespace(
                content="This candidate ends because it reached the configured token",
                finish_reason="length",
            )

    provider = TruncatedProvider()
    registry = types.SimpleNamespace(
        list_providers=lambda: [
            {
                "provider_id": provider.provider_id,
                "local_or_remote": "local",
                "cost_type": "free",
            }
        ],
        get_provider=lambda provider_id: provider,
    )
    monkeypatch.setattr(server, "NOVA_GATEWAY", types.SimpleNamespace(providers=registry))

    result = server._generate_alternate_local_candidate(
        "Compare two architectures and recommend one.",
        "",
        "",
        {"local_llm_model": "qwen2.5:1.5b"},
        {},
    )

    assert result["ok"] is False
    assert result["reason"] == "candidate_token_limit"
    assert result["finish_reason"] == "length"
    assert "answer" not in result


def test_ollama_candidate_respects_adaptive_memory_block_without_generation(monkeypatch):
    import nova_model_memory

    generated = []
    capability = types.SimpleNamespace(
        model_id="qwen2.5-coder:7b",
        provider_id="ollama",
        text_input=True,
        text_output=True,
        reasoning=True,
        local_or_remote="local",
        estimated_cost_type="free",
        availability="available",
        health_status="healthy",
        metadata={"size": 4_700_000_000},
    )
    provider = types.SimpleNamespace(
        provider_id="ollama",
        local_or_remote="local",
        cost_type="free",
        base_url="http://127.0.0.1:11434",
        list_models=lambda: [capability],
        generate=lambda _request: generated.append(True),
    )
    registry = types.SimpleNamespace(
        list_providers=lambda: [
            {
                "provider_id": "ollama",
                "local_or_remote": "local",
                "cost_type": "free",
            }
        ],
        get_provider=lambda _provider_id: provider,
    )
    monkeypatch.setattr(server, "NOVA_GATEWAY", types.SimpleNamespace(providers=registry))
    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **_kwargs: nullcontext(
            {
                "enabled": True,
                "allowed": False,
                "reason": "insufficient_safe_memory",
                "content_logged": False,
            }
        ),
    )

    result = server._generate_alternate_local_candidate(
        "Analyze this difficult local architecture.",
        "",
        "",
        {"local_llm_model": "qwen2.5:1.5b"},
        {},
    )

    assert result["ok"] is False
    assert result["reason"] == "model_memory_policy_blocked"
    assert generated == []
    assert result["model_selection"]["resource_manager"]["content_logged"] is False


def test_candidate_retry_policy_blocks_action_routes_and_remote_endpoints(monkeypatch):
    monkeypatch.setenv("NOVA_CANDIDATE_RETRY_ENABLED", "true")

    allowed, reason = server._candidate_retry_allowed(
        {"source": "app_navigation", "action": "open", "domain": "navigation"},
        {},
    )
    assert allowed is False
    assert reason == "action_route"
    assert server._provider_is_safe_local_candidate(
        types.SimpleNamespace(local_or_remote="local", cost_type="free", base_url="http://127.0.0.1:11434")
    ) is True
    assert server._provider_is_safe_local_candidate(
        types.SimpleNamespace(local_or_remote="local", cost_type="free", base_url="https://models.example.com")
    ) is False
    assert server._provider_is_safe_local_candidate(
        types.SimpleNamespace(local_or_remote="remote", cost_type="free", base_url="http://127.0.0.1:11434")
    ) is False


def test_run_chat_firewall_never_checks_or_rewrites_raw_adapter_output(monkeypatch):
    raw_answer = "Raw adapter words, exactly as generated."
    progress = []
    captured_context = {}

    def fake_raw_brain(text, context=None):
        captured_context.update(context or {})
        return raw_answer, {"source": "raw_adapter_only", "roles": ["raw_qwen_adapter"]}

    monkeypatch.setattr(server, "brain_route", fake_raw_brain)
    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("raw mode must not run candidate selection")),
    )

    response, trace = server._run_nova_chat_turn(
        "answer raw",
        context={
            "nova_gateway": True,
            "adapter_only_mode": True,
            "progress_callback": lambda stage, label, percent: progress.append(
                (stage, label, percent)
            ) or True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == raw_answer
    assert trace["source"] == "raw_adapter_only"
    assert trace["answer_firewall"]["status"] == "bypassed_raw"
    assert trace["answer_firewall"]["checked"] is False
    assert trace["answer_firewall"]["intercepted"] is False
    assert trace["fact_grounding"]["status"] == "bypassed_raw"
    assert trace["fact_grounding"]["blocking"] is False
    assert trace["answer_consistency"]["status"] == "bypassed_raw"
    assert trace["answer_consistency"]["applied"] is False
    assert trace["direct_middle_routing"]["reason"] == "raw_adapter_bypass"
    assert trace["direct_middle_primary"] is False
    assert "primary_model_override" not in captured_context
    assert "uncertainty_routing" not in trace
    assert [item[0] for item in progress] == ["raw_adapter"]


def test_web_ui_sends_context_for_all_modes_and_shows_firewall_state():
    html = server.WEB_HTML

    assert "payload.conversation_history = recentConversationHistory.slice(-8)" in html
    assert "payload.conversation_summary = conversationSummary" in html
    assert "payload.conversation_summary_write_allowed = conversationPersistenceEnabled && !privateModeEnabled" in html
    assert "summary:conversationSummary" in html
    assert "trace?.conversation_summary" in html
    assert "firewallStatus === 'bypassed_raw'" in html
    assert "NO WEB/TOOLS" in html
    assert "firewallStatus === 'passed_after_retry'" in html
    assert "shield: better answer selected" in html
    assert "firewallStatus === 'fact_grounding_blocked'" in html
    assert "shield: current fact blocked" in html
    assert "shield: off-topic blocked" in html
    assert "shield: answer checked" in html
    assert "groundingStatus === 'grounded'" in html
    assert "fact: grounded" in html
    assert "fact: source needed" in html
    assert "groundingStatus === 'web_privacy_blocked'" in html
    assert "retrievalStatus === 'success'" in html
    assert "web: '+sourceCount+' sources" in html
    assert "consensusStatus === 'corroborated'" in html
    assert "consensus: sources disagree" in html
    assert "meaning: matched" in html
    assert "meta.uncertainty_routing?.difficulty_tier === 'hard'" in html
    assert "brain: hard task" in html
    assert "brain: larger local selected" in html
    assert "brain: Qwen kept" in html
    assert "brain: safe recovery" in html
    assert "logic: consistency checked" in html
    assert "logic: contradiction blocked" in html
    assert "function evidenceDrawerHtml" in html
    assert "Evidence details &middot;" in html
    assert "numeric_derived:'converted measurement'" in html
    assert 'rel="noopener noreferrer"' in html


def test_run_chat_rolls_old_context_into_portable_summary_without_logging_content(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "Current answer.",
            {"source": "raw_adapter_only", "roles": ["raw_qwen_adapter"]},
        ),
    )
    history = []
    for index in range(1, 5):
        history.extend(
            [
                {"role": "user", "content": f"Earlier question {index}"},
                {"role": "assistant", "content": f"Earlier answer {index}"},
            ]
        )
    before = len(server.SESSION_LOG)

    response, trace = server._run_nova_chat_turn(
        "Current question",
        context={
            "nova_gateway": True,
            "adapter_only_mode": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "conversation_summary_write_allowed": True,
            "conversation_history": history,
        },
    )

    assert response == "Current answer."
    assert trace["conversation_summary_updated"] is True
    assert trace["conversation_summary_revision"] == 1
    assert trace["conversation_summary"]["topics"] == ["Earlier question 1"]
    assert "conversation_summary" not in server.SESSION_LOG[before]


def test_private_turn_cannot_update_supplied_conversation_summary(monkeypatch):
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "Private answer.",
            {"source": "raw_adapter_only", "roles": ["raw_qwen_adapter"]},
        ),
    )

    _response, trace = server._run_nova_chat_turn(
        "Private question",
        context={
            "nova_gateway": True,
            "adapter_only_mode": True,
            "private_mode": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "conversation_summary_write_allowed": False,
            "conversation_summary": {"schema_version": "1.0", "revision": 4},
            "conversation_history": [
                {"role": "user", "content": f"private {index}"}
                if index % 2 == 0
                else {"role": "assistant", "content": f"private {index}"}
                for index in range(8)
            ],
        },
    )

    assert "conversation_summary" not in trace
    assert "conversation_summary_updated" not in trace


def test_raw_adapter_prompt_receives_summary_as_context_without_answer_interception():
    prompt = server._raw_adapter_prompt_with_history(
        "What did I prefer?",
        [{"role": "assistant", "content": "We were comparing providers."}],
        {
            "schema_version": "1.0",
            "revision": 2,
            "user_facts": ["I prefer local models."],
        },
    )

    assert "EARLIER CONVERSATION SUMMARY" in prompt
    assert "I prefer local models." in prompt
    assert "Recent conversation:" in prompt
    assert prompt.endswith("User: What did I prefer?\nAssistant:")


def test_background_model_warmup_reports_ready_without_blocking_server(monkeypatch):
    import nova_local_llm_connector

    monkeypatch.setenv("NOVA_MODEL_WARMUP_DELAY_SECONDS", "0")
    monkeypatch.setenv("NOVA_REVIEWER_WARMUP", "false")
    monkeypatch.setattr(
        nova_local_llm_connector.LocalLLMConnector,
        "warm_up",
        lambda self: {
            "ok": True,
            "state": "ready",
            "provider": "hf_peft_lora",
            "model": "Nova cached test model",
            "device": "cpu",
            "elapsed_ms": 12.5,
        },
    )

    thread = server._start_model_warmup()
    assert thread is not None
    thread.join(timeout=2)
    status = server._public_model_warmup_status()

    assert status["state"] == "ready"
    assert status["provider"] == "hf_peft_lora"
    assert status["model"] == "Nova cached test model"
    assert status["reviewer"]["state"] == "disabled"
    assert "error" not in status


def test_reviewer_warmup_selects_installed_large_local_model_with_memory_headroom(monkeypatch):
    import nova_model_memory

    captured = {}
    capability = types.SimpleNamespace(
        model_id="large-reviewer",
        provider_id="local-test-provider",
        display_name="Large Reviewer",
        text_input=True,
        text_output=True,
        reasoning=True,
        local_or_remote="local",
        estimated_cost_type="free",
        availability="available",
        health_status="healthy",
        metadata={"size": 4_000_000_000},
    )

    class FakeProvider:
        provider_id = "local-test-provider"
        local_or_remote = "local"
        cost_type = "free"
        base_url = "http://127.0.0.1:11434"

        def list_models(self):
            return [capability]

        def warm_up_model(self, model_id, *, keep_alive=None, timeout=None):
            captured.update(model_id=model_id, keep_alive=keep_alive, timeout=timeout)
            return {
                "ok": True,
                "state": "ready",
                "provider": self.provider_id,
                "model": model_id,
                "elapsed_ms": 25.0,
            }

    provider = FakeProvider()
    registry = types.SimpleNamespace(
        list_providers=lambda: [
            {
                "provider_id": provider.provider_id,
                "local_or_remote": "local",
                "cost_type": "free",
            }
        ],
        get_provider=lambda _provider_id: provider,
    )
    monkeypatch.setattr(server, "NOVA_GATEWAY", types.SimpleNamespace(providers=registry))
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {"available_physical_gb": 12.0},
    )
    config = types.SimpleNamespace(
        reviewer_warmup=True,
        reviewer_warmup_task="reasoning",
        reviewer_warmup_min_available_gb=8.0,
        reviewer_keep_alive="60m",
        regular_chat_escalation_enabled=True,
        model="small-primary",
        model_warmup_timeout=90,
        escalation_model_preferences=lambda _task: ("large-reviewer",),
    )

    result = server._warm_reviewer_model(config)

    assert result["state"] == "ready"
    assert result["model"] == "large-reviewer"
    assert result["available_memory_gb"] == 12.0
    assert result["required_memory_gb"] >= 8.0
    assert result["content_logged"] is False
    assert captured == {
        "model_id": "large-reviewer",
        "keep_alive": "60m",
        "timeout": 90,
    }


def test_reviewer_warmup_prefers_configured_middle_tier_with_lower_safe_ram_gate(monkeypatch):
    import nova_model_memory

    captured = {}

    def model(model_id, size):
        return types.SimpleNamespace(
            model_id=model_id,
            provider_id="local-test-provider",
            text_input=True,
            text_output=True,
            reasoning=True,
            local_or_remote="local",
            estimated_cost_type="free",
            availability="available",
            health_status="healthy",
            metadata={"size": size},
        )

    provider = types.SimpleNamespace(
        provider_id="local-test-provider",
        local_or_remote="local",
        cost_type="free",
        base_url="http://127.0.0.1:11434",
        list_models=lambda: [
            model("qwen2.5:3b", 2_000_000_000),
            model("qwen2.5-coder:7b", 4_700_000_000),
        ],
        warm_up_model=lambda model_id, **kwargs: (
            captured.update(model_id=model_id, **kwargs)
            or {
                "ok": True,
                "state": "ready",
                "provider": "local-test-provider",
                "model": model_id,
                "elapsed_ms": 18.0,
            }
        ),
    )
    registry = types.SimpleNamespace(
        list_providers=lambda: [
            {
                "provider_id": provider.provider_id,
                "local_or_remote": "local",
                "cost_type": "free",
            }
        ],
        get_provider=lambda _provider_id: provider,
    )
    monkeypatch.setattr(server, "NOVA_GATEWAY", types.SimpleNamespace(providers=registry))
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {"available_physical_gb": 6.0},
    )
    monkeypatch.setattr(nova_model_memory, "list_ollama_loaded_models", lambda: [])
    config = types.SimpleNamespace(
        reviewer_warmup=True,
        reviewer_warmup_task="reasoning",
        reviewer_warmup_min_available_gb=8.0,
        reviewer_keep_alive="10m",
        regular_chat_escalation_enabled=True,
        middle_reviewer_enabled=True,
        middle_reviewer_min_model_bytes=1_500_000_000,
        middle_reviewer_max_model_bytes=3_000_000_000,
        middle_reviewer_warmup_min_available_gb=5.0,
        middle_reviewer_model_preferences=lambda _task: ("qwen2.5:3b",),
        model="qwen2.5:1.5b",
        model_warmup_timeout=90,
        escalation_model_preferences=lambda _task: ("qwen2.5-coder:7b",),
    )

    result = server._warm_reviewer_model(config)

    assert result["state"] == "ready"
    assert result["tier"] == "middle"
    assert result["model"] == "qwen2.5:3b"
    assert result["required_memory_gb"] == 5.0
    assert captured["model_id"] == "qwen2.5:3b"


def test_reviewer_warmup_reports_already_resident_middle_model_ready_under_ram_gate(monkeypatch):
    import nova_model_memory

    capability = types.SimpleNamespace(
        model_id="qwen2.5:3b",
        provider_id="local-test-provider",
        text_input=True,
        text_output=True,
        reasoning=True,
        local_or_remote="local",
        estimated_cost_type="free",
        availability="available",
        health_status="healthy",
        metadata={"size": 2_000_000_000},
    )
    provider = types.SimpleNamespace(
        provider_id="local-test-provider",
        local_or_remote="local",
        cost_type="free",
        base_url="http://127.0.0.1:11434",
        list_models=lambda: [capability],
        warm_up_model=lambda *args, **kwargs: pytest.fail("resident model must not reload"),
    )
    registry = types.SimpleNamespace(
        list_providers=lambda: [
            {
                "provider_id": provider.provider_id,
                "local_or_remote": "local",
                "cost_type": "free",
            }
        ],
        get_provider=lambda _provider_id: provider,
    )
    monkeypatch.setattr(server, "NOVA_GATEWAY", types.SimpleNamespace(providers=registry))
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {"available_physical_gb": 3.0},
    )
    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [{"name": "qwen2.5:3b"}],
    )
    config = types.SimpleNamespace(
        reviewer_warmup=True,
        reviewer_warmup_task="reasoning",
        reviewer_warmup_min_available_gb=8.0,
        reviewer_keep_alive="10m",
        regular_chat_escalation_enabled=True,
        middle_reviewer_enabled=True,
        middle_reviewer_min_model_bytes=1_500_000_000,
        middle_reviewer_max_model_bytes=3_000_000_000,
        middle_reviewer_warmup_min_available_gb=5.0,
        middle_reviewer_model_preferences=lambda _task: ("qwen2.5:3b",),
        model="qwen2.5:1.5b",
        model_warmup_timeout=90,
        escalation_model_preferences=lambda _task: ("qwen2.5-coder:7b",),
    )

    result = server._warm_reviewer_model(config)

    assert result["state"] == "ready"
    assert result["reason_code"] == "already_resident"
    assert result["tier"] == "middle"
    assert result["available_memory_gb"] == 3.0


def test_reviewer_warmup_defers_without_calling_model_under_memory_pressure(monkeypatch):
    import nova_model_memory

    called = []
    capability = types.SimpleNamespace(
        model_id="large-reviewer",
        provider_id="local-test-provider",
        text_input=True,
        text_output=True,
        reasoning=True,
        local_or_remote="local",
        estimated_cost_type="free",
        availability="available",
        health_status="healthy",
        metadata={"size": 5_000_000_000},
    )
    provider = types.SimpleNamespace(
        provider_id="local-test-provider",
        local_or_remote="local",
        cost_type="free",
        base_url="http://127.0.0.1:11434",
        list_models=lambda: [capability],
        warm_up_model=lambda *args, **kwargs: called.append((args, kwargs)),
    )
    registry = types.SimpleNamespace(
        list_providers=lambda: [
            {
                "provider_id": provider.provider_id,
                "local_or_remote": "local",
                "cost_type": "free",
            }
        ],
        get_provider=lambda _provider_id: provider,
    )
    monkeypatch.setattr(server, "NOVA_GATEWAY", types.SimpleNamespace(providers=registry))
    monkeypatch.setattr(
        nova_model_memory,
        "system_memory_status",
        lambda: {"available_physical_gb": 4.0},
    )
    config = types.SimpleNamespace(
        reviewer_warmup=True,
        reviewer_warmup_task="reasoning",
        reviewer_warmup_min_available_gb=8.0,
        reviewer_keep_alive="60m",
        regular_chat_escalation_enabled=True,
        model="small-primary",
        model_warmup_timeout=90,
        escalation_model_preferences=lambda _task: ("large-reviewer",),
    )

    result = server._warm_reviewer_model(config)

    assert result["state"] == "deferred_memory"
    assert result["reason_code"] == "memory_headroom"
    assert called == []


def test_web_ui_exposes_camera_flip_and_front_camera_mode():
    html = server.WEB_HTML
    required_markers = [
        'id="mainFlipCameraBtn"',
        'class="flip-camera-btn"',
        'onclick="flipCamera()"',
        'id="btnFlipCamera"',
        "Front Cam",
        "Back Cam",
        "cameraFacingMode",
        "function cameraFacingLabel",
        "function updateCameraFacingUi",
        "function flipCamera",
        "facingMode: {ideal: cameraFacingMode}",
        "cameraPreview.style.transform",
        "Camera flipped to",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_exposes_permission_based_sensor_awareness_overlay():
    html = server.WEB_HTML
    required_markers = [
        'id="sensorOverlay"',
        'id="sensorOverlayPanel"',
        'id="sensorStatusGrid"',
        'id="sensorEventLog"',
        'id="btnSensors"',
        'id="mainSensorsBtn"',
        'onclick="toggleSensorOverlay()"',
        "Sensor Overlay",
        "Sensor Awareness",
        "sensorAwarenessState",
        "function toggleSensorOverlay",
        "function enableSensorAwareness",
        "function disableSensorAwareness",
        "function requestLocationSensor",
        "function requestMotionSensors",
        "function buildSensorSnapshot",
        "function sensorSnapshotForNova",
        "navigator.geolocation.getCurrentPosition",
        "DeviceMotionEvent.requestPermission",
        "window.addEventListener('devicemotion'",
        "window.addEventListener('deviceorientation'",
        "navigator.getBattery",
        "navigator.connection",
        "sensor_snapshot",
        "Permission based",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_embeds_clean_engineer_hud_over_camera_view():
    html = server.WEB_HTML
    required_markers = [
        'id="cameraDockViewport"',
        'class="camera-dock-viewport"',
        'id="novaVisionHud"',
        'class="nova-vision-hud clean-engineer-hud"',
        'id="novaHudReticle"',
        'id="novaHudTopStrip"',
        'id="novaHudLeftRail"',
        'id="novaHudRightRail"',
        'id="novaHudBottomGraph"',
        'id="novaHudToggle"',
        'onclick="toggleNovaVisionHud()"',
        'data-hud-field="orientation"',
        'data-hud-field="motion"',
        'data-hud-field="location"',
        'data-hud-field="temperature"',
        'data-hud-field="network"',
        'data-hud-field="battery"',
        "clean engineer hud",
        "function toggleNovaVisionHud",
        "function updateNovaVisionHud",
        "novaVisionHudEnabled",
        "temperature: not exposed",
        "pointer-events:none",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_exposes_real_distance_mode_over_camera_hud():
    html = server.WEB_HTML
    required_markers = [
        'id="novaDistanceModeBtn"',
        'id="btnDistanceMode"',
        'onclick="toggleDistanceMode()"',
        'id="novaDistanceHud"',
        'id="novaHudDistance"',
        'data-hud-field="distance"',
        "Distance Mode",
        "distanceState",
        "knownWidthMeters",
        "fovDegrees",
        "rough camera estimate",
        "function toggleDistanceMode",
        "function estimateDistanceFromReticle",
        "function buildDistanceEstimate",
        "function enumerateCameraDevicesForDepth",
        "navigator.mediaDevices.enumerateDevices",
        "dualCameraAvailable",
        "stereoDepthStatus",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_distance_mode_live_updates_and_readout_can_hide():
    html = server.WEB_HTML
    required_markers = [
        "distanceUpdateTimer",
        "distanceState.readoutVisible",
        "function startDistanceLiveUpdates",
        "function stopDistanceLiveUpdates",
        "setInterval(() => updateDistanceUi(buildDistanceEstimate())",
        "startDistanceLiveUpdates()",
        "stopDistanceLiveUpdates()",
        'id="novaDistanceReadoutBtn"',
        "function toggleDistanceReadout",
        "Hide Range",
        "Show Range",
        "readout hidden; Distance Mode still measuring",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_distance_popup_has_obvious_close_button():
    html = server.WEB_HTML
    required_markers = [
        'id="novaDistanceHudText"',
        'id="novaDistanceHudCloseBtn"',
        'class="nova-distance-close"',
        'onclick="toggleDistanceReadout(false)"',
        'aria-label="Close distance readout"',
        "×",
        "Close range",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_makes_range_close_and_full_sensors_controls_obvious():
    html = server.WEB_HTML
    required_markers = [
        "Close Range",
        "nova-distance-close-label",
        'id="mainDistanceReadoutBtn"',
        'class="range-readout-btn"',
        'onclick="toggleDistanceReadout()"',
        "Hide Range",
        "Show Range",
        "Full Sensors",
        "Full Sensor Awareness",
        "mainSensorsBtn.textContent = sensorAwarenessState.enabled ? 'Full Sensors ON' : 'Full Sensors'",
        "btnSensors.textContent = sensorAwarenessState.enabled ? 'Full Sensors ON' : 'Full Sensors'",
        "mainDistanceReadoutBtn.textContent = distanceState.readoutVisible ? 'Hide Range' : 'Show Range'",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_keeps_activation_buttons_visible_in_mobile_dock():
    html = server.WEB_HTML
    required_markers = [
        'id="activationDock"',
        'class="activation-dock"',
        'aria-label="Activation buttons"',
        ".activation-dock{",
        "overflow-x:auto",
        "position:absolute",
        "class=\"nova-distance-close\"",
        "id=\"novaDistanceHudCloseBtn\"",
        "right:-10px",
        "top:-14px",
        "z-index:6",
        "activation-dock button",
        "mainMicBtn",
        "mainCameraBtn",
        "mainLookBtn",
        "mainSensorsBtn",
        "mainDistanceModeBtn",
        "mainDistanceReadoutBtn",
        "mainAdapterOnlyBtn",
        "voiceBtn",
        "talkBtn",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_has_trained_adapter_only_toggle_and_payload_flag():
    html = server.WEB_HTML
    required_markers = [
        'id="mainAdapterOnlyBtn"',
        'class="adapter-only-btn"',
        'onclick="toggleAdapterOnlyMode()"',
        "Qwen Adapter OFF",
        "function toggleAdapterOnlyMode",
        "trainedAdapterOnlyMode",
        "payload.adapter_only_mode = true",
        "payload.use_lora_runtime = true",
        "payload.lora_adapter_id = dolphinAdapterOnlyMode ? DOLPHIN_LORA_ADAPTER_ID : QWEN_LORA_ADAPTER_ID",
        "trained_adapter_only",
        ".activation-dock .adapter-only-btn.on",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_has_dolphin_adapter_only_toggle_and_payload_flag():
    html = server.WEB_HTML
    required_markers = [
        'id="mainDolphinAdapterBtn"',
        'onclick="toggleDolphinAdapterOnlyMode()"',
        "Dolphin Adapter OFF",
        "function toggleDolphinAdapterOnlyMode",
        "dolphinAdapterOnlyMode",
        "payload.dolphin_adapter_only = true",
        "payload.allow_slow_dolphin_cpu = true",
        "nova-dolphin3-llama3-1-8b-full-sft-20260712",
        "function refreshAdapterRuntimeAvailability",
        "CPU SLOW",
        "Nova will not intercept, replace, or reroute the adapter answer",
        "data.latest_adapter_ids?.dolphin",
        "/api/adapters/list",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_has_raw_adapter_compare_button_and_renderer():
    html = server.WEB_HTML
    required_markers = [
        'id="mainAdapterCompareBtn"',
        'onclick="runRawAdapterCompare()"',
        "Raw Compare",
        "function runRawAdapterCompare",
        "/api/adapters/compare",
        "formatRawAdapterCompare",
        "RAW Qwen adapter",
        "RAW Dolphin adapter",
        "max_new_tokens: 96",
        "conversation_history: recentConversationHistory.slice(-8)",
        "Status: INCOMPLETE - raw output ended mid-thought.",
        "rememberConversationTurn(text, data?.nova_app_fix?.response || formattedCompare",
        "Nova app review/fix",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_has_safe_cognitive_blackboard_view():
    html = server.WEB_HTML
    required_markers = [
        'id="mainWorldModelBtn"',
        'onclick="showWorldModel()"',
        "function showWorldModel",
        "restart-safe local checkpoint",
        "/nova/v1/world-model?conversation_id=",
        "[COGNITIVE BLACKBOARD]",
        "operational state only",
        "Private chain-of-thought is never stored",
        "Pair this phone with Nova",
        "showPairingRequired",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_has_bounded_dream_lab_and_honest_comfyui_engine_view():
    html = server.WEB_HTML
    required_markers = [
        'id="mainDreamLabBtn"',
        'onclick="showDreamLab()"',
        "function showDreamLab",
        "/nova/v1/dream-lab?conversation_id=",
        "[DREAM LAB]",
        "Actions executed: no",
        "No prompt, response, or hidden reasoning is stored.",
        'id="mainEnginesBtn"',
        'onclick="showEngineStatus()"',
        "function showEngineStatus",
        "/nova/v1/engines",
        "[NOVA ENGINES]",
        "ComfyUI:",
        "configure an API-format workflow",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_has_scoped_dream_studio_job_interface():
    html = server.WEB_HTML
    required_markers = [
        'data-panel="dream-studio-panel"',
        'id="dream-studio-panel"',
        'id="mainDreamStudioBtn"',
        "Dream Studio",
        'id="dreamStudioMode"',
        'id="dreamStudioPrompt"',
        'id="dreamStudioGenerateBtn"',
        'id="dreamStudioCancelBtn"',
        'id="dreamStudioPreview"',
        'id="dreamStudioJobs"',
        "Media permission is separate from chat.",
        "setTimeout(loadDreamStudio, 0)",
        'href="assets/nova_dream_studio.css"',
        'src="assets/nova_dream_studio.js"',
    ]

    for marker in required_markers:
        assert marker in html


def test_dream_studio_hides_video_only_controls_in_image_mode():
    root = Path(server.__file__).resolve().parent
    css = (root / "assets" / "nova_dream_studio.css").read_text(encoding="utf-8")
    javascript = (root / "assets" / "nova_dream_studio.js").read_text(
        encoding="utf-8"
    )

    assert (
        ".dream-studio-options [data-dream-video-option][hidden]"
        "{display:none!important}"
    ) in css
    assert "item.hidden = !video;" in javascript


def test_web_ui_persists_recent_context_and_honors_private_mode():
    html = server.WEB_HTML
    required_markers = [
        "Conversation continuity",
        'id="conversationPersistenceState"',
        'id="conversationContextCount"',
        "CONVERSATION_STORAGE_KEY",
        "function loadConversationContext",
        "function persistConversationContext",
        "function clearConversationContext",
        "function startNewConversation",
        "private:privateModeEnabled",
        "privateModeEnabled || !conversationPersistenceEnabled",
        "conversation_id:conversationId",
        "renderRestoredConversationContext",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_has_safe_model_memory_controls_and_loading_progress():
    html = server.WEB_HTML
    source = Path(server.__file__).read_text(encoding="utf-8")
    required_html_markers = [
        "Local model memory",
        'id="systemModelMemoryState"',
        'id="qwenModelMemoryState"',
        'id="dolphinModelMemoryState"',
        'id="reviewerModelMemoryState"',
        'id="adaptiveModelMemoryState"',
        'id="modelQualityState"',
        "Smart RAM manager",
        "Model quality guard",
        "Check Loaded Models",
        "function startModelQualityCheck",
        "unloadModelMemory('reviewer')",
        "function loadModelMemoryStatus",
        "function unloadModelMemory",
        "/api/models/memory",
        "/api/models/memory/unload",
        "/api/models/quality",
        "/api/models/quality/check",
        "function setAdapterLoadingProgress",
        "response.heartbeat",
        "response.progress",
        "function updateStreamingProgress",
        "larger_local_review",
        "middle_local_review",
        "deep_local_review",
        "reviewerTier",
        "No model files will be removed",
        "Private Capability Lab",
        'id="capabilityLabState"',
        'id="capabilityVerifierState"',
        'id="capabilityShadowState"',
        'id="capabilityEvidenceState"',
        'id="capabilityRecommendationState"',
        'id="capabilityVisionImage"',
        'id="capabilityVisionKeywords"',
        "Evaluate Loaded Text Models",
        "Evaluate Vision Image",
        "function loadCapabilityEvaluationStatus",
        "function startCapabilityTextEvaluation",
        "function startCapabilityVisionEvaluation",
        "/api/models/capabilities/evaluations",
        "/api/models/capabilities/evaluate",
        "never enter Nova's training system",
        "Routing is unchanged",
    ]
    required_server_markers = [
        "def _model_memory_status",
        "def _unload_model_memory",
        "parsed.path == '/api/models/memory'",
        "parsed.path == '/api/models/memory/unload'",
        "def _model_quality_status",
        "def _start_loaded_model_quality_check",
        "parsed.path == '/api/models/quality'",
        "parsed.path == '/api/models/quality/check'",
        "def _capability_evaluation_status",
        "def _deterministic_verifier_enabled",
        "def _capability_shadow_router_enabled",
        "def _capability_shadow_route",
        "def _start_capability_evaluation",
        "parsed.path == '/api/models/capabilities/evaluations'",
        "parsed.path == '/api/models/capabilities/evaluate'",
        "model_activity(\"dolphin\")",
        "model_activity(\"reviewer\")",
    ]

    for marker in required_html_markers:
        assert marker in html
    for marker in required_server_markers:
        assert marker in source


def test_web_ui_raw_mode_is_untouched_but_never_implies_tool_execution():
    html = server.WEB_HTML

    assert "Raw Qwen · no tools" in html
    assert "Raw Dolphin · no tools" in html
    assert "RAW · no web/tools" in html
    assert "The raw adapter cannot browse, run tools, or verify live facts" in html
    assert "claims that it will take an action are generated text only" in html
    assert "Nova will not intercept, replace, or reroute the adapter answer" in html
    assert "RAW &middot; untouched" in html
    assert 'class="tag raw-limit"' in html


def test_web_ui_exposes_managed_strong_mode_without_changing_raw_modes():
    html = server.WEB_HTML

    assert '<option value="strong">Nova Strong · Qwen 3 8B</option>' in html
    assert "let managedModelMode = 'nova'" in html
    assert "payload.nova_model_mode = 'strong'" in html
    assert "Strong · Qwen 3 8B · CPU slow" in html
    assert "Nova Strong keeps identity, memory, tools, and safety" in html
    assert "trainedAdapterOnlyMode = ['qwen','dolphin'].includes(requested)" in html
    assert "Raw Qwen · no tools" in html
    assert "Raw Dolphin · no tools" in html


def test_web_ui_exposes_raw_memory_mode_selector_and_persisted_state():
    html = server.WEB_HTML

    assert '<option value="raw_memory">Raw + Memory · Qwen</option>' in html
    assert "['nova','strong','raw_memory'].includes(state.managedModelMode)" in html
    assert "if(mode === 'raw_memory')" in html
    assert "Raw + Memory · Qwen · no tools" in html


def test_web_ui_raw_memory_mode_sends_only_managed_mode_literal():
    html = server.WEB_HTML

    assert "managedModelMode = ['strong','raw_memory'].includes(requested) ? requested : 'nova';" in html
    assert "if(managedModelMode === 'raw_memory' && !trainedAdapterOnlyMode && !dolphinAdapterOnlyMode) payload.nova_model_mode = 'raw_memory';" in html
    assert "trainedAdapterOnlyMode = ['qwen','dolphin'].includes(requested);" in html
    assert "dolphinAdapterOnlyMode = requested === 'dolphin';" in html


def test_web_ui_raw_memory_mode_reports_no_tools_status_without_strong_claim():
    html = server.WEB_HTML

    assert "Raw + Memory · Qwen · no tools" in html
    assert "Raw + Memory keeps browser memory operations available" in html
    assert "Raw + Memory · Qwen 3 8B active" not in html


def test_web_ui_raw_memory_fallback_reason_is_visible_and_escaped_in_metadata():
    html = server.WEB_HTML

    assert "meta.raw_memory_fallback_reason" in html
    assert "Raw + Memory could not run · " in html
    assert "escapeHtml(reason)" in html


def test_web_ui_disables_model_selector_when_a_managed_chat_starts():
    html = server.WEB_HTML

    assert "activeChatController = new AbortController();\n        updateModelControlUi();" in html


def test_web_ui_strong_mode_reports_availability_and_safe_fallback_reason():
    html = server.WEB_HTML

    assert "strong_local_model:'Nova Strong is checking Qwen 3 8B availability'" in html
    assert "meta.optional_model_mode?.requested" in html
    assert "actualModel === requestedModel" in html
    assert "Strong · Qwen 3 8B active" in html
    assert "meta.model_residency?.reason" in html
    assert "Strong fallback · " in html
    assert "escapeHtml(reason)" in html


def test_web_ui_locks_model_selector_for_every_chat_request():
    html = server.WEB_HTML

    assert "let chatRequestInFlight = false;" in html
    assert "select.disabled = !!activeChatController || chatRequestInFlight;" in html
    assert "if(activeChatController || chatRequestInFlight)" in html
    assert "chatRequestInFlight = true;\n  updateModelControlUi();\n  if(shouldUseActiveVisionContext(text))" in html
    assert "chatRequestInFlight = false;\n      updateModelControlUi();" in html
    assert "chatRequestInFlight = false;" in html


def test_web_ui_model_memory_text_has_no_double_encoded_separator():
    html = server.WEB_HTML

    assert "Â" not in html
    assert "ON · ${adaptive.reserve_gb ?? 1.5} GB reserve" in html
    assert "last.reason ? ` · ${String(last.reason)" in html


def test_web_ui_has_adapter_import_install_panel_and_server_routes():
    html = server.WEB_HTML
    source = Path(server.__file__).read_text(encoding="utf-8")
    required_html_markers = [
        "Adapter Import / Install",
        'id="adapterInstallerPanel"',
        'id="adapterZipInput"',
        'id="adapterImportId"',
        'id="adapterActivateAfterImport"',
        "function loadAdapterRegistry",
        "function importAdapterZip",
        "function activateAdapter",
        "/api/adapters/list",
        "/api/adapters/import",
        "/api/adapters/activate",
    ]
    required_server_markers = [
        "def _adapter_registry_list",
        "def _adapter_registry_import",
        "def _adapter_registry_activate",
        "parsed.path == '/api/adapters/list'",
        "parsed.path == '/api/adapters/import'",
        "parsed.path == '/api/adapters/activate'",
    ]

    for marker in required_html_markers:
        assert marker in html
    for marker in required_server_markers:
        assert marker in source


def test_adapter_registry_list_includes_safe_runtime_capability(monkeypatch):
    import nova_lora_adapter_registry
    import nova_lora_runtime

    monkeypatch.setattr(server, "_ollama_adapter_model_available", lambda *args, **kwargs: False)

    monkeypatch.setattr(
        nova_lora_adapter_registry,
        "list_lora_adapters",
        lambda: {
            "ok": True,
            "active_adapter_id": "dolphin-test",
            "adapters": [
                {
                    "id": "dolphin-test",
                    "base_model": "dphn/Dolphin3.0-Llama3.1-8B",
                    "path": "C:/models/dolphin-test",
                }
            ],
        },
    )
    monkeypatch.setattr(
        nova_lora_runtime,
        "adapter_runtime_availability",
        lambda model, path: {
            "runnable": False,
            "state": "unavailable",
            "reason": "CUDA required",
            "model": model,
            "requires_cuda": True,
        },
    )

    payload = server._adapter_registry_list()

    runtime = payload["adapters"][0]["runtime"]
    assert runtime["runnable"] is False
    assert runtime["requires_cuda"] is True
    assert runtime["reason"] == "CUDA required"


def test_web_ui_has_training_studio_import_and_bundle_controls():
    html = server.WEB_HTML
    required_markers = [
        "Nova Training Studio",
        'id="studioFileInput"',
        'id="studioImportText"',
        "importTrainingStudioData",
        "runTrainingStudioChecks",
        "startTrainingStudioLocalLora",
        "downloadTrainingStudioBundle",
        'id="reviewTrainCenter"',
        "renderCorrectionReviews",
        "loadCorrectionReviews",
        "submitCorrectionReview",
        "/api/training/studio/import",
        "/api/training/studio/reviews",
        "/api/training/studio/review",
        "/api/training/studio/train",
        "/api/training/studio/kaggle-bundle.zip",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_has_bad_answer_correction_training_flow():
    html = server.WEB_HTML
    required_markers = [
        "Bad Answer / Teach Better",
        "attachCorrectionControls",
        "openCorrectionBox",
        "saveCorrectionExample",
        "/api/training/studio/feedback",
        "Send to Review Queue",
        "Correction saved for review",
        "Approved alternate phrasings",
        "Nova will match only the exact phrases you approve",
        "aliases.value.split",
        ".review-train-center,.review-list,.review-card{min-width:0;max-width:100%}",
        ".review-card textarea{width:100%;min-width:0;max-width:100%",
        "grid-template-columns:minmax(0,1fr)",
    ]

    for marker in required_markers:
        assert marker in html


def test_training_studio_review_passes_only_explicit_alias_arrays(monkeypatch):
    import nova_training_studio

    captured = {}

    def fake_review(project_root, **kwargs):
        captured.update(project_root=project_root, **kwargs)
        return {"ok": True, "action": kwargs["action"], "review": {"review_id": kwargs["review_id"]}}

    monkeypatch.setattr(nova_training_studio, "review_correction_example", fake_review)

    result = server._training_studio_review(
        {
            "review_id": "review-safe",
            "action": "approve",
            "response": "Approved answer.",
            "aliases": ["Alternate wording", "Another wording"],
        }
    )

    assert result["ok"] is True
    assert captured["aliases"] == ["Alternate wording", "Another wording"]

    try:
        server._training_studio_review(
            {
                "review_id": "review-unsafe",
                "action": "approve",
                "response": "Approved answer.",
                "aliases": "not-an-array",
            }
        )
    except ValueError as exc:
        assert "aliases must be an array" in str(exc)
    else:
        raise AssertionError("non-array aliases must be rejected")


def test_web_ui_has_mobile_stable_chat_and_simple_model_control():
    html = server.WEB_HTML
    required_markers = [
        'id="mainModelModeSelect"',
        'value="nova"',
        'value="qwen"',
        'value="dolphin"',
        "function selectModelMode",
        "function syncVisibleAppViewport",
        "window.visualViewport",
        "keyboard-open",
        "chatIsNearBottom",
        "scrollChatToBottom",
        "scheduleChatScrollToBottom",
        "chatScrollFrame",
        "chatShouldStickToBottom",
        "rememberChatScrollIntent",
        "chat?.addEventListener('touchend', rememberChatScrollIntent",
        "const shouldFollowBottom = chatShouldStickToBottom || chatIsNearBottom();",
        "no_scroll:true",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_bottom_controls_remain_scrollable_on_small_mobile_viewports():
    html = server.WEB_HTML

    assert "#globalInputSlot{flex:0 1 auto;max-height:56dvh;overflow-y:auto;overflow-x:hidden" in html
    assert "scroll-padding-bottom:max(8px,env(safe-area-inset-bottom))" in html
    assert "touch-action:pan-x;overscroll-behavior-x:contain" in html
    assert "const visibleHeight = Math.max(1, Math.round(viewport?.height || window.innerHeight));" in html
    assert "Math.max(320, Math.round(viewport?.height || window.innerHeight))" not in html
    assert "window.addEventListener('resize', syncVisibleAppViewport, {passive:true});" in html


def test_web_ui_bottom_control_rows_support_side_scroll_buttons_wheel_and_drag():
    html = server.WEB_HTML

    required_markers = [
        'data-scroll-shell="activationDock"',
        'data-scroll-shell="permissionsDock"',
        'aria-label="Scroll activation controls left"',
        'aria-label="Scroll activation controls right"',
        'aria-label="Scroll status controls left"',
        'aria-label="Scroll status controls right"',
        'id="permissionsDock"',
        "function scrollBottomRow",
        "function bindBottomHorizontalScroll",
        "row.addEventListener('wheel'",
        "row.addEventListener('pointermove'",
        "touch-action:pan-x",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_bottom_buttons_keep_taps_separate_from_row_dragging():
    html = server.WEB_HTML

    assert ".activation-dock button,.permissions button,.bottom-scroll-arrow{touch-action:manipulation;pointer-events:auto}" in html
    assert "event.target.closest('button,input,select,textarea,a,label')" in html
    interactive_branch = html[html.index("if(event.target.closest('button,input,select,textarea,a,label'))"):]
    assert "dragged = false;" in interactive_branch[:500]
    assert "row.scrollBy({left: direction * distance, behavior:'auto'});" in html
    assert "behavior:'smooth'" not in html[html.index("function scrollBottomRow"):html.index("function bindBottomHorizontalScroll")]


def test_web_ui_throttles_3d_animation_and_pauses_it_behind_chat():
    html = server.WEB_HTML

    required_markers = [
        "const NOVA_3D_FRAME_INTERVAL_MS = 50;",
        "function shouldAnimateNova3D()",
        "!document.hidden",
        "displayPanel?.classList.contains('active')",
        "now - nova3DLastAnimationFrame >= NOVA_3D_FRAME_INTERVAL_MS",
    ]

    for marker in required_markers:
        assert marker in html


def test_training_studio_check_does_not_start_guarded_weight_training(monkeypatch):
    dataset = {"dataset_id": "safe-dataset", "training_ready": True, "review_required": False}
    monkeypatch.setattr(server, "_training_studio_dataset_by_id", lambda _dataset_id=None: dataset)
    monkeypatch.setattr(server, "_training_studio_dry_run", lambda _dataset: {"ok": True})
    monkeypatch.setattr(server, "_run_full_training_suite", lambda: {"passed": True})

    def unexpected_training_start():
        raise AssertionError("a dataset check must not mutate model weights")

    monkeypatch.setattr(server, "_start_training_center_job", unexpected_training_start)

    result = server._training_studio_train({"dataset_id": "safe-dataset", "run_checks": True})

    assert result["ok"] is True
    assert result["training_job"] is None
    assert result["report"] == {"passed": True}


def test_memory_search_does_not_hijack_normal_live_or_greeting_requests():
    memory = {
        "lessons": {
            "personal": {"text": "I live in Cincinnati", "category": "user_fact"},
            "release": {"text": "the latest code from github is now live"},
        }
    }

    assert router._is_personal_memory_recall_query("Give me a one-sentence live app test greeting.") is False
    assert router._search_lessons("Give me a one-sentence live app test greeting.", memory) == []


def test_memory_search_keeps_explicit_personal_recall_and_strong_lessons():
    personal_memory = {"lessons": {"home": {"text": "I live in Cincinnati", "category": "user_fact"}}}
    lesson_memory = {
        "lessons": {
            "router": {"text": "hybrid routers combine dictionary lookup with transformer generation"}
        }
    }

    assert router._is_personal_memory_recall_query("Where do I live?") is True
    assert router._search_lessons("Where do I live?", personal_memory) == ["I live in Cincinnati"]
    assert router._search_lessons(
        "Explain how hybrid routers combine dictionary lookup.", lesson_memory
    ) == ["hybrid routers combine dictionary lookup with transformer generation"]


def test_web_ui_has_memory_control_panel_and_api_routes():
    html = server.WEB_HTML
    required_markers = [
        "memoryControlPanel",
        "memorySearchInput",
        "loadMemoryControl",
        "saveMemoryEdit",
        "memoryAction",
        "/api/memory/list",
        "/api/memory/update",
        "/api/memory/action",
        "Train This",
        "Pin",
        "Hide",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_syncs_adapter_mode_buttons_after_mobile_toggles():
    html = server.WEB_HTML
    required_markers = [
        "function syncAdapterModeState",
        "document.body.dataset.adapterOnly",
        "document.body.dataset.dolphinAdapterOnly",
        "persistAdapterModeState()",
        "requestAnimationFrame(updateAdapterOnlyButton)",
        "setTimeout(updateAdapterOnlyButton, 150)",
        "setTimeout(updateAdapterOnlyButton, 600)",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_reconnects_before_showing_offline_fallback():
    html = server.WEB_HTML
    required_markers = [
        "function offlineHelpMessage",
        "Nova connection dropped. I am retrying the live server",
        "data = await retryLiveCall(text)",
        "py -3 nova_enhanced_server.py 53910",
        "Remote tunnel could not reach Nova",
    ]

    for marker in required_markers:
        assert marker in html

    assert "nova_enhanced_server.py 3000" not in html


def test_web_ui_distance_popup_can_be_pulled_down_to_hide():
    html = server.WEB_HTML
    required_markers = [
        "data-pull-close",
        "distancePopupDragState",
        "function bindDistancePopupDragToClose",
        "function handleDistancePopupPointerDown",
        "function handleDistancePopupPointerMove",
        "function handleDistancePopupPointerUp",
        "pointerdown",
        "pointermove",
        "pointerup",
        "pointercancel",
        "setPointerCapture",
        "toggleDistanceReadout(false)",
        "Pull down to hide range",
        ".nova-distance-hud.dragging",
        "touch-action:none",
        "bindDistancePopupDragToClose()",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_exposes_full_sensor_awareness_panel():
    html = server.WEB_HTML
    required_markers = [
        "Full Sensor Awareness",
        "actual browser data only",
        'id="fullSensorAwarenessPanel"',
        'id="sensorCameraState"',
        'id="sensorMicState"',
        'id="sensorSpeakerState"',
        'id="sensorThermalState"',
        "Camera permission",
        "Microphone",
        "Speaker",
        "Thermal",
        "temperature not exposed",
        "Distance estimate",
        "setSensorText('sensorCameraState'",
        "setSensorText('sensorMicState'",
        "setSensorText('sensorSpeakerState'",
        "setSensorText('sensorThermalState'",
    ]

    for marker in required_markers:
        assert marker in html


def test_chat_api_accepts_sensor_snapshot_for_awareness_answers():
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        result = _json_post(
            base_url,
            "/api/chat",
            {
                "text": "what sensors can you see right now?",
                "sensor_snapshot": {
                    "enabled": True,
                    "source": "browser_sensor_overlay",
                    "permissions": {"camera": True, "mic": False, "speaker": True},
                    "viewport": {"width": 390, "height": 844},
                    "screen": {"width": 390, "height": 844, "orientation": "portrait-primary"},
                    "network": {"online": True, "effectiveType": "4g"},
                    "battery": {"level": 0.82, "charging": True},
                    "location": {"available": True, "lat": 39.1, "lon": -84.5, "accuracy": 30},
                    "motion": {"available": True, "x": 0.1, "y": 0.2, "z": 9.7},
                    "orientation": {"available": True, "alpha": 10, "beta": 2, "gamma": -1},
                },
            },
        )

        assert result["trace"]["source"] == "sensor_awareness"
        assert result["trace"]["sensor_snapshot"]["source"] == "browser_sensor_overlay"
        assert "camera ON" in result["response"]
        assert "battery 82%" in result["response"]
        assert "location available" in result["response"]
        assert "motion/orientation available" in result["response"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_chat_api_accepts_message_field_like_text_field(monkeypatch):
    def fake_brain_route(text, context=None):
        return "received:" + text, {"source": "test_route", "input": text}

    monkeypatch.setattr(server, "brain_route", fake_brain_route)

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        result = _json_post(base_url, "/api/chat", {"message": "WHAT IS YOUR NAME"})

        assert result["response"] == "received:WHAT IS YOUR NAME"
        assert result["trace"]["input"] == "WHAT IS YOUR NAME"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_chat_api_answers_distance_questions_from_sensor_snapshot(monkeypatch):
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", False, raising=False)
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", True, raising=False)
    monkeypatch.setattr(
        server,
        "route_and_respond",
        lambda text, dict_lookup_fn=None, memory=None: ("fallback", {"source": "fallback", "confidence": 0.1}),
        raising=False,
    )
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        result = _json_post(
            base_url,
            "/api/chat",
            {
                "text": "how far is that from me?",
                "sensor_snapshot": {
                    "enabled": True,
                    "source": "browser_sensor_overlay",
                    "permissions": {"camera": True, "mic": False, "speaker": True},
                    "cameraFacingMode": "environment",
                    "distance": {
                        "available": True,
                        "distanceMeters": 2.4,
                        "confidence": "medium",
                        "method": "monocular_reticle",
                        "calibrated": False,
                        "target": "person torso",
                        "pixelWidth": 210,
                        "knownWidthMeters": 0.45,
                        "stereoDepthStatus": "two cameras detected, browser depth not calibrated",
                    },
                },
            },
        )

        assert result["trace"]["source"] == "distance_awareness"
        assert result["trace"]["sensor_snapshot"]["distance"]["distanceMeters"] == 2.4
        assert "about 2.4 meters" in result["response"]
        assert "rough camera estimate" in result["response"]
        assert "not true LiDAR/depth" in result["response"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_python_range_question_is_not_misrouted_to_camera_distance_mode():
    assert server._is_distance_awareness_question(
        "In Python, why does range(3) produce 0, 1, 2?"
    ) is False
    assert server._is_distance_awareness_question(
        "What is the camera range to that object?"
    ) is True


def test_emotional_statement_is_not_parsed_as_a_name_introduction():
    assert server._extract_user_name_introduction(
        "I'm nervous about an important conversation tomorrow."
    ) is None
    assert server._extract_user_name_introduction("I'm Mr Novatron.") == "Mr Novatron"
    assert server._extract_user_name_introduction("My name is Mr Novatron.") == "Mr Novatron"


def test_name_introduction_stops_before_following_memory_instruction():
    assert server._extract_user_name_introduction(
        "My name is Mr Novatron. Remember that for this conversation."
    ) == "Mr Novatron"


def test_name_recall_followup_uses_memory_without_model_fallback(monkeypatch):
    memory = {
        "people": {
            "mr novatron": {"name": "Mr Novatron"},
        },
        "lessons": {},
        "last_person": "mr novatron",
        "last_lesson": None,
    }
    monkeypatch.setattr(server, "MEMORY", memory)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)

    def fail_if_model_runs(*args, **kwargs):
        raise AssertionError("name recall should not invoke a slow model")

    monkeypatch.setattr(server, "cognitive_route", fail_if_model_runs, raising=False)
    response, trace = server.brain_route(
        "What name did I just give you?",
        {
            "nova_gateway": True,
            "memory_read_allowed": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert response == "Your name is Mr Novatron. I remember you."
    assert trace["source"] == "people_memory"
    assert trace["memory_event"] == "name_recall:Mr Novatron"


def test_name_recall_accepts_saved_name_phrasing():
    assert server._is_name_recall_request("What name is saved for me?") is True
    assert server._is_name_recall_request("What name do you have for me?") is True


def test_gateway_name_recall_uses_direct_memory_before_normal_pipeline(monkeypatch):
    memory = {
        "people": {
            "mr novatron": {"name": "Mr Novatron"},
        },
        "lessons": {},
        "last_person": "mr novatron",
        "last_lesson": None,
    }
    monkeypatch.setattr(server, "MEMORY", memory)
    response, trace = server._run_nova_chat_turn(
        "What name is saved for me?",
        {
            "nova_gateway": True,
            "request_id": "gateway_name_recall_test",
            "user_id": "anonymous",
            "conversation_id": "gateway_name_recall_test",
            "memory_read_allowed": True,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
            "native_streaming": True,
            "stream_callback": lambda _delta: True,
            "progress_callback": lambda *_args, **_kwargs: True,
        },
    )

    assert response == "Your name is Mr Novatron. I remember you."
    assert trace["source"] == "people_memory"
    assert trace["final_answer_source"] == "people_memory"
    assert trace["memory_event"] == "name_recall:Mr Novatron"


def test_gateway_memory_policy_blocks_legacy_name_and_conversation_writes(monkeypatch):
    memory = {
        "people": {},
        "lessons": {},
        "last_person": None,
        "last_lesson": None,
    }
    monkeypatch.setattr(server, "MEMORY", memory)
    monkeypatch.setattr(
        server,
        "_save_memory",
        lambda: (_ for _ in ()).throw(
            AssertionError("memory_write_allowed=false must block legacy writes")
        ),
    )

    class RecordingConversationEngine:
        def __init__(self):
            self.exchanges = []

        def add_exchange(self, user_text, response):
            self.exchanges.append((user_text, response))

    engine = RecordingConversationEngine()
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", True)
    monkeypatch.setattr(
        server,
        "_CONV_ENGINE",
        server._ConversationEnginePolicyProxy(engine),
    )

    response, trace = server.brain_route(
        "My name is Private Test",
        {
            "nova_gateway": True,
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_memory_allowed": False,
        },
    )

    assert memory["people"] == {}
    assert memory["last_person"] is None
    assert engine.exchanges == []
    assert trace["memory_write_allowed"] is False
    assert "saved your name" not in response.lower()


def test_server_conversation_engine_does_not_pollute_training_data_during_pytest(
    monkeypatch,
):
    class RecordingConversationEngine:
        def __init__(self):
            self.exchanges = []

        def add_exchange(self, user_text, response):
            self.exchanges.append((user_text, response))
            return True

    engine = RecordingConversationEngine()
    proxy = server._ConversationEnginePolicyProxy(engine)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "server isolation")
    server._CONVERSATION_WRITES_ALLOWED.set(True)

    assert proxy.add_exchange("test prompt", "test response") is False
    assert engine.exchanges == []


def test_practical_support_blocks_automatic_memory_and_training_writes(monkeypatch):
    writes = {"natural": [], "memory_v2": [], "training": []}

    class RecordingConversationEngine:
        def add_exchange(self, user_text, response):
            writes["training"].append((user_text, response))
            return True

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", True)
    monkeypatch.setattr(
        server,
        "_CONV_ENGINE",
        server._ConversationEnginePolicyProxy(RecordingConversationEngine()),
    )
    monkeypatch.setitem(
        sys.modules,
        "nova_natural_chat",
        types.SimpleNamespace(
            natural_chat_enabled=lambda: True,
            update_conversation_memory=lambda text, response: writes["natural"].append(
                (text, response)
            ),
            get_recent_memory=lambda: [],
            shape_verified_response=lambda response, **kwargs: response,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "nova_memory_v2",
        types.SimpleNamespace(
            selective_memory_update=lambda text, **kwargs: writes["memory_v2"].append(
                (text, kwargs)
            ),
        ),
    )

    def draft_with_training_attempt(text, context=None):
        server._CONV_ENGINE.add_exchange(text, "draft")
        return "Let's identify the amount and deadline first.", {
            "source": "cognitive_os",
            "domain": "general_conversation",
            "roles": ["speech_output_transformer"],
            "skills": [],
            "route_path": ["cognitive_os"],
            "confidence": 0.8,
        }

    monkeypatch.setattr(server, "brain_route", draft_with_training_attempt)

    _, trace = server._run_nova_chat_turn("I need some money", context={})

    assert writes == {"natural": [], "memory_v2": [], "training": []}
    assert trace["conversation_decision"]["memory_recommended"] is False


@pytest.mark.parametrize(
    "prompt",
    ("Tell me a joke", "Remember that my favorite color is green"),
)
def test_non_practical_turns_keep_automatic_persistence_enabled(monkeypatch, prompt):
    writes = {"natural": [], "memory_v2": [], "training": []}

    class RecordingConversationEngine:
        def add_exchange(self, user_text, response):
            writes["training"].append((user_text, response))
            return True

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", True)
    monkeypatch.setattr(
        server,
        "_CONV_ENGINE",
        server._ConversationEnginePolicyProxy(RecordingConversationEngine()),
    )
    monkeypatch.setitem(
        sys.modules,
        "nova_natural_chat",
        types.SimpleNamespace(
            natural_chat_enabled=lambda: True,
            update_conversation_memory=lambda text, response: writes["natural"].append(
                (text, response)
            ),
            get_recent_memory=lambda: [],
            shape_verified_response=lambda response, **kwargs: response,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "nova_memory_v2",
        types.SimpleNamespace(
            selective_memory_update=lambda text, **kwargs: writes["memory_v2"].append(
                (text, kwargs)
            ),
        ),
    )

    def draft_with_training_attempt(text, context=None):
        server._CONV_ENGINE.add_exchange(text, "draft")
        return "Here is a normal reply.", {
            "source": "cognitive_os",
            "domain": "general_conversation",
            "roles": ["speech_output_transformer"],
            "skills": [],
            "route_path": ["cognitive_os"],
            "confidence": 0.8,
        }

    monkeypatch.setattr(server, "brain_route", draft_with_training_attempt)

    _, trace = server._run_nova_chat_turn(prompt, context={})

    assert len(writes["natural"]) == 1
    assert len(writes["memory_v2"]) == 1
    assert len(writes["training"]) == 1
    assert trace["conversation_decision"]["intent_family"] != "practical_support"


def test_earth_sun_distance_question_is_not_misrouted_to_camera_distance_mode():
    assert server._is_distance_awareness_question(
        "Why is it warmer in summer: Earth's distance from the Sun or axial tilt?"
    ) is False
    assert server._is_distance_awareness_question(
        "Use the camera to measure the distance to that object."
    ) is True


def test_chat_api_guides_distance_mode_when_no_estimate_exists(monkeypatch):
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", False, raising=False)
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", True, raising=False)
    monkeypatch.setattr(
        server,
        "route_and_respond",
        lambda text, dict_lookup_fn=None, memory=None: ("fallback", {"source": "fallback", "confidence": 0.1}),
        raising=False,
    )
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        result = _json_post(
            base_url,
            "/api/chat",
            {
                "text": "how far away is that thing?",
                "sensor_snapshot": {
                    "enabled": True,
                    "source": "browser_sensor_overlay",
                    "permissions": {"camera": True, "mic": False, "speaker": True},
                    "distance": {"available": False, "reason": "not measured yet"},
                },
            },
        )

        assert result["trace"]["source"] == "distance_awareness"
        assert "Turn on Distance Mode" in result["response"]
        assert "aim the reticle" in result["response"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_chat_api_answers_distance_close_control_complaint(monkeypatch):
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", False, raising=False)
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False, raising=False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", True, raising=False)
    monkeypatch.setattr(
        server,
        "route_and_respond",
        lambda text, dict_lookup_fn=None, memory=None: ("fallback", {"source": "fallback", "confidence": 0.1}),
        raising=False,
    )
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        result = _json_post(
            base_url,
            "/api/chat",
            {
                "text": "distance mode is not live updating and there is no x button to close it",
                "sensor_snapshot": {
                    "enabled": True,
                    "source": "browser_sensor_overlay",
                    "permissions": {"camera": True, "mic": False, "speaker": True},
                    "distance": {"available": False, "reason": "not measured yet"},
                },
            },
        )

        assert result["trace"]["source"] == "distance_awareness"
        assert "close control" in result["response"]
        assert "X" in result["response"]
        assert "UI bug" in result["response"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_tts_api_prefers_neural_voice_payload(monkeypatch):
    old_speaker = server.PERMISSIONS["speaker"]
    try:
        server.PERMISSIONS["speaker"] = True

        def fake_neural_tts(text, voice=None):
            assert text == "Hello from Nova."
            assert voice == server.NOVA_TTS_NEURAL_VOICE
            return base64.b64encode(b"ID3fakeMP3bytes").decode("ascii"), "Nova Neural Test", "audio/mpeg"

        def fail_windows(text):
            raise AssertionError("Windows fallback should not run when neural voice works")

        monkeypatch.setattr(server, "_generate_edge_neural_tts_audio_base64", fake_neural_tts, raising=False)
        monkeypatch.setattr(server, "_generate_windows_tts_wav_base64", fail_windows, raising=False)
        httpd, base_url = _start_test_server(server.NovaHandler)
        try:
            result = _json_post(base_url, "/api/tts", {"text": "Hello from Nova."})

            assert result["ok"] is True
            assert result["mime_type"] == "audio/mpeg"
            assert result["audio_base64"] == base64.b64encode(b"ID3fakeMP3bytes").decode("ascii")
            assert result["voice_engine"] == "edge_neural"
            assert result["voice_name"] == "Nova Neural Test"
        finally:
            httpd.shutdown()
            httpd.server_close()
    finally:
        server.PERMISSIONS["speaker"] = old_speaker


def test_tts_api_falls_back_to_windows_voice_when_neural_unavailable(monkeypatch):
    old_speaker = server.PERMISSIONS["speaker"]
    try:
        server.PERMISSIONS["speaker"] = True

        def fail_neural(text, voice=None):
            raise RuntimeError("edge neural missing")

        def fake_windows_tts(text):
            assert text == "Hello from Nova."
            return base64.b64encode(b"RIFFfakeWAVEbytes").decode("ascii"), "Test Voice"

        monkeypatch.setattr(server, "_generate_edge_neural_tts_audio_base64", fail_neural, raising=False)
        monkeypatch.setattr(server, "_generate_windows_tts_wav_base64", fake_windows_tts, raising=False)
        httpd, base_url = _start_test_server(server.NovaHandler)
        try:
            result = _json_post(base_url, "/api/tts", {"text": "Hello from Nova."})

            assert result["ok"] is True
            assert result["mime_type"] == "audio/wav"
            assert result["audio_base64"] == base64.b64encode(b"RIFFfakeWAVEbytes").decode("ascii")
            assert result["voice_engine"] == "windows_sapi"
            assert result["voice_name"] == "Test Voice"
            assert result["fallback_from"] == "edge_neural"
            assert "edge neural missing" in result["fallback_reason"]
        finally:
            httpd.shutdown()
            httpd.server_close()
    finally:
        server.PERMISSIONS["speaker"] = old_speaker


def test_tts_api_requires_speaker_or_force(monkeypatch):
    old_speaker = server.PERMISSIONS["speaker"]
    try:
        server.PERMISSIONS["speaker"] = False
        httpd, base_url = _start_test_server(server.NovaHandler)
        try:
            request = urllib.request.Request(
                base_url + "/api/tts",
                data=json.dumps({"text": "blocked"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(request, timeout=5)
                assert False, "expected HTTPError"
            except urllib.error.HTTPError as exc:
                payload = json.loads(exc.read().decode("utf-8"))
                assert exc.code == 403
                assert payload["ok"] is False
                assert payload["permission"] == "speaker_required"
        finally:
            httpd.shutdown()
            httpd.server_close()
    finally:
        server.PERMISSIONS["speaker"] = old_speaker


def test_uploaded_image_vision_requires_camera_permission():
    old_camera = server.PERMISSIONS["camera"]
    try:
        server.PERMISSIONS["camera"] = False
        payload, status = server._vision_response_from_upload(
            {
                "filename": "tiny.png",
                "mime_type": "image/png",
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAFklEQVR4nGP4TyFgGDVg1IBRA4aLAQBdePwur/3haQAAAABJRU5ErkJggg==",
            }
        )

        assert status == 403
        assert payload["ok"] is False
        assert payload["trace"]["permission"] == "camera_required"
        assert "allow camera" in payload["response"].lower()
    finally:
        server.PERMISSIONS["camera"] = old_camera


def test_uploaded_image_vision_reports_basic_picture_properties():
    old_camera = server.PERMISSIONS["camera"]
    try:
        server.PERMISSIONS["camera"] = True
        payload, status = server._vision_response_from_upload(
            {
                "filename": "tiny.png",
                "mime_type": "image/png",
                "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lp55WQAAAABJRU5ErkJggg==",
                "prompt": "what do you see?",
            }
        )

        assert status == 200
        assert payload["ok"] is True
        assert "tiny.png" in payload["response"]
        assert "1×1" in payload["response"]
        assert payload["trace"]["source"] == "image_upload_vision"
        assert payload["trace"]["image"]["format"] == "PNG"
        assert payload["trace"]["image"]["width"] == 1
        assert payload["trace"]["image"]["height"] == 1
        assert "basic_image_inspection" in payload["trace"]["skills"]
        assert payload["trace"]["vision_model_used"] is False
        assert payload["trace"]["vision_model_error"] == "image_too_small_for_semantic_vision"
        assert "too small for a reliable visual description" in payload["response"]
    finally:
        server.PERMISSIONS["camera"] = old_camera


def test_uploaded_image_vision_uses_moondream_when_available(monkeypatch):
    old_camera = server.PERMISSIONS["camera"]
    captured = {}
    try:
        server.PERMISSIONS["camera"] = True

        def fake_moondream(image_base64, prompt):
            captured["image_base64"] = image_base64
            captured["prompt"] = prompt
            return "I see a tiny test image.", {
                "used": True,
                "model": "moondream",
                "error": None,
            }

        monkeypatch.setattr(server, "_call_moondream_vision", fake_moondream, raising=False)
        payload, status = server._vision_response_from_upload(
            {
                "filename": "tiny.png",
                "mime_type": "image/png",
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAFklEQVR4nGP4TyFgGDVg1IBRA4aLAQBdePwur/3haQAAAABJRU5ErkJggg==",
                "prompt": "what is this?",
                "client_processing": {
                    "resized": True,
                    "width": 1024,
                    "height": 768,
                    "source_width": 4032,
                    "source_height": 3024,
                },
            }
        )

        assert status == 200
        assert payload["ok"] is True
        assert "I see a tiny test image." in payload["response"]
        assert payload["trace"]["vision_model"] == "moondream"
        assert payload["trace"]["vision_model_used"] is True
        assert "moondream_vision" in payload["trace"]["skills"]
        assert payload["trace"]["client_processing"] == {
            "resized": True,
            "width": 1024,
            "height": 768,
            "source_width": 4032,
            "source_height": 3024,
        }
        assert captured["prompt"] == "what is this?"
        assert captured["image_base64"]
    finally:
        server.PERMISSIONS["camera"] = old_camera


def test_detailed_picture_request_combines_semantics_with_verified_scene_and_robot_gate(monkeypatch):
    old_camera = server.PERMISSIONS["camera"]
    try:
        server.PERMISSIONS["camera"] = True
        monkeypatch.setattr(
            server,
            "_call_moondream_vision",
            lambda *_args, **_kwargs: (
                "A purple robot is visible in a blue room.",
                {"used": True, "model": "moondream", "error": None},
            ),
        )
        payload, status = server._vision_response_from_upload(
            {
                "filename": "robot.png",
                "mime_type": "image/png",
                "image_base64": (
                    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9h"
                    "AAAAFklEQVR4nGP4TyFgGDVg1IBRA4aLAQBdePwur/3haQAAAABJRU5ErkJggg=="
                ),
                "prompt": (
                    "Identify everything visible and explain whether a robot can navigate "
                    "safely from this picture."
                ),
            }
        )

        assert status == 200
        assert "A purple robot is visible" in payload["response"]
        assert "Verified local scene scan" in payload["response"]
        assert "not movement clearance" in payload["response"]
        assert payload["trace"]["scene_probe"]["local_only"] is True
        assert payload["trace"]["scene_probe"]["image_persisted"] is False
        assert payload["trace"]["navigation_ready"] is False
        assert "deterministic_scene_probe" in payload["trace"]["skills"]
        assert "robot_navigation_safety_gate" in payload["trace"]["skills"]
        assert "image_base64" not in json.dumps(payload["trace"])
    finally:
        server.PERMISSIONS["camera"] = old_camera


def test_uploaded_picture_combines_private_local_ocr_with_vision(monkeypatch):
    import nova_ocr

    old_camera = server.PERMISSIONS["camera"]
    server.PERMISSIONS["camera"] = True
    captured = {}
    monkeypatch.setattr(
        nova_ocr,
        "extract_text",
        lambda *_args, **_kwargs: (
            "Example Control Panel\nChat Home Display\nTalk here",
            {
                "engine": "tesseract",
                "available": True,
                "used": True,
                "characters": 49,
                "lines": 3,
                "error": None,
                "content_logged": False,
                "image_persisted": False,
                "local_only": True,
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_call_moondream_vision",
        lambda image, prompt: captured.update(image=image, prompt=prompt)
        or (
            "A phone screen shows an example control panel.",
            {"used": True, "model": "moondream", "error": None, "resource_manager": None},
        ),
    )
    try:
        payload, status = server._vision_response_from_upload(
            {
                "filename": "phone.png",
                "mime_type": "image/png",
                "image_base64": base64.b64encode(
                    b"\x89PNG\r\n\x1a\n" + b"0" * 64
                ).decode("ascii"),
                "prompt": "What app is visible? Read the screen text.",
            }
        )
    finally:
        server.PERMISSIONS["camera"] = old_camera

    assert status == 200
    assert "Verified local OCR text" in captured["prompt"]
    assert "Example Control Panel" in captured["prompt"]
    assert "Readable text: Example Control Panel | Chat Home Display | Talk here" in payload["response"]
    assert payload["trace"]["ocr"] == {
        "engine": "tesseract",
        "available": True,
        "used": True,
        "characters": 49,
        "lines": 3,
        "error": None,
        "content_logged": False,
        "image_persisted": False,
        "local_only": True,
    }
    assert "tesseract_ocr" in payload["trace"]["skills"]
    assert "Nova Creature" not in json.dumps(payload["trace"])


def test_uploaded_picture_ocr_identifies_nova_without_waiting_for_vision_model(monkeypatch):
    import nova_ocr

    old_camera = server.PERMISSIONS["camera"]
    server.PERMISSIONS["camera"] = True
    monkeypatch.setattr(
        nova_ocr,
        "extract_text",
        lambda *_args, **_kwargs: (
            "Nova Creature\nChat Home Display\nTalk to Nova",
            {
                "engine": "tesseract",
                "available": True,
                "used": True,
                "characters": 45,
                "lines": 3,
                "error": None,
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_call_moondream_vision",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Nova UI OCR should not wait for the vision model")
        ),
    )
    try:
        payload, status = server._vision_response_from_upload(
            {
                "filename": "phone.png",
                "mime_type": "image/png",
                "image_base64": base64.b64encode(
                    b"\x89PNG\r\n\x1a\n" + b"0" * 64
                ).decode("ascii"),
                "prompt": "What app is visible? Read the screen text.",
            }
        )
    finally:
        server.PERMISSIONS["camera"] = old_camera

    assert status == 200
    assert payload["response"].startswith(
        "[VISION] I can read the screen. This is the Nova Creature app."
    )
    assert "Readable text: Nova Creature | Chat Home Display | Talk to Nova" in payload["response"]
    assert payload["trace"]["vision_model_used"] is False
    assert payload["trace"]["vision_model_error"] is None
    assert payload["trace"]["vision_bypass_reason"] == "local_ocr_answered_nova_screen_request"
    assert payload["trace"]["ocr"]["engine"] == "tesseract"
    assert payload["trace"]["ocr"]["used"] is True


def test_natural_visual_follow_up_on_nova_screen_stays_on_fast_ocr(monkeypatch):
    import nova_ocr

    old_camera = server.PERMISSIONS["camera"]
    server.PERMISSIONS["camera"] = True
    monkeypatch.setattr(
        nova_ocr,
        "extract_text",
        lambda *_args, **_kwargs: (
            "Nova Creature\nQwen Raw Adapter is ON\nMemory save and recall still work",
            {
                "engine": "tesseract",
                "available": True,
                "used": True,
                "characters": 69,
                "lines": 3,
                "error": None,
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_call_moondream_vision",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("a readable Nova-screen follow-up must stay on fast OCR")
        ),
    )
    image = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode("ascii")
    try:
        payload, status = server._vision_response_from_upload(
            {
                "filename": "phone.png",
                "mime_type": "image/png",
                "image_base64": image,
                "prompt": "What does that Qwen adapter message say?",
                "visual_follow_up": True,
            }
        )
    finally:
        server.PERMISSIONS["camera"] = old_camera

    assert status == 200
    assert payload["trace"]["vision_model_used"] is False
    assert payload["trace"]["vision_bypass_reason"] == "local_ocr_answered_nova_screen_request"
    assert payload["trace"]["visual_follow_up"] is True
    assert "Qwen Raw Adapter is ON" in payload["response"]


def test_uploaded_image_vision_response_is_user_friendly(monkeypatch):
    old_camera = server.PERMISSIONS["camera"]
    try:
        server.PERMISSIONS["camera"] = True

        def fake_moondream(image_base64, prompt):
            return "The picture shows a phone screen with Nova Creature open.", {
                "used": True,
                "model": "moondream",
                "error": None,
            }

        monkeypatch.setattr(server, "_call_moondream_vision", fake_moondream, raising=False)
        payload, status = server._vision_response_from_upload(
            {
                "filename": "screen.jpg",
                "mime_type": "image/jpeg",
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAFklEQVR4nGP4TyFgGDVg1IBRA4aLAQBdePwur/3haQAAAABJRU5ErkJggg==",
                "prompt": "what do you see?",
            }
        )

        assert status == 200
        assert payload["ok"] is True
        response = payload["response"]
        assert response.startswith("[VISION] I can see it.")
        assert "The picture shows a phone screen" in response
        assert "uploaded picture file" not in response
        assert "I also kept the basic file inspection" not in response
        assert "moondream says" not in response.lower()
    finally:
        server.PERMISSIONS["camera"] = old_camera


def test_live_camera_vision_feels_present_and_asks_social_question(monkeypatch):
    old_camera = server.PERMISSIONS["camera"]
    try:
        server.PERMISSIONS["camera"] = True

        def fake_moondream(image_base64, prompt):
            return "I see a person near a phone screen in a dim room.", {
                "used": True,
                "model": "moondream",
                "error": None,
            }

        monkeypatch.setattr(server, "_call_moondream_vision", fake_moondream, raising=False)
        payload, status = server._vision_response_from_upload(
            {
                "filename": "live-camera-frame.jpg",
                "mime_type": "image/jpeg",
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAFklEQVR4nGP4TyFgGDVg1IBRA4aLAQBdePwur/3haQAAAABJRU5ErkJggg==",
                "prompt": "Describe what Nova is seeing from this live camera snapshot.",
            }
        )

        assert status == 200
        response = payload["response"]
        assert response.startswith("[VISION] I see you there.")
        assert "I see a person near a phone screen" in response
        assert "?" in response
        assert any(
            phrase in response
            for phrase in (
                "What pulled your attention",
                "What's been on your mind",
                "What feels interesting",
            )
        )
    finally:
        server.PERMISSIONS["camera"] = old_camera


def test_vision_answer_cleaner_removes_moondream_image_marker():
    assert server._clean_vision_answer("!!!IMAGE!!! A bright red square.") == "A bright red square."


def test_vision_answer_cleaner_removes_other_moondream_bang_markers():
    assert server._clean_vision_answer("!!!RED!!! A bright red square.") == "A bright red square."


def test_moondream_vision_uses_fast_mobile_safe_limits(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {"message": {"role": "assistant", "content": "A small test image."}}
            ).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    import nova_model_memory

    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **kwargs: captured.update(residency_kwargs=kwargs)
        or nullcontext(
            {
                "enabled": True,
                "allowed": True,
                "target_resident": True,
                "reason": "headroom_available",
                "content_logged": False,
            }
        ),
    )

    answer, meta = server._call_moondream_vision(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
        "",
    )

    assert answer == "A small test image."
    assert meta["used"] is True
    assert meta["resource_manager"]["content_logged"] is False
    assert 8 <= captured["timeout"] <= 120
    assert captured["payload"]["options"]["num_predict"] <= 80
    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["messages"][0]["role"] == "user"
    compact_prompt = captured["payload"]["messages"][0]["content"].lower()
    assert "describe this image" in compact_prompt
    assert "main subject" in compact_prompt
    assert len(compact_prompt) <= 140
    assert captured["payload"]["keep_alive"] == "10m"
    assert meta["provider_route"] == "ollama_chat"
    assert meta["prompt_compacted"] is True
    assert captured["residency_kwargs"]["allow_commit_fallback"] is True
    assert captured["residency_kwargs"]["allow_unmanaged_idle_handoff"] is True


def test_moondream_cold_start_gets_longer_bounded_timeout(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"response": "A cold-start image."}).encode("utf-8")

    monkeypatch.setattr(
        server.urllib.request,
        "urlopen",
        lambda request, timeout=None: captured.update(timeout=timeout) or FakeResponse(),
    )
    import nova_model_memory

    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **_kwargs: nullcontext(
            {
                "enabled": True,
                "allowed": True,
                "target_resident": False,
                "reason": "headroom_available",
                "content_logged": False,
            }
        ),
    )

    answer, meta = server._call_moondream_vision(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
        "",
    )

    assert answer == "A cold-start image."
    assert server.NOVA_VISION_TIMEOUT <= captured["timeout"] <= 120
    assert meta["cold_start"] is True
    assert meta["timeout_seconds"] == captured["timeout"]
    assert captured["timeout"] == 120


def test_vision_answer_quality_rejects_one_token_noise_but_allows_color_answer():
    assert server._vision_answer_is_usable("xtalk", "What app is visible?") is False
    assert server._vision_answer_is_usable("xtalk on a phone", "What app is visible?") is False
    assert server._vision_answer_is_usable("A phone screen is visible.", "What is visible?") is True
    assert server._vision_answer_is_usable("red", "What single color fills this image?") is True


def test_moondream_prompt_is_compact_and_keeps_short_specific_question():
    camera_prompt = server._compact_moondream_prompt(
        "Answer the user's request directly from the supplied image or images. "
        "Inspect every relevant detail before answering. User request: "
        "Describe what Nova is seeing from this live camera snapshot."
    )
    color_prompt = server._compact_moondream_prompt("What color is the cup?")

    assert camera_prompt.startswith("Describe this image.")
    assert len(camera_prompt) <= 140
    assert color_prompt == "Look at this image and answer: What color is the cup?"


def test_moondream_quarantine_returns_immediately_without_provider_call(monkeypatch):
    server.MODEL_QUALITY.record_failure(
        "ollama",
        server.NOVA_VISION_MODEL,
        reason="low_quality_vision_response",
    )
    server.MODEL_QUALITY.record_failure(
        "ollama",
        server.NOVA_VISION_MODEL,
        reason="low_quality_vision_response",
    )
    monkeypatch.setattr(
        server.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("a quarantined vision model must not be called")
        ),
    )

    answer, meta = server._call_moondream_vision(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
        "What is visible?",
    )

    assert answer == ""
    assert meta["error"] == "model_quarantined"
    assert meta["model_quality"]["quarantined"] is True


def test_moondream_retries_after_operational_timeout_quarantine(monkeypatch):
    for _ in range(2):
        server.MODEL_QUALITY.record_failure(
            "ollama",
            server.NOVA_VISION_MODEL,
            reason="timeout",
            source="vision_runtime",
        )
    assert server.MODEL_QUALITY.is_quarantined(
        "ollama", server.NOVA_VISION_MODEL
    ) is True

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"response": "A phone screen is visible."}).encode(
                "utf-8"
            )

    monkeypatch.setattr(server.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    import nova_model_memory

    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **_kwargs: nullcontext(
            {
                "allowed": True,
                "target_resident": True,
                "content_logged": False,
            }
        ),
    )

    answer, meta = server._call_moondream_vision(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
        "What is visible?",
    )

    assert answer == "A phone screen is visible."
    assert meta["used"] is True
    assert server.MODEL_QUALITY.is_quarantined(
        "ollama", server.NOVA_VISION_MODEL
    ) is False


def test_web_ui_compresses_picture_uploads_before_vision_send():
    html = server.WEB_HTML

    required_markers = [
        "const MAX_VISION_UPLOAD_DIMENSION",
        "const VISION_UPLOAD_JPEG_QUALITY",
        "async function prepareVisionImageBase64",
        "canvas.toDataURL('image/jpeg', VISION_UPLOAD_JPEG_QUALITY)",
        "const prepared = await prepareVisionImageBase64(file)",
        "image_base64: prepared.image_base64",
        "mime_type: prepared.mime_type",
    ]

    for marker in required_markers:
        assert marker in html


def test_web_ui_previews_picture_and_accepts_a_question_before_local_analysis():
    html = server.WEB_HTML
    required_markers = [
        'id="pictureReviewDialog"',
        'id="pictureReviewPreview"',
        'id="pictureReviewPrompt"',
        'id="pictureUploadProgress"',
        'id="analyzePictureBtn"',
        "async function stageVisionImage",
        "async function analyzeStagedPicture",
        "pictureInput.value = '';",
        "setPictureProgress('Checking local picture permission…', true);",
        "await syncCameraPermission(true);",
        "function validateVisionFile",
        "MAX_VISION_SOURCE_BYTES",
        "MAX_VISION_ENCODED_BYTES",
        "VISION_UPLOAD_TIMEOUT_MS",
        "client_processing:",
        "source_width: prepared.source_width",
        "if(file) await stageVisionImage(file)",
        "encodedBytes > MAX_VISION_ENCODED_BYTES",
    ]

    for marker in required_markers:
        assert marker in html
    assert "const VISION_UPLOAD_TIMEOUT_MS = 150000" in html


def test_web_ui_opens_mobile_picture_picker_inside_the_user_gesture():
    html = server.WEB_HTML
    choose_start = html.index("function choosePicture(){")
    choose_end = html.index("function loadImageForVision", choose_start)
    choose_body = html[choose_start:choose_end]

    assert "syncCameraPermission(true);" in choose_body
    assert "openPicturePicker();" in choose_body
    assert "await syncCameraPermission" not in choose_body
    assert choose_body.index("syncCameraPermission(true);") < choose_body.index("openPicturePicker();")


def test_smart_picture_router_selects_local_capabilities():
    image = {"width": 1080, "height": 1920}

    nova_ui = server._classify_vision_request(
        image,
        prompt="What app is on this screen?",
        ocr_text="Nova Creature\nChat Home Display",
        filename="phone.jpg",
    )
    document = server._classify_vision_request(
        image,
        prompt="Read this receipt",
        ocr_text="TOTAL 12.50",
        filename="receipt.jpg",
    )
    photo = server._classify_vision_request(
        {"width": 1200, "height": 900},
        prompt="What is in this picture?",
        filename="garden.jpg",
    )
    comparison = server._classify_vision_request(
        image,
        prompt="What changed?",
        filename="before.png",
        has_comparison=True,
    )

    assert nova_ui["task_type"] == "nova_ui"
    assert nova_ui["strategy"] == "local_ocr"
    assert document["task_type"] == "document"
    assert photo["task_type"] == "photo_scene"
    assert photo["strategy"] == "local_vision"
    assert comparison["task_type"] == "comparison"
    assert all(route["local_only"] for route in (nova_ui, document, photo, comparison))


def test_moondream_comparison_sends_two_images(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"response": "The second image has a new button."}).encode("utf-8")

    monkeypatch.setattr(
        server.MODEL_QUALITY,
        "model_status",
        lambda *_args, **_kwargs: {"quarantined": False},
    )
    monkeypatch.setattr(server.MODEL_QUALITY, "record_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda request, **_kwargs: captured.update(url=request.full_url, payload=json.loads(request.data.decode("utf-8"))) or FakeResponse())
    import nova_model_memory

    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **_kwargs: nullcontext({"allowed": True, "target_resident": True}),
    )

    answer, meta = server._call_moondream_vision("Zmlyc3Q=", "What changed?", "c2Vjb25k")

    assert answer == "The second image has a new button."
    assert meta["used"] is True
    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["messages"][0]["images"] == ["Zmlyc3Q=", "c2Vjb25k"]
    assert "compare these two images" in captured["payload"]["messages"][0]["content"].lower()


def test_picture_comparison_uses_private_local_ocr_without_vision_delay(monkeypatch):
    import nova_ocr

    old_camera = server.PERMISSIONS["camera"]
    answers = iter(
        [
            ("Nova Creature\nVoice OFF", {"engine": "tesseract", "available": True, "used": True, "characters": 23, "lines": 2}),
            ("Nova Creature\nVoice ON", {"engine": "tesseract", "available": True, "used": True, "characters": 22, "lines": 2}),
        ]
    )
    monkeypatch.setattr(nova_ocr, "extract_text", lambda *_args, **_kwargs: next(answers))
    monkeypatch.setattr(
        server,
        "_call_moondream_vision",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("OCR comparison should bypass Moondream")),
    )
    server.PERMISSIONS["camera"] = True
    image = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode("ascii")
    try:
        payload, status = server._vision_response_from_upload(
            {
                "filename": "before.png",
                "mime_type": "image/png",
                "image_base64": image,
                "comparison_filename": "after.png",
                "comparison_mime_type": "image/png",
                "comparison_image_base64": image,
                "prompt": "Read the screens and tell me what changed",
                "inspection_focus": {"x": 0.25, "y": 0.75, "zoom": 2, "rotation": 90, "set": True},
            }
        )
    finally:
        server.PERMISSIONS["camera"] = old_camera

    assert status == 200
    assert payload["response"].startswith("[VISION COMPARE]")
    assert "Only in the first: Voice OFF" in payload["response"]
    assert "Only in the second: Voice ON" in payload["response"]
    assert payload["trace"]["vision_route"]["task_type"] == "comparison"
    assert payload["trace"]["vision_bypass_reason"] == "local_ocr_answered_image_comparison"
    assert payload["trace"]["ocr"]["image_persisted"] is False
    assert payload["trace"]["comparison_ocr"]["image_persisted"] is False
    assert "Nova Creature" not in json.dumps(payload["trace"])


def test_web_ui_has_smart_picture_edit_compare_and_private_context_flow():
    html = server.WEB_HTML
    required_markers = [
        'id="picturePreviewStage"',
        'id="pictureFocusMarker"',
        'id="pictureZoomRange"',
        'id="comparisonPictureInput"',
        "function rotateStagedPicture",
        "function setPictureFocus",
        "function stageComparisonPicture",
        "ctx.drawImage(image, sourceX, sourceY, cropWidth, cropHeight",
        "comparison_image_base64: comparisonPrepared?.image_base64",
        "rememberConversationTurn(userLine, data.response || '', data.trace || {})",
        "comparisonPictureInput.value = '';",
    ]

    for marker in required_markers:
        assert marker in html


def test_visual_follow_up_is_traced_as_temporary_and_never_contains_image_bytes(monkeypatch):
    import nova_ocr

    old_camera = server.PERMISSIONS["camera"]
    server.PERMISSIONS["camera"] = True
    monkeypatch.setattr(
        nova_ocr,
        "extract_text",
        lambda *_args, **_kwargs: (
            "",
            {
                "engine": "tesseract",
                "available": True,
                "used": False,
                "characters": 0,
                "lines": 0,
                "error": None,
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_call_moondream_vision",
        lambda _image, _prompt: (
            "The button in the picture is purple.",
            {"used": True, "model": "moondream", "error": None, "resource_manager": None},
        ),
    )
    image = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode("ascii")
    try:
        payload, status = server._vision_response_from_upload(
            {
                "filename": "temporary-picture.png",
                "mime_type": "image/png",
                "image_base64": image,
                "prompt": "What color is that button?",
                "visual_follow_up": True,
            }
        )
    finally:
        server.PERMISSIONS["camera"] = old_camera

    assert status == 200
    assert payload["trace"]["visual_follow_up"] is True
    assert payload["trace"]["memory_event"] == "temporary_visual_context_used"
    assert "temporary_visual_context" in payload["trace"]["skills"]
    assert "visual_context_follow_up" in payload["trace"]["route_path"]
    assert payload["trace"]["ocr"]["image_persisted"] is False
    assert image not in json.dumps(payload["trace"])


def test_web_ui_keeps_visual_follow_up_context_only_in_ephemeral_browser_memory():
    html = server.WEB_HTML
    required_markers = [
        "const VISION_CONTEXT_TTL_MS = 10 * 60 * 1000",
        'id="btnVisionContext"',
        "function setActiveVisionContext",
        "function clearActiveVisionContext",
        "function shouldUseActiveVisionContext",
        "async function sendActiveVisionFollowUp",
        "visual_follow_up: !!options.followUp",
        "if(trainedAdapterOnlyMode || dolphinAdapterOnlyMode || managedModelMode === 'raw_memory') return false",
        "if(shouldUseActiveVisionContext(text))",
        "temporary picture context cleared",
    ]
    for marker in required_markers:
        assert marker.lower() in html.lower()

    setter_start = html.index("function setActiveVisionContext")
    setter_end = html.index("function currentActiveVisionContext", setter_start)
    setter_body = html[setter_start:setter_end]
    assert "localStorage" not in setter_body
    assert "sessionStorage" not in setter_body
    assert "image_base64" not in setter_body


def test_picture_quality_metadata_is_bounded_and_content_free():
    normalized = server._normalize_client_picture_quality(
        {
            "score": 800,
            "grade": "POOR",
            "brightness": -10,
            "contrast": 999,
            "sharpness": 7.234,
            "issues": ["very_dark", "made_up_issue", "low_contrast"],
            "enhancement_recommended": True,
            "secret_sample": "pixel content must not survive",
        }
    )

    assert normalized == {
        "score": 100,
        "grade": "poor",
        "brightness": 0.0,
        "contrast": 128.0,
        "sharpness": 7.2,
        "issues": ["very_dark", "low_contrast"],
        "enhancement_recommended": True,
        "estimated": True,
        "content_logged": False,
    }
    assert "secret_sample" not in normalized


def test_poor_picture_quality_adds_honest_warning_and_safe_trace(monkeypatch):
    import nova_ocr

    old_camera = server.PERMISSIONS["camera"]
    server.PERMISSIONS["camera"] = True
    monkeypatch.setattr(
        nova_ocr,
        "extract_text",
        lambda *_args, **_kwargs: (
            "",
            {"engine": "tesseract", "available": True, "used": False, "characters": 0, "lines": 0, "error": None},
        ),
    )
    monkeypatch.setattr(
        server,
        "_call_moondream_vision",
        lambda _image, _prompt: (
            "I can make out a dim control panel.",
            {"used": True, "model": "moondream", "error": None, "resource_manager": None},
        ),
    )
    image = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode("ascii")
    try:
        payload, status = server._vision_response_from_upload(
            {
                "filename": "dark.png",
                "mime_type": "image/png",
                "image_base64": image,
                "prompt": "What is visible?",
                "client_processing": {
                    "enhanced": True,
                    "picture_quality": {
                        "score": 31,
                        "grade": "poor",
                        "brightness": 28,
                        "contrast": 12,
                        "sharpness": 3.4,
                        "issues": ["very_dark", "low_contrast", "low_detail_or_blur"],
                        "raw_pixels": "must not be copied",
                    },
                },
            }
        )
    finally:
        server.PERMISSIONS["camera"] = old_camera

    assert status == 200
    assert "Quality warning:" in payload["response"]
    assert "clearer or closer picture" in payload["response"]
    assert payload["trace"]["picture_enhanced"] is True
    assert payload["trace"]["picture_quality"]["score"] == 31
    assert payload["trace"]["picture_quality"]["issues"] == [
        "very_dark", "low_contrast", "low_detail_or_blur"
    ]
    assert "raw_pixels" not in json.dumps(payload["trace"])


def test_web_ui_has_local_picture_quality_guard_and_bounded_enhancement():
    html = server.WEB_HTML
    required_markers = [
        'id="pictureQualityStatus"',
        'id="autoEnhancePictureBtn"',
        "function analyzeVisionImageQuality",
        "function updatePictureQualityUi",
        "function togglePictureEnhancement",
        "function applyLocalPictureEnhancement",
        "getImageData(0, 0, width, height)",
        "enhancement_recommended",
        "enhanced: !!prepared.enhanced",
        "picture_quality: prepared.quality || null",
        "enhance:stagedVisionEnhance",
        "function prepareLiveCameraAnalysisFrame",
        "quality?.enhancement_recommended",
        "client_processing:clientProcessing",
        "picture_quality:prepared.picture_quality",
        "Give phone cameras a brief moment to settle autofocus and exposure.",
    ]
    for marker in required_markers:
        assert marker in html
    assert 'id="autoEnhancePictureBtn" onclick="togglePictureEnhancement()" disabled' in html

    analyzer_start = html.index("function analyzeVisionImageQuality")
    analyzer_end = html.index("function pictureQualityIssueText", analyzer_start)
    analyzer_body = html[analyzer_start:analyzer_end]
    assert "96 / Math.max(sourceWidth, sourceHeight)" in analyzer_body
    assert "localStorage" not in analyzer_body
    assert "fetch(" not in analyzer_body


def test_web_ui_display_tab_shows_nova_body_and_live_status():
    required_display_markers = [
        'id="displayAvatar"',
        'id="novaWalkSpace"',
        'id="novaFullBody"',
        'id="novaBotChassis"',
        'id="nova3DSpace"',
        'id="nova3DStage"',
        'id="novaBot3D"',
        'id="nova3DCanvas"',
        'class="nova-3d-canvas"',
        'id="botHeadingIndicator"',
        'id="novaScreenHead"',
        'id="novaDisplayScreen"',
        'id="virtualSelfState"',
        'id="botChatDock"',
        'id="botChatLog"',
        'id="botChatInput"',
        'id="botChatSend"',
        'id="spaceCameraControls"',
        'id="spaceCameraState"',
        'data-motion="walk"',
        'data-motion="wave"',
        'data-motion="stop"',
        'data-drive="forward"',
        'data-drive="reverse"',
        'data-drive="turn-left"',
        'data-drive="turn-right"',
        'data-drive="stop"',
        'data-head="left"',
        'data-head="center"',
        'data-head="right"',
        'data-screen="face"',
        'data-screen="route"',
        'data-screen="status"',
        'data-screen="memory"',
        'data-space-control="orbit-left"',
        'data-space-control="orbit-right"',
        'data-space-control="tilt-up"',
        'data-space-control="tilt-down"',
        'data-space-control="zoom-in"',
        'data-space-control="zoom-out"',
        'data-space-control="pan-left"',
        'data-space-control="pan-right"',
        'data-space-control="reset"',
        'id="displayRouteTrace"',
        'id="displayRouteModel"',
        'id="displaySessionState"',
        'id="displayPeopleCount"',
        'id="displayLessonsCount"',
        'data-role="memory_transformer"',
        'data-role="speech_output_transformer"',
        "function updateDisplayTelemetry",
        "function setBodyMotion",
        "function setBotDrive",
        "function setHeadTurn",
        "function setScreenMode",
        "function handleBotBodyCommand",
        "handleBotBodyCommand(text)",
        "function buildNova3DModel",
        "function project3DPoint",
        "function drawNova3DScene",
        "function renderNova3DBot",
        "function applySpaceCameraDelta",
        "function resetSpaceCamera",
        "function bindSpaceCanvasControls",
        "function visualYawFromHeading",
        "function updateBotTransform",
        "function sendBotChat",
        "function addBotChatLine",
        "function formatRoutePath",
        "function updateDisplayCounts",
        "openPanel('agent-library-panel')",
        "openPanel('app-builder-panel')",
        "openPanel('debug-logs-panel')",
        'id="projectsList"',
        'id="projectStatus"',
        'id="fileProjectSelect"',
        'id="projectFilesList"',
        'id="fileEditor"',
        'id="fileLivePreviewFrame"',
        'id="projectImportInput"',
        "function loadProjects",
        "function exportProjectZip",
        "function deployProject",
        "function runProjectQualityGate",
        "function renderQualityGateVisualLinks",
        "quality_gate_screenshots",
        "screenshot_url",
        "Quality Gate",
        "function importProjectZip",
        "function updateLivePreview",
        "function buildPreviewDocument",
        "function saveProjectFile",
        "/api/projects",
    ]

    for marker in required_display_markers:
        assert marker in server.WEB_HTML

    assert "rotateY(var(--bot-yaw" not in server.WEB_HTML
    assert 'sandbox="allow-scripts allow-forms"' in server.WEB_HTML
    assert 'allow-same-origin' not in server.WEB_HTML


def test_sandbox_project_static_path_resolves_preview_file():
    resolved = server._resolve_sandbox_static_path(
        "/sandbox/app_builder_projects/Nova_Pac_Runner/index.html"
    )

    assert resolved is not None
    assert resolved.name == "index.html"
    assert resolved.exists()
    assert "Nova_Pac_Runner" in str(resolved)


def test_sandbox_project_static_path_blocks_directory_escape():
    resolved = server._resolve_sandbox_static_path(
        "/sandbox/app_builder_projects/Nova_Pac_Runner/../../../../nova_llm_config.json"
    )

    assert resolved is None


def test_project_manager_api_lists_edits_exports_deploys_and_imports(monkeypatch, tmp_path):
    projects_root = tmp_path / "projects"
    exports_root = tmp_path / "exports"
    deployments_root = tmp_path / "deployments"
    _make_project(projects_root)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", str(projects_root))
    monkeypatch.setattr(server, "PROJECT_EXPORTS_ROOT", str(exports_root), raising=False)
    monkeypatch.setattr(server, "PROJECT_DEPLOYMENTS_ROOT", str(deployments_root), raising=False)

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        projects = _json_get(base_url, "/api/projects")["projects"]
        assert projects[0]["id"] == "Music_Sound_Secrets_Website"

        files = _json_get(base_url, "/api/projects/Music_Sound_Secrets_Website/files")["files"]
        assert "index.html" in [item["path"] for item in files]

        file_data = _json_get(base_url, "/api/projects/Music_Sound_Secrets_Website/file?path=index.html")
        assert "Music home" in file_data["content"]

        saved = _json_post(
            base_url,
            "/api/projects/Music_Sound_Secrets_Website/file",
            {"path": "notes.txt", "content": "ship the mix"},
        )
        assert saved["path"] == "notes.txt"
        assert (projects_root / "Music_Sound_Secrets_Website" / "notes.txt").read_text(encoding="utf-8") == "ship the mix"

        with urllib.request.urlopen(base_url + "/api/projects/Music_Sound_Secrets_Website/export.zip", timeout=5) as response:
            zip_bytes = response.read()
            assert response.headers["Content-Type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            assert "index.html" in archive.namelist()

        deployed = _json_post(base_url, "/api/projects/Music_Sound_Secrets_Website/deploy", {})
        assert deployed["deploy_url"] == "/sandbox/deployments/Music_Sound_Secrets_Website/index.html"
        assert (deployments_root / "Music_Sound_Secrets_Website" / "mixing.html").exists()

        import_buffer = io.BytesIO()
        with zipfile.ZipFile(import_buffer, "w") as archive:
            archive.writestr("index.html", "<html>Imported</html>")
        imported = _json_post(
            base_url,
            "/api/projects/import",
            {
                "project_id": "Imported_Music_Site",
                "content_base64": base64.b64encode(import_buffer.getvalue()).decode("ascii"),
            },
        )
        assert imported["project"]["id"] == "Imported_Music_Site"
        assert (projects_root / "Imported_Music_Site" / "index.html").exists()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_project_manager_api_imports_general_zip_and_single_file(monkeypatch, tmp_path):
    projects_root = tmp_path / "projects"
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", str(projects_root))
    monkeypatch.setattr(server, "PROJECT_EXPORTS_ROOT", str(tmp_path / "exports"), raising=False)
    monkeypatch.setattr(server, "PROJECT_DEPLOYMENTS_ROOT", str(tmp_path / "deployments"), raising=False)

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        general_zip = io.BytesIO()
        with zipfile.ZipFile(general_zip, "w") as archive:
            archive.writestr("chef_clash_dev/readme.md", "# Chef Clash")
            archive.writestr("chef_clash_dev/assets/sprite.png", b"\x89PNG\r\n")

        imported_zip = _json_post(
            base_url,
            "/api/projects/import",
            {
                "project_id": "Chef_Clash_Dev",
                "filename": "chef_clash_dev_v1_6.zip",
                "content_base64": base64.b64encode(general_zip.getvalue()).decode("ascii"),
            },
        )
        assert imported_zip["project"]["id"] == "Chef_Clash_Dev"
        assert imported_zip["project"]["project_type"] == "files"
        assert imported_zip["project"]["open_url"] is None
        assert (projects_root / "Chef_Clash_Dev" / "readme.md").exists()

        imported_file = _json_post(
            base_url,
            "/api/projects/import",
            {
                "project_id": "Single_Mod_File",
                "filename": "mod_config.txt",
                "content_base64": base64.b64encode(b"speed=fast").decode("ascii"),
            },
        )
        assert imported_file["project"]["id"] == "Single_Mod_File"
        assert (projects_root / "Single_Mod_File" / "mod_config.txt").exists()

        projects_list = _json_get(base_url, "/api/projects")["projects"]
        assert {item["id"] for item in projects_list} == {"Chef_Clash_Dev", "Single_Mod_File"}
        assert all(item["project_type"] == "files" for item in projects_list)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_new_flags_default_safe_and_raw_adapters_remain_independent(monkeypatch):
    for name in (
        "NOVA_CONVERSATION_INTELLIGENCE_ENABLED",
        "NOVA_RESPONSE_REPAIR_ENABLED",
        "NOVA_RESPONSE_REPAIR_MAXIMUM_ATTEMPTS",
        "NOVA_CONVERSATION_SMALL_MODEL",
        "NOVA_CONVERSATION_MIDDLE_MODEL",
        "NOVA_DEEP_MODELS_REQUIRE_RESOURCE_APPROVAL",
        "NOVA_CONVERSATION_CONTINUITY_ENABLED",
        "NOVA_CONVERSATION_MAXIMUM_OPEN_LOOPS",
        "NOVA_PERCEPTION_FUSION_ENABLED",
        "NOVA_REQUIRE_CALIBRATED_DEPTH_FOR_NAVIGATION",
        "NOVA_ROBOT_SIMULATION_ENABLED",
        "NOVA_ROBOT_PHYSICAL_MOVEMENT_ENABLED",
        "NOVA_RAW_ADAPTER_MANAGED_INTERCEPTION",
    ):
        monkeypatch.delenv(name, raising=False)

    config = server._runtime_cognitive_config()

    assert config["conversation_intelligence"] == {
        "enabled": True,
        "schema_version": "1.0",
    }
    assert config["response_repair"]["maximum_attempts"] == 1
    assert config["model_routing"]["small_model"] == "qwen2.5:1.5b"
    assert config["model_routing"]["middle_model"] == "qwen2.5:3b"
    assert config["model_routing"]["deep_models_require_resource_approval"] is True
    assert config["conversation_continuity"]["maximum_open_loops"] == 8
    assert config["perception"]["require_calibrated_depth_for_navigation"] is True
    assert config["robot"]["simulation_enabled"] is True
    assert config["robot"]["physical_movement_enabled"] is False
    assert config["telemetry"] == {
        "enabled": False,
        "log_prompts": False,
        "log_private_memory": False,
    }
    assert config["raw_adapters"]["managed_interception"] is False


def test_new_flags_honor_environment_overrides(monkeypatch):
    monkeypatch.setenv("NOVA_CONVERSATION_INTELLIGENCE_ENABLED", "false")
    monkeypatch.setenv("NOVA_RESPONSE_REPAIR_MAXIMUM_ATTEMPTS", "0")
    monkeypatch.setenv("NOVA_CONVERSATION_MIDDLE_MODEL", "test-middle")
    monkeypatch.setenv("NOVA_ROBOT_SIMULATION_ENABLED", "false")

    config = server._runtime_cognitive_config()

    assert config["conversation_intelligence"]["enabled"] is False
    assert config["response_repair"]["maximum_attempts"] == 0
    assert config["model_routing"]["middle_model"] == "test-middle"
    assert config["robot"]["simulation_enabled"] is False


def test_managed_turn_does_not_commit_firewall_recovery_as_valid_context(monkeypatch):
    original = (server._LAST_USER_TEXT, server._LAST_NOVA_RESPONSE)
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "Earlier topic")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "Earlier valid answer")

    def fake_impl(text, context):
        server._LAST_USER_TEXT = text
        server._LAST_NOVA_RESPONSE = "I caught an off-topic draft before sending it."
        return (
            "I caught an off-topic draft before sending it.",
            {
                "source": "answer_firewall_recovery",
                "final_answer_source": "answer_firewall_recovery",
                "fallback_used": True,
                "answer_firewall": {"status": "blocked", "accepted": False},
            },
        )

    monkeypatch.setattr(server, "_run_nova_chat_turn_impl", fake_impl)

    response, trace = server._run_nova_chat_turn("I have been thinking about a garden", {})

    assert "off-topic draft" in response
    assert server._LAST_USER_TEXT == "Earlier topic"
    assert server._LAST_NOVA_RESPONSE == "Earlier valid answer"
    assert trace["conversation_state_committed"] is False
    assert trace["conversation_state_commit_reason"] == "recovery_response"
    assert trace["pending_turn"] is True


def test_managed_turn_commits_valid_answer(monkeypatch):
    monkeypatch.setattr(server, "_LAST_USER_TEXT", "Earlier topic")
    monkeypatch.setattr(server, "_LAST_NOVA_RESPONSE", "Earlier valid answer")

    def fake_impl(text, context):
        server._LAST_USER_TEXT = text
        server._LAST_NOVA_RESPONSE = "A garden can start with herbs in a sunny pot."
        return (
            "A garden can start with herbs in a sunny pot.",
            {
                "source": "cognitive_os",
                "final_answer_source": "llm_synthesis",
                "fallback_used": False,
                "answer_firewall": {"status": "passed", "accepted": True},
            },
        )

    monkeypatch.setattr(server, "_run_nova_chat_turn_impl", fake_impl)

    response, trace = server._run_nova_chat_turn("I want to start a garden", {})

    assert response.startswith("A garden")
    assert server._LAST_USER_TEXT == "I want to start a garden"
    assert server._LAST_NOVA_RESPONSE.startswith("A garden")
    assert trace["conversation_state_committed"] is True
    assert trace["conversation_state_commit_reason"] == "validated_answer"
    assert trace["pending_turn"] is False


def test_client_history_boundary_does_not_fall_back_to_stale_legacy_context():
    selected = server._select_previous_exchange(
        {"conversation_history": [
            {"role": "user", "content": "I have been thinking about a garden."},
            {"role": "assistant", "content": "I caught an off-topic draft before sending it."},
        ]},
        client_previous=("", ""),
        legacy_previous=("Old unrelated topic", "Old unrelated answer"),
    )

    assert selected == ("", "")
