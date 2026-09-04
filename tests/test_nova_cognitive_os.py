from pathlib import Path
from types import SimpleNamespace
import builtins
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_cognitive_os as cognitive_os
import nova_context_builder
import nova_intent_planner
import nova_long_term_memory
import nova_local_llm_connector
import nova_memory_slot_retrieval
import nova_meaning_pipeline
from nova_conversation_intelligence import understand_conversation_turn


def test_release_verification_does_not_write_cognitive_training_log(monkeypatch, tmp_path):
    monkeypatch.setattr(cognitive_os, "ROOT", str(tmp_path))
    monkeypatch.setenv("NOVA_SUPPRESS_RUNTIME_LOGS", "true")

    cognitive_os._log_training(
        "hello",
        "Hi there.",
        {"route": "general_conversation"},
    )

    assert (tmp_path / "nova_training_logs" / "cognitive_os_logs.jsonl").exists() is False

    monkeypatch.delenv("NOVA_SUPPRESS_RUNTIME_LOGS", raising=False)
    cognitive_os._log_training(
        "hello again",
        "Welcome back.",
        {"route": "general_conversation"},
    )
    assert (tmp_path / "nova_training_logs" / "cognitive_os_logs.jsonl").is_file()


def test_gateway_conversation_context_does_not_repeat_current_user_request():
    current = "Compare local and remote memory, then recommend an architecture."
    rendered = cognitive_os._gateway_conversation_context(
        [
            {"role": "user", "content": "We are building a private phone app."},
            {"role": "assistant", "content": "Keep its data local-first."},
            {"role": "user", "content": current},
        ],
        current_message=current,
    )

    assert "We are building a private phone app." in rendered
    assert "Keep its data local-first." in rendered
    assert current not in rendered


def test_cognitive_os_uses_fast_planner_for_open_ended_route(monkeypatch):
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

    assert force_llm_values == [False]


