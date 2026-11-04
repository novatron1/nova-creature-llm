from pathlib import Path
from types import SimpleNamespace
import builtins
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_cognitive_os as cognitive_os
import nova_context_builder
import nova_intent_planner
import nova_long_term_memory
import nova_local_llm_connector
import nova_memory_slot_retrieval


def test_cognitive_os_uses_llm_planner_first_for_open_ended_route(monkeypatch):
    force_llm_values = []

    class Planner:
        def plan(self, message, force_llm=True):
            force_llm_values.append(force_llm)
            return {
                "route": "general_conversation",
                "intent": "open-ended chat",
                "slot_needed": None,
                "needs_memory": False,
                "needs_dictionary": False,
                "needs_math": False,
                "needs_weather": False,
                "needs_web": False,
                "needs_llm_synthesis": False,
                "answer_style": "short_answer",
                "confidence": 0.75,
                "_planner_used": "llm",
            }

    class ValidationResult:
        ok = True

        def __init__(self, plan):
            self.plan = plan

    class Validator:
        def validate(self, plan, raw_user_message=""):
            return ValidationResult(plan)

    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_slot_retrieval", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_answer_synthesizer", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_context_builder", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_web", lambda: None)

    cognitive_os.route("Tell me how robots learn")

    assert force_llm_values == [True]


def test_cognitive_os_tracks_plan_repair_separately_from_final_fallback(monkeypatch):
    class Planner:
        def plan(self, message, force_llm=True):
            return {
                "route": "general_conversation",
                "_planner_used": "llm",
            }

    class ValidationResult:
        ok = False
        errors = ["missing field: intent"]
        fallback_reason = "missing_fields"

        def __init__(self, plan):
            self.plan = plan

    class Validator:
        def validate(self, plan, raw_user_message=""):
            return ValidationResult(plan)

        def make_fallback_plan(self, message):
            return {
                "route": "general_conversation",
                "intent": "fallback classification: general",
                "slot_needed": None,
                "answer_style": "short_answer",
                "needs_memory": False,
                "needs_dictionary": False,
                "needs_math": False,
                "needs_weather": False,
                "needs_web": False,
                "needs_tool": False,
                "needs_llm_synthesis": False,
                "confidence": 0.60,
                "_planner_used": "fallback_validator",
            }

    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_slot_retrieval", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_answer_synthesizer", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_context_builder", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_web", lambda: None)

    _, trace = cognitive_os.route("Tell me something")

    assert trace["plan_repair_used"] is True
    assert trace["fallback_used"] is False


def test_llm_planner_can_call_connector_without_httpx(monkeypatch):
    calls = []

    class FakeConnector:
        def __init__(self):
            self.config = SimpleNamespace(url="http://127.0.0.1:11434/api/generate")

        def generate(self, context):
            calls.append(context)
            return SimpleNamespace(
                local_llm_used=True,
                raw_output='{"route":"general_conversation","needs_llm_synthesis":true}',
            )

    real_import = builtins.__import__

    def import_without_httpx(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("httpx unavailable in this environment")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)
    monkeypatch.setattr(builtins, "__import__", import_without_httpx)

    raw = nova_intent_planner._call_llm_planner("hello")

    assert raw == '{"route":"general_conversation","needs_llm_synthesis":true}'
    assert calls
    assert "raw_prompt" in calls[0]
    assert calls[0]["local_llm_model"] == "qwen2.5:1.5b"
    assert calls[0]["local_llm_timeout"] <= 45
    assert calls[0]["ollama_options"]["temperature"] == 0
    assert calls[0]["ollama_options"]["num_predict"] >= 700


def test_cognitive_os_loads_llm_synthesizer():
    cognitive_os._LLM_SYNTH = None

    synth = cognitive_os._get_llm_synth()

    assert synth is not None
    assert hasattr(synth, "generate")


def test_context_builder_allows_general_answers_without_memory():
    packet = nova_context_builder.build(
        "Why should a robot test code?",
        {
            "route": "coding_help",
            "answer_style": "short_answer",
        },
    )

    assert "answer the user's general question normally" in packet["system_prompt"]
    assert 'If memory context is "None", say you don' not in packet["system_prompt"]