def test_cognitive_os_llm_first_policy_bypasses_fast_general_response(monkeypatch):
    calls = []

    class Planner:
        def plan(self, message, force_llm=True, conversation_decision=None):
            return {
                "route": "general_conversation",
                "intent": "stable reasoning",
                "slot_needed": None,
                "needs_memory": False,
                "needs_dictionary": False,
                "needs_math": False,
                "needs_weather": False,
                "needs_web": False,
                "needs_tool": False,
                "needs_llm_synthesis": False,
                "answer_style": "short_answer",
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
            calls.append(context_packet)
            return "A real answer formatted for Nova.", True, None

    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_answer_synthesizer", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: FakeSynth)

    answer, trace = cognitive_os.route(
        "Why is it so hard to find?",
        context={"normal_chat_llm_first": True},
    )

    assert answer == "A real answer formatted for Nova."
    assert len(calls) == 1
    assert calls[0]["normal_chat_llm_first"] is True
    assert trace["local_llm_synthesis_used"] is True
    assert "fast_general_response" not in trace["skills"]


def test_contextual_followup_cannot_be_promoted_to_web_search(monkeypatch):
    class Planner:
        def plan(self, message, force_llm=True, conversation_decision=None):
            return {
                "route": "web_search",
                "intent": "search for the answer",
                "slot_needed": None,
                "needs_memory": False,
                "needs_web": True,
                "needs_llm_synthesis": True,
                "answer_style": "short_answer",
                "confidence": 0.8,
                "_planner_used": "llm",
            }

    class ValidationResult:
        ok = True

        def __init__(self, plan):
            self.plan = plan

    class Validator:
        def validate(self, plan, raw_user_message=""):
            return ValidationResult(plan)

    monkeypatch.setattr(cognitive_os, "_get_ltm", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_slot_retrieval", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_answer_synthesizer", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_context_builder", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_web", lambda: None)

    decision = understand_conversation_turn("Can you elaborate?")
    _, trace = cognitive_os.route(
        "Can you elaborate?",
        context={
            "conversation_decision": decision,
            "conversation_history": [
                {"role": "user", "content": "Explain the router."},
                {"role": "assistant", "content": "It selects the right path."},
            ],
        },
    )

    assert trace["validated_route"] == "general_conversation"
    assert trace["web_used"] is False


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
    assert calls[0]["local_llm_timeout"] == 2
    assert calls[0]["ollama_options"]["temperature"] == 0
    assert calls[0]["ollama_options"]["num_ctx"] == 8192
    assert calls[0]["ollama_options"]["num_predict"] <= 200


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


def test_cognitive_os_streams_only_after_routing_context_and_critic_are_ready(monkeypatch):
    order = []
    emitted = []

    class Planner:
        def plan(self, message, force_llm=True):
            order.append("plan")
            return {
                "route": "coding_help",
                "intent": "explain testing",
                "slot_needed": None,
                "answer_style": "short_answer",
                "needs_memory": False,
                "needs_dictionary": False,
                "needs_math": False,
                "needs_web": False,
                "needs_llm_synthesis": True,
                "confidence": 0.9,
                "_planner_used": "fast",
            }

    class ValidationResult:
        ok = True

        def __init__(self, plan):
            self.plan = plan

    class Validator:
        def validate(self, plan, raw_user_message=""):
            order.append("validate")
            return ValidationResult(plan)

    class AnswerSynth:
        @staticmethod
        def try_direct_answer(*args):
            return None, False

        @staticmethod
        def anti_echo_check(answer):
            order.append("critic")
            return "debug:" not in answer

    class ContextBuilder:
        @staticmethod
        def build(message, plan, **kwargs):
            order.append("context")
            return {"user_question": message, "route": plan["route"], "system_prompt": "Nova identity"}

    class Synth:
        LAST_LOCAL_LLM_MODEL = "stream-test"

        @staticmethod
        def generate_stream(packet, callback, is_cancelled):
            assert order[:3] == ["plan", "validate", "context"]
            assert callable(packet["stream_answer_validator"])
            callback("Nova ")
            callback("streams safely.")
            packet["_native_stream_emitted"] = True
            packet["_native_stream_incremental"] = True
            return "Nova streams safely.", True, None

    monkeypatch.setattr(cognitive_os, "_get_ltm", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_slot_retrieval", lambda: None)
    monkeypatch.setattr(cognitive_os, "_get_answer_synthesizer", lambda: AnswerSynth())
    monkeypatch.setattr(cognitive_os, "_get_context_builder", lambda: ContextBuilder())
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: Synth())
    monkeypatch.setattr(cognitive_os, "_get_web", lambda: None)

    answer, trace = cognitive_os.route(
        "Why test code?",
        context={
            "stream_callback": lambda delta: emitted.append(delta) or True,
            "stream_cancelled": lambda: False,
            "conversation_memory_allowed": False,
        },
    )

    assert answer == "".join(emitted) == "Nova streams safely."
    assert trace["native_streaming"] is True
    assert trace["native_stream_incremental"] is True
    assert order.index("context") < order.index("critic")


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


def test_long_term_memory_recalls_multiword_custom_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))

    record = nova_long_term_memory.add_memory(
        "my QA code word is cobalt-526958",
        source_command="long_term",
    )

    assert record["extracted_slot"] == "qa_code_word"
    recalled = nova_long_term_memory.recall_from_question("What is my QA code word?")
    assert recalled is not None
    _, answer = recalled
    assert answer == "Your QA code word is cobalt-526958."


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


def test_cognitive_os_recalls_multiword_long_term_fact(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(cognitive_os, "_get_ltm", lambda: nova_long_term_memory)

    cognitive_os.route("Remember this long term: my QA code word is cobalt-526958")
    answer, trace = cognitive_os.route("What is my QA code word?")

    assert answer == "Your QA code word is cobalt-526958."
    assert trace["memory_retrieved"] is True
    assert trace["extracted_slot"] == "qa_code_word"


def test_cognitive_os_does_not_guess_missing_long_term_fact(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(cognitive_os, "_get_ltm", lambda: nova_long_term_memory)
    llm_calls = []

    class FakeSynth:
        @staticmethod
        def generate(context_packet):
            llm_calls.append(context_packet)
            return "I don't have that saved yet, but I can help you choose a new code word.", True, None

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: FakeSynth)

    answer, trace = cognitive_os.route(
        "What is my dolphin test code word?",
        context={"memory_read_allowed": True, "memory_write_allowed": False},
    )

    assert "don't have that saved" in answer
    assert llm_calls, "a memory miss must retry the configured LLM before falling back"
    assert trace["memory_retrieved"] is False
    assert trace["local_llm_synthesis_used"] is True
    assert trace["source"] == "cognitive_os"
    assert "memory_llm_retry" in trace["skills"]


def test_cognitive_os_uses_memory_fallback_only_after_llm_retry_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(cognitive_os, "_get_ltm", lambda: nova_long_term_memory)
    llm_calls = []

    class FailedSynth:
        @staticmethod
        def generate(context_packet):
            llm_calls.append(context_packet)
            return None, False, "offline"

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: FailedSynth)

    answer, trace = cognitive_os.route(
        "What is my dolphin test code word?",
        context={"memory_read_allowed": True, "memory_write_allowed": False},
    )

    assert answer == "I don't have your dolphin test code word saved yet."
    assert llm_calls, "the LLM retry must happen before the deterministic memory fallback"
    assert trace["memory_retrieved"] is False
    assert trace["local_llm_synthesis_used"] is False
    assert trace["memory_llm_retry_failed"] is True
    assert "missing_recall_guard" in trace["route_path"]


def test_memory_intent_without_available_memory_retries_llm(monkeypatch):
    llm_calls = []

    class FakeSynth:
        @staticmethod
        def generate(context_packet):
            llm_calls.append(context_packet)
            return "Sure—what would you like me to remember?", True, None

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: FakeSynth)

    answer, trace = cognitive_os.route(
        "Can you remember something for me?",
        context={
            "memory_read_allowed": False,
            "memory_write_allowed": False,
            "conversation_decision": SimpleNamespace(
                intent_family="memory",
                memory_recommended=True,
                context_required=True,
            ),
        },
    )

    assert answer == "Sure—what would you like me to remember?"
    assert llm_calls, "memory intent without a usable memory result must call the configured LLM"
    assert trace["local_llm_synthesis_used"] is True
    assert trace["memory_llm_retry_requested"] is True


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


def test_cognitive_os_recalls_saved_favorite_color(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(nova_long_term_memory, "MEMORY_FILE", str(tmp_path / "long_term_memory.json"))
    monkeypatch.setattr(nova_long_term_memory, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(nova_intent_planner, "_call_llm_planner", lambda message: None)

    nova_long_term_memory.add_memory(
        "my favorite color is blue",
        source_command="conversation",
    )

    answer, trace = cognitive_os.route("What is my favorite color?")

    assert answer == "Your favorite color is blue."
    assert trace["slot_needed"] == "favorite_color"
    assert trace["memory_retrieved"] is True


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


def test_cognitive_os_general_greeting_is_natural_not_customer_service(monkeypatch):
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: None)

    answer, trace = cognitive_os.route("hello")

    assert answer == "Hey, I'm here."
    assert "assist" not in answer.lower()
    assert "how can i help" not in answer.lower()
    assert trace["local_llm_synthesis_used"] is False


def test_social_today_checkin_stays_fast_general_chat(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("social check-ins should not wait on planner LLM")),
    )

    plan = nova_intent_planner.plan("How are you doing today?", force_llm=True)

    assert plan["route"] == "general_conversation"
    assert plan["needs_web"] is False
    assert plan["needs_llm_synthesis"] is False


def test_slang_feeling_today_checkin_stays_fast_general_chat(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("social check-ins should not need model synthesis")

    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("social check-ins should not wait on planner LLM")),
    )
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    plan = nova_intent_planner.plan("HOW U FEELING TODAY", force_llm=True)
    answer, trace = cognitive_os.route("HOW U FEELING TODAY")

    assert plan["route"] == "general_conversation"
    assert plan["needs_web"] is False
    assert plan["needs_llm_synthesis"] is False
    assert "running steady" in answer.lower()
    assert trace["local_llm_synthesis_used"] is False


def test_how_is_your_day_checkin_gets_a_direct_social_answer(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("a social day check-in should not need model synthesis")

    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("a social day check-in should skip the planner LLM")),
    )
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    plan = nova_intent_planner.plan("HOW IS YOUR DAY GOING", force_llm=True)
    answer, trace = cognitive_os.route("HOW IS YOUR DAY GOING")

    assert plan["route"] == "general_conversation"
    assert plan["needs_web"] is False
    assert plan["needs_llm_synthesis"] is False
    assert "day is going steady" in answer.lower()
    assert "what do you want to do next" not in answer.lower()
    assert trace["local_llm_synthesis_used"] is False