def test_cognitive_os_strips_unsupported_citations_without_web():
    cleaned = cognitive_os._strip_unsupported_citations(
        "Testing catches bugs early [1].",
        web_used=False,
    )

    assert cleaned == "Testing catches bugs early."


def test_cognitive_os_keeps_citations_when_web_was_used():
    cleaned = cognitive_os._strip_unsupported_citations(
        "Latest result came from the source [1].",
        web_used=True,
    )

    assert cleaned == "Latest result came from the source [1]."


def test_explicit_long_term_teaching_saves_custom_knowledge(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))

    text = "In the Nova college test, a retrieval cue is a hint that helps memory recall."
    record = nova_long_term_memory.add_memory(text, source_command="long_term")

    assert record is not None
    assert record["extracted_slot"] == "custom_knowledge"
    assert "retrieval cue" in record["extracted_value"].lower()

    matches = nova_long_term_memory.find_by_query("retrieval cue")
    assert matches
    assert nova_long_term_memory.synthesize_memory_answer(
        matches[0]["extracted_slot"],
        matches[0]["extracted_value"],
    ) == text


def test_explicit_long_term_teaching_confirmation_is_clean(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(cognitive_os, "_get_ltm", lambda: nova_long_term_memory)

    answer, trace = cognitive_os.route(
        "long-term remember this: In the Nova college test, a retrieval cue is a hint that helps memory recall."
    )

    assert answer == "Saved long-term: In the Nova college test, a retrieval cue is a hint that helps memory recall."
    assert "your custom knowledge" not in answer
    assert ".." not in answer
    assert trace["long_term_memory_saved"] is True


def test_memory_retrieval_prefers_specific_taught_fact(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))

    nova_long_term_memory.add_memory(
        "In the Nova college test, a retrieval cue is a hint that helps memory recall.",
        source_command="long_term",
    )
    nova_long_term_memory.add_memory(
        "In the Nova final fix test, a transfer example connects ideas across subjects.",
        source_command="long_term",
    )

    result = nova_memory_slot_retrieval.retrieve(
        {"route": "memory_recall", "slot_needed": None, "needs_memory": True},
        raw_user_message="In the Nova final fix test, what is a transfer example?",
    )

    assert result["found"] is True
    assert "transfer example" in result["value"].lower()
    assert "retrieval cue" not in result["value"].lower()


def test_flat_earth_question_uses_fast_direct_answer(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("flat-earth fact should skip slow planner")),
    )
    plan = nova_intent_planner.plan("is the earth flat/", force_llm=True)

    assert plan["route"] == "general_conversation"
    assert plan["needs_llm_synthesis"] is False
    assert "No" in plan["_direct_answer"]
    assert "not flat" in plan["_direct_answer"]


def test_nova_age_question_uses_fast_direct_answer(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("Nova age question should skip slow planner")),
    )
    plan = nova_intent_planner.plan("how old is u", force_llm=True)

    assert plan["route"] == "general_conversation"
    assert plan["needs_llm_synthesis"] is False
    assert "human age" in plan["_direct_answer"]
    assert "Nova Creature" in plan["_direct_answer"]


def test_cognitive_os_answers_simple_direct_facts_without_llm_synthesis(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("direct facts should skip slow planner")),
    )
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: None)

    answer, trace = cognitive_os.route("is the earth flat/")

    assert "No" in answer
    assert "not flat" in answer
    assert trace["local_llm_synthesis_used"] is False
    assert "nova_direct_answer" in trace["route_path"]