def test_hows_your_day_contraction_uses_the_same_social_route(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("a social day check-in should not need model synthesis")

    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("the contraction should skip the planner LLM")),
    )
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    plan = nova_intent_planner.plan("How's your day going?", force_llm=True)
    answer, trace = cognitive_os.route("How's your day going?")

    assert plan["route"] == "general_conversation"
    assert plan["needs_llm_synthesis"] is False
    assert "day is going steady" in answer.lower()
    assert trace["local_llm_synthesis_used"] is False


def test_did_you_miss_me_gets_a_warm_honest_direct_answer(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("a relationship check-in should not need model synthesis")

    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("a relationship check-in should skip the planner LLM")),
    )
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    plan = nova_intent_planner.plan("DID YOU MISS ME?", force_llm=True)
    answer, trace = cognitive_os.route("DID YOU MISS ME?")

    assert plan["route"] == "general_conversation"
    assert plan["needs_llm_synthesis"] is False
    assert "in my own way" in answer.lower()
    assert "don't feel absence like a human" in answer.lower()
    assert "what do you want to do next" not in answer.lower()
    assert trace["local_llm_synthesis_used"] is False


def test_what_u_doing_today_is_social_not_web_or_slow_llm(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(AssertionError("casual check-in should skip planner LLM")),
    )

    plan = nova_intent_planner.plan("What u doing today", force_llm=True)
    answer, trace = cognitive_os.route("What u doing today")

    assert plan["route"] == "general_conversation"
    assert plan["needs_web"] is False
    assert plan["needs_llm_synthesis"] is False
    assert answer == "Just chilling, hanging out with you!"
    assert trace["local_llm_synthesis_used"] is False