def test_cognitive_os_trace_uses_actual_synthesis_model(monkeypatch):
    class Planner:
        def plan(self, message, force_llm=True):
            return {
                "route": "general_conversation",
                "intent": "open-ended synthesis",
                "slot_needed": None,
                "answer_style": "short_answer",
                "needs_memory": False,
                "needs_dictionary": False,
                "needs_math": False,
                "needs_weather": False,
                "needs_web": False,
                "needs_tool": False,
                "needs_llm_synthesis": True,
                "confidence": 0.80,
                "_planner_used": "deterministic_fast_path",
            }

    class ValidationResult:
        ok = True
        errors = []

        def __init__(self, plan):
            self.plan = plan

    class Validator:
        def validate(self, plan, raw_user_message=""):
            return ValidationResult(plan)

    class FakeSynth:
        LAST_LOCAL_LLM_MODEL = "qwen2.5:1.5b"

        @staticmethod
        def generate(context_packet):
            FakeSynth.LAST_LOCAL_LLM_MODEL = "qwen2.5:1.5b"
            return "Testing catches bugs before users do.", True, None

    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: FakeSynth)

    answer, trace = cognitive_os.route("Explain why testing matters.")

    assert answer == "Testing catches bugs before users do."
    assert trace["local_llm_model"] == "qwen2.5:1.5b"
    assert "qwen_synthesis" in trace["route_path"]


def test_college_algebra_prompt_routes_to_llm_math_synthesis(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("academic route should skip slow planner")),
    )
    plan = nova_intent_planner.plan(
        "College algebra: solve 2x + 3 = 11 and explain the steps.",
        force_llm=True,
    )

    assert plan["route"] == "general_conversation"
    assert plan["answer_style"] == "explanation"
    assert plan["needs_llm_synthesis"] is True
    assert plan["needs_memory"] is False


def test_college_physics_prompt_does_not_route_to_memory_recall(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("academic route should skip slow planner")),
    )
    plan = nova_intent_planner.plan(
        "College physics: explain F = ma and give one plain example.",
        force_llm=True,
    )

    assert plan["route"] == "general_conversation"
    assert plan["needs_llm_synthesis"] is True
    assert plan["needs_memory"] is False


def test_college_coding_fix_routes_to_coding_help(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("academic route should skip slow planner")),
    )
    plan = nova_intent_planner.plan(
        "College coding: fix this Python and explain the error: print('hello'",
        force_llm=True,
    )

    assert plan["route"] == "coding_help"
    assert plan["needs_llm_synthesis"] is True
    assert plan["needs_memory"] is False


def test_college_psychology_prompt_routes_to_academic_synthesis(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("academic route should skip slow planner")),
    )
    plan = nova_intent_planner.plan(
        "College psychology: explain cognitive dissonance in two sentences.",
        force_llm=True,
    )

    assert plan["route"] == "general_conversation"
    assert plan["answer_style"] == "explanation"
    assert plan["needs_llm_synthesis"] is True
    assert plan["needs_memory"] is False


def test_college_cross_domain_prompt_routes_to_academic_synthesis(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("academic route should skip slow planner")),
    )
    plan = nova_intent_planner.plan(
        "College cross-domain reasoning: connect physics and psychology in one example.",
        force_llm=True,
    )

    assert plan["route"] == "general_conversation"
    assert plan["answer_style"] == "explanation"
    assert plan["needs_llm_synthesis"] is True
    assert plan["needs_memory"] is False


def test_college_taught_fact_question_routes_to_memory_recall(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("taught fact recall should skip slow planner")),
    )
    plan = nova_intent_planner.plan(
        "In the Nova college test, what is a retrieval cue?",
        force_llm=True,
    )

    assert plan["route"] == "memory_recall"
    assert plan["needs_memory"] is True
    assert plan["needs_llm_synthesis"] is False


def test_nova_named_test_fact_question_routes_to_memory_recall(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("named test recall should skip slow planner")),
    )
    plan = nova_intent_planner.plan(
        "In the Nova final fix test, what is a transfer example?",
        force_llm=True,
    )

    assert plan["route"] == "memory_recall"
    assert plan["needs_memory"] is True
    assert plan["needs_llm_synthesis"] is False


def test_academic_fallback_answers_known_college_prompts():
    assert "x = 4" in cognitive_os._academic_fallback_answer(
        "College algebra: solve 2x + 3 = 11.",
        "general_conversation",
    )
    physics = cognitive_os._academic_fallback_answer(
        "College physics: explain F = ma.",
        "general_conversation",
    )
    assert "force" in physics.lower()
    assert "mass" in physics.lower()
    assert "acceleration" in physics.lower()
    coding = cognitive_os._academic_fallback_answer(
        "College coding: fix this Python: print('hello'",
        "coding_help",
    )
    assert "print('hello')" in coding
    assert "closing" in coding.lower()