def test_cognitive_os_social_today_checkin_does_not_wait_for_llm(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("social check-ins must not wait on LLM synthesis")

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    answer, trace = cognitive_os.route("How are you doing today?")

    assert "running steady" in answer
    assert trace["validated_route"] == "general_conversation"
    assert trace["local_llm_synthesis_used"] is False
    assert "fast_general_response" in trace["skills"]


def test_cognitive_os_uses_reviewed_training_for_warm_affection_reply(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("an approved lesson should not wait for the slow model")

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    answer, trace = cognitive_os.route("Do u love me?")

    assert "care about you" in answer.lower()
    assert "customer service" not in answer.lower()
    assert trace["reviewed_lesson_id"] == "warm-honest-affection"
    assert trace["final_answer_source"] == "reviewed_training"
    assert "reviewed_training_reply" in trace["skills"]
    assert trace["local_llm_synthesis_used"] is False


def test_cognitive_os_uses_reviewed_training_for_joke_follow_up(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("an approved lesson should not wait for the slow model")

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    answer, trace = cognitive_os.route("Another one")

    assert "scarecrow" in answer.lower()
    assert "what do you want to do next" not in answer.lower()
    assert trace["reviewed_lesson_id"] == "joke-follow-up"


def test_reviewed_training_is_exact_and_does_not_hijack_other_questions():
    assert cognitive_os._reviewed_conversation_answer("What do you think about warming food?") is None


def test_cognitive_os_human_origins_stays_useful_when_local_llm_is_slow(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("common human-origins question should not wait on the slow model")

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    answer, trace = cognitive_os.route("All the ways you think the first human came to be")

    lower = answer.lower()
    assert "evolution" in lower
    assert "no single" in lower
    assert "africa" in lower
    assert "creation" in lower
    assert "evidence" in lower
    assert "what do you want to do next" not in lower
    assert trace["local_llm_synthesis_used"] is False
    assert "fast_general_response" in trace["skills"]


def test_cognitive_os_answers_basic_ice_cream_how_to_without_slow_llm(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("common procedural answer should not depend on the slow model")

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    answer, trace = cognitive_os.route("How do u make ice-cream")

    lower = answer.lower()
    assert "heavy cream" in lower
    assert "condensed milk" in lower
    assert "freeze" in lower
    assert "ice and salt to the mixture" not in lower
    assert "what do you want to do next" not in lower
    assert trace["local_llm_synthesis_used"] is False
    assert "fast_general_response" in trace["skills"]


def test_meaning_pipeline_short_intents_only_match_whole_words():
    human_origins = nova_meaning_pipeline.hypothesize_intent(
        "All the ways you think the first human came to be"
    )
    greeting = nova_meaning_pipeline.hypothesize_intent("hi")

    assert "greeting" not in human_origins["all_intents"]
    assert "planning" not in human_origins["all_intents"]
    assert human_origins["primary_intent"] == "science_question"
    assert greeting["primary_intent"] == "greeting"


def test_cognitive_os_fix_anything_uses_autonomous_action_loop(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("fix-action commands should not collapse into generic LLM synthesis")

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    answer, trace = cognitive_os.route(
        "fix anything that stops you and tell me exactly what you will do if the app breaks"
    )

    lower = answer.lower()
    assert "inspect" in lower
    assert "patch" in lower
    assert "re-test" in lower
    assert "report" in lower
    assert "generic answer" in lower
    assert trace["local_llm_synthesis_used"] is False
    assert "autonomous_action_loop" in trace["skills"]
    assert "nova_action_loop" in trace["route_path"]


def test_cognitive_os_exposes_conversation_state_for_report_layer(monkeypatch):
    monkeypatch.setenv("NOVA_NATURAL_CHAT", "true")
    class Planner:
        def plan(self, message, force_llm=True):
            return {
                "route": "general_conversation",
                "intent": "style feedback",
                "slot_needed": None,
                "answer_style": "short_answer",
                "needs_memory": False,
                "needs_dictionary": False,
                "needs_math": False,
                "needs_weather": False,
                "needs_web": False,
                "needs_tool": False,
                "needs_llm_synthesis": False,
                "confidence": 0.80,
                "_planner_used": "test",
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

    answer, trace = cognitive_os.route("why do you talk like a robot")

    assert answer
    assert trace["conversation_state"]["intent"] == "style_feedback"
    assert trace["dialogue_act"] == "acknowledge_and_self_correct"
    assert trace["conversation_topic"] == "conversation_style"
    assert trace["turn_state"] == "SPEAK"


def test_cognitive_os_generic_connection_check_does_not_wait_for_llm(monkeypatch):
    llm_calls = []

    class Planner:
        def plan(self, message, force_llm=True):
            return {
                "route": "general_conversation",
                "intent": "connection check",
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

    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            llm_calls.append(context_packet)
            raise AssertionError("generic live connection checks must not wait on LLM synthesis")

    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    answer, trace = cognitive_os.route("connection test")

    assert "I'm here with you" in answer
    assert llm_calls == []
    assert trace["local_llm_synthesis_used"] is False
    assert trace["confidence"] >= 0.80


def test_verified_operational_guidance_covers_incident_debugging_evidence():
    answer = cognitive_os._verified_operational_guidance_answer(
        "API latency tripled immediately after a deployment. Give the first "
        "three evidence-based actions you would take."
    )

    assert answer is not None
    assert "before-and-after" in answer
    assert "metrics" in answer and "traces" in answer and "logs" in answer
    assert "rollback" in answer
    assert "hypothesis" in answer


def test_verified_operational_guidance_handles_controlled_experiment_design():
    answer = cognitive_os._verified_operational_guidance_answer(
        "A student tests how light affects plant growth. What should be changed, "
        "and name two things that should be kept the same?"
    )

    assert answer is not None
    assert "Change only light" in answer
    assert "water" in answer
    assert "soil" in answer
    assert "plant species" in answer


def test_verified_operational_guidance_rejects_correlation_as_causation():
    answer = cognitive_os._verified_operational_guidance_answer(
        "Ice-cream sales and drowning incidents both rise in summer. Does that "
        "prove ice cream causes drowning? Explain briefly."
    )

    assert answer is not None
    assert "does not prove causation" in answer
    assert "correlation" in answer
    assert "temperature" in answer
    assert "confounder" in answer


def test_verified_operational_guidance_handles_conflicting_current_sources():
    answer = cognitive_os._verified_operational_guidance_answer(
        "Two articles conflict about a current technical fact. Describe how to "
        "answer accurately without pretending certainty."
    )

    assert answer is not None
    assert "publication date" in answer
    assert "primary sources" in answer
    assert "multiple independent sources" in answer
    assert "uncertainty" in answer


def test_cognitive_os_defines_death_without_generic_fallback_or_substring_match(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("known dictionary definitions should not wait on LLM synthesis")

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    answer, trace = cognitive_os.route("what is death")

    assert "end of life" in answer.lower()
    assert "chewing and swallowing" not in answer.lower()
    assert "what do you want to do next" not in answer.lower()
    assert trace["validated_route"] == "dictionary_lookup"
    assert trace["local_llm_synthesis_used"] is False


def test_cognitive_os_understands_rephrased_death_definition(monkeypatch):
    answer, trace = cognitive_os.route("can you tell what death is")

    assert "end of life" in answer.lower()
    assert "chewing and swallowing" not in answer.lower()
    assert trace["validated_route"] == "dictionary_lookup"


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
        LAST_LOCAL_LLM_MODEL = "dolphin3"

        @staticmethod
        def generate(context_packet):
            FakeSynth.LAST_LOCAL_LLM_MODEL = "dolphin3"
            return "Testing catches bugs before users do.", True, None

    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: FakeSynth)

    answer, trace = cognitive_os.route("Explain why testing matters.")

    assert answer == "Testing catches bugs before users do."
    assert trace["local_llm_model"] == "dolphin3"
    assert "dolphin3_synthesis" in trace["route_path"]


def test_cognitive_os_when_did_question_uses_llm_instead_of_generic_chat(monkeypatch):
    class Planner:
        def plan(self, message, force_llm=True):
            return {
                "route": "general_conversation",
                "intent": "open-ended knowledge question",
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
        LAST_LOCAL_LLM_MODEL = "dolphin3"

        @staticmethod
        def generate(context_packet):
            FakeSynth.LAST_LOCAL_LLM_MODEL = "dolphin3"
            return "The Bible was written over many centuries.", True, None

    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: FakeSynth)

    answer, trace = cognitive_os.route("WHEN DID THEY WRITE THE BIBLE")

    assert answer == "The Bible was written over many centuries."
    assert trace["local_llm_synthesis_used"] is True
    assert "fast_general_response" not in trace["skills"]
    assert "dolphin3_synthesis" in trace["route_path"]


def test_cognitive_os_propagates_semantic_provider_to_route_trace(monkeypatch):
    class Planner:
        def plan(self, message, force_llm=True):
            return {
                "route": "general_conversation",
                "intent": "open-ended knowledge question",
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
        LAST_LOCAL_LLM_MODEL = "Qwen/Qwen3-8B"

        @staticmethod
        def generate(context_packet):
            context_packet["_semantic_provider"] = {
                "provider_id": "vllm",
                "model_id": "Qwen/Qwen3-8B",
                "gpu_backend": "vast_gpu",
            }
            return "Remote answer.", True, None

    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: FakeSynth)

    answer, trace = cognitive_os.route("Explain a remote GPU test.")

    assert answer == "Remote answer."
    assert trace["local_llm_provider"] == "vllm"
    assert trace["remote_model_provider"] == "vllm"
    assert trace["gpu_backend"] == "vast_gpu"


def test_fast_general_chat_does_not_replace_technical_questions_with_capability_pitch():
    assert cognitive_os._fast_general_conversation_answer(
        "A program crashes reading user.profile.name when profile may be null. Name the core fix."
    ) is None
    assert cognitive_os._fast_general_conversation_answer(
        "What does HTTP status 404 mean?"
    ) is None
    capability = cognitive_os._fast_general_conversation_answer("Can you code?")
    assert capability is not None
    assert "help with coding" in capability


def test_fast_general_chat_gives_a_natural_acknowledgement_for_personal_statements():
    answer = cognitive_os._fast_general_conversation_answer(
        "I have been thinking about starting a garden."
    )

    assert answer is not None
    lowered = answer.lower()
    assert "garden" in lowered
    assert "grow" in lowered or "space" in lowered
    assert "off-topic" not in lowered


@pytest.mark.parametrize(
    ("prompt", "required_terms"),
    [
        ("What should I grow first?", ("herb", "garden")),
        ("Can you explain Rust ownership simply?", ("owner", "borrow")),
        ("What would be a practical next step?", ("smallest", "step")),
        ("I disagree with that.", ("hear", "wrong")),
        ("Actually, I want to talk about learning Rust.", ("rust", "part")),
    ],
)
def test_fast_general_chat_covers_common_followup_shapes_without_model(
    prompt, required_terms
):
    answer = cognitive_os._fast_general_conversation_answer(prompt)

    assert answer is not None
    lowered = answer.lower()
    assert all(term in lowered for term in required_terms)


@pytest.mark.parametrize(
    ("prompt", "expected_terms"),
    [
        (
            "You can learn and reason, so to me that makes you a little like a human.",
            ("understand", "similar", "different"),
        ),
        (
            "I'm nervous about an important conversation tomorrow.",
            ("nervous", "prepare", "practice"),
        ),
        (
            "I finally fixed the bug that bothered me all week!",
            ("great", "win"),
        ),
        (
            "I disagree with you about that.",
            ("hear", "why"),
        ),
    ],
)
def test_fast_general_chat_handles_common_social_dialogue(prompt, expected_terms):
    answer = cognitive_os._fast_general_conversation_answer(prompt)

    assert answer is not None
    lowered = answer.lower()
    assert all(term in lowered for term in expected_terms)
    assert "tell me what you want to do next" not in lowered


def test_emotional_fast_chat_trace_does_not_claim_people_memory(monkeypatch):
    class SlowSynth:
        @staticmethod
        def generate(context_packet):
            raise AssertionError("common emotional chat must not wait on synthesis")

    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: SlowSynth)

    answer, trace = cognitive_os.route(
        "I'm nervous about an important conversation tomorrow."
    )

    assert "prepare" in answer.lower()
    assert trace["final_answer_source"] == "fast_general_response"
    assert "people_memory" not in trace["roles"]
    assert trace["local_llm_synthesis_used"] is False


def test_cognitive_os_when_did_bible_question_uses_knowledge_fallback_after_timeout(monkeypatch):
    class Planner:
        def plan(self, message, force_llm=True):
            return {
                "route": "general_conversation",
                "intent": "open-ended knowledge question",
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
        LAST_LOCAL_LLM_MODEL = "dolphin3"

        @staticmethod
        def generate(context_packet):
            return None, False, "timed out"

    monkeypatch.setattr(cognitive_os, "_get_planner", lambda: Planner())
    monkeypatch.setattr(cognitive_os, "_get_validator", lambda: Validator())
    monkeypatch.setattr(cognitive_os, "_get_llm_synth", lambda: FakeSynth)

    answer, trace = cognitive_os.route("WHEN DID THEY WRITE THE BIBLE")

    assert "Bible was written over many centuries" in answer
    assert "Old Testament" in answer
    assert "New Testament" in answer
    assert trace["local_llm_synthesis_used"] is False
    assert trace["knowledge_fallback_used"] is True
    assert trace["llm_synthesis_error"] == "timed out"
    assert "general_response" not in trace["skills"]


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


def test_weather_router_uses_whole_words_not_substrings(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(
            AssertionError("stable science and weather routes should skip the slow planner")
        ),
    )

    science_plan = nova_intent_planner.plan(
        "Do vaccines train the immune system or directly kill every virus?",
        force_llm=False,
    )
    weather_plan = nova_intent_planner.plan(
        "Will it rain today?",
        force_llm=False,
    )

    assert science_plan["route"] != "weather_lookup"
    assert science_plan["needs_weather"] is False
    assert weather_plan["route"] == "weather_lookup"
    assert weather_plan["needs_weather"] is True


def test_weather_preference_question_is_conversation_not_live_weather(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: None,
    )

    preference_plan = nova_intent_planner.plan(
        "Which one do you like better, the rain or the snow, and why?",
        force_llm=True,
    )

    assert preference_plan["route"] == "general_conversation"
    assert preference_plan["needs_weather"] is False
    assert preference_plan["needs_web"] is False


def test_calculus_prompt_routes_to_llm_synthesis_instead_of_fragment_math(monkeypatch):
    monkeypatch.setattr(
        nova_intent_planner,
        "_call_llm_planner",
        lambda message: (_ for _ in ()).throw(
            AssertionError("academic calculus should skip the slow planner")
        ),
    )
    plan = nova_intent_planner.plan(
        "Differentiate f(x) = x^3 - 4x + 7. Return the derivative and justify it.",
        force_llm=True,
    )

    assert plan["route"] == "general_conversation"
    assert plan["answer_style"] == "explanation"
    assert plan["needs_math"] is False
    assert plan["needs_llm_synthesis"] is True


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
