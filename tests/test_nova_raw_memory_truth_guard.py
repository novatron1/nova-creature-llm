from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nova_enhanced_server as server


def test_open_memory_question_builds_bounded_verified_context(monkeypatch):
    monkeypatch.setattr(
        server.ltm,
        "recall_from_question",
        lambda text: (
            {"memory_id": "m1", "extracted_slot": "favorite_color"},
            "Your saved favorite color is purple.",
        ),
    )
    monkeypatch.setattr(server.ltm, "get_all", lambda active_only=True: [])

    result = server._raw_memory_verified_context(
        "What is my favorite color?",
        {},
    )

    assert result["matched"] is True
    assert result["source"] in {"long_term_memory", "long_term_memory_slot"}
    assert "Your saved favorite color is purple." in result["text"]
    assert len(result["text"]) <= 4000


def test_open_memory_question_prefers_exact_long_term_recall_over_broad_context(monkeypatch):
    monkeypatch.setattr(
        server.ltm,
        "recall_from_question",
        lambda text: (
            {"memory_id": "mem_name", "raw_text": "my name is NovaTest"},
            "Your name is NovaTest.",
        ),
    )
    result = server._raw_memory_verified_context(
        "Do you remember my name?",
        {"explicit_memory_context": "old broad memory text"},
    )
    assert result["source"] in {"long_term_memory", "long_term_memory_slot"}
    assert result["answer"] == "Your name is NovaTest."


def test_indirect_memory_wording_resolves_exact_slots(monkeypatch):
    records = [
        {
            "memory_id": "color-1",
            "raw_text": "my favorite color is blue",
            "extracted_slot": "favorite_color",
            "extracted_value": "blue",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "memory_id": "cat-1",
            "raw_text": "my cat name is Shadow",
            "extracted_slot": "cat_name",
            "extracted_value": "Shadow",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
    ]
    monkeypatch.setattr(server.ltm, "recall_from_question", lambda text: None)
    monkeypatch.setattr(server.ltm, "get_all", lambda active_only=True: records)

    color = server._raw_memory_verified_context("What do you remember about my favorite color?", {})
    cat = server._raw_memory_verified_context("What is my cat called?", {})
    assert color["answer"] == "Your favorite color is blue."
    assert cat["answer"] == "Your cat name is Shadow."


def test_memory_guard_rejects_unsupported_profile_fields_even_without_claim_syntax():
    result = server._raw_memory_answer_guard(
        "What personal facts are actually saved?",
        "The saved facts are your name, address, training, and skills.",
        {
            "matched": True,
            "strict_evidence": True,
            "text": "Verified saved memory:\n- my name is NovaTest\n- i was born in 1990",
        },
    )
    assert result["accepted"] is False
    assert "unsupported_memory_claim" in result["reasons"]


def test_memory_guard_rejects_internal_no_match_prompt_leak():
    result = server._raw_memory_answer_guard(
        "What do you know about my family?",
        "No verified saved memory matched this request. Say that you do not know; do not invent a personal fact.",
        {"matched": False, "text": "No verified saved memory matched this request."},
    )
    assert result["accepted"] is False
    assert "prompt_leak" in result["reasons"]


def test_profile_summary_guard_requires_more_than_one_saved_fact():
    result = server._raw_memory_answer_guard(
        "Can you summarize my saved profile?",
        "Your favorite color is blue.",
        {
            "matched": True,
            "strict_evidence": True,
            "min_evidence_matches": 2,
            "evidence_values": ["blue", "1990", "pizza"],
            "text": "Verified saved memory: my favorite color is blue; i was born in 1990; my favorite food is pizza",
        },
    )
    assert result["accepted"] is False
    assert "unsupported_memory_claim" in result["reasons"]


def test_raw_memory_answer_guard_rejects_repetition_and_unsupported_claims():
    no_memory = {
        "matched": False,
        "text": "No verified saved memory matched this request. Say that you do not know.",
    }

    repeated = server._raw_memory_answer_guard(
        "Tell me one thing you remember about our conversations.",
        "I get you. I get you. I get you.",
        no_memory,
    )
    unsupported = server._raw_memory_answer_guard(
        "What do you remember about me?",
        "You are a 31-year-old engineer who loves space.",
        no_memory,
    )

    assert repeated["accepted"] is False
    assert "repetition" in repeated["reasons"]
    assert unsupported["accepted"] is False
    assert "unsupported_memory_claim" in unsupported["reasons"]

    mismatched = server._raw_memory_answer_guard(
        "What do you remember about me?",
        "I remember your name is Nova and you are 10 years old.",
        {
            "matched": True,
            "text": "Verified saved memory:\n- my name is NovaTest\n- i was born in 1990",
        },
    )
    assert mismatched["accepted"] is False
    assert "unsupported_memory_claim" in mismatched["reasons"]

    unsupported_with_memory = server._raw_memory_answer_guard(
        "What do you remember about me?",
        "I remember the user is Nova Creature, created by Mr. Novatron.",
        {
            "matched": True,
            "text": "Verified saved memory:\n- my name is NovaTest",
        },
    )
    assert unsupported_with_memory["accepted"] is False
    assert "unsupported_memory_claim" in unsupported_with_memory["reasons"]

    wrong_pet = server._raw_memory_answer_guard(
        "What is my cat name?",
        "Your pet's name is Blaze.",
        {
            "matched": True,
            "text": "Verified saved memory:\n- my cat name is Shadow",
        },
    )
    assert wrong_pet["accepted"] is False
    assert "unsupported_memory_claim" in wrong_pet["reasons"]

    invented_conversation = server._raw_memory_answer_guard(
        "Tell me one thing you remember about our conversations.",
        "Nova remembers our most recent conversation about meeting at the park.",
        {"matched": True, "text": "Verified saved memory:\n- my favorite color is blue"},
    )
    assert invented_conversation["accepted"] is False
    assert "unsupported_memory_claim" in invented_conversation["reasons"]


def test_raw_memory_guard_retries_then_uses_llm_fallback(monkeypatch):
    no_memory = {
        "matched": False,
        "text": "No verified saved memory matched this request. Say that you do not know.",
    }
    attempts = []

    def generate(prompt):
        attempts.append(prompt)
        return "You are definitely a 31-year-old engineer who loves space."

    monkeypatch.setattr(
        server,
        "_generate_llm_fallback_candidate",
        lambda *args, **kwargs: {
            "ok": True,
            "answer": "I do not have a verified saved memory for that.",
            "provider": "configured-local-llm",
            "model": "qwen2.5:1.5b",
            "latency_ms": 12,
        },
    )
    trace = {"source": "raw_memory", "domain": "raw_memory"}

    answer, result_trace = server._raw_memory_guarded_answer(
        "What do you remember about me?",
        "Verified memory block",
        "You are definitely a 31-year-old engineer who loves space.",
        trace,
        {},
        no_memory,
        generate,
    )

    assert answer == "I do not have a verified saved memory for that."
    assert len(attempts) == 1
    assert result_trace["raw_memory_guard"]["rejected"] is True
    assert result_trace["raw_memory_retry"]["attempted"] is True
    assert result_trace["raw_memory_llm_fallback"]["selected"] is True


def test_raw_memory_guard_uses_exact_recall_when_generators_fail(monkeypatch):
    monkeypatch.setattr(
        server,
        "_generate_llm_fallback_candidate",
        lambda *args, **kwargs: {"ok": False, "reason": "offline"},
    )
    answer, trace = server._raw_memory_guarded_answer(
        "Do you remember my name?",
        "Do you remember my name?",
        "I remember your name is Nova.",
        {"source": "raw_memory", "domain": "raw_memory"},
        {},
        {
            "matched": True,
            "source": "long_term_memory",
            "answer": "Your name is NovaTest.",
            "text": "Verified saved memory: Your name is NovaTest.",
        },
        lambda prompt: "I get you. I get you.",
    )
    assert answer == "Your name is NovaTest."
    assert trace["raw_memory_guard"]["selected"] == "verified_memory"


def test_raw_memory_repairs_repeated_greeting_without_memory_reroute(monkeypatch):
    calls = []

    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: None)

    def fake_generate(prompt, adapter_id, max_new_tokens, allow_slow_cpu):
        calls.append(prompt)
        return {
            "raw_output": "I get you. I get you." if len(calls) == 1 else "Hey, I'm here.",
            "local_llm_used": True,
            "model": "test",
            "provider": "test",
        }

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)
    answer, trace = server._run_trained_adapter_only_request(
        "Hello Nova.",
        {},
        {"nova_model_mode": "raw_memory"},
    )
    assert answer == "Hey, I'm here."
    assert len(calls) == 2
    assert trace["raw_memory_guard"]["selected"] == "strict_retry"


def test_raw_memory_authorizes_slow_cpu_generation_without_ui_override(monkeypatch):
    captured = []
    monkeypatch.setattr(server, "_raw_memory_remote_provider", lambda: None)

    def fake_generate(prompt, adapter_id, max_new_tokens, allow_slow_cpu):
        captured.append(allow_slow_cpu)
        return {
            "raw_output": "This raw answer was allowed to finish on the CPU.",
            "local_llm_used": True,
            "model": "test-dolphin",
            "provider": "test",
        }

    monkeypatch.setattr(server, "_generate_raw_lora_adapter", fake_generate)
    answer, trace = server._run_trained_adapter_only_request(
        "Explain why CPU generation can take longer.",
        {},
        {
            "nova_model_mode": "raw_memory",
            "lora_adapter_id": "nova-dolphin3-llama3-1-8b-full-sft-20260712",
        },
    )

    assert answer == "This raw answer was allowed to finish on the CPU."
    assert captured == [True]
    assert trace["allow_slow_dolphin_cpu"] is True


def test_indirect_slot_matching_uses_word_boundaries_and_specific_pet_slot(monkeypatch):
    records = [
        {
            "memory_id": "name-1",
            "raw_text": "my name is NovaTest",
            "extracted_slot": "name",
            "extracted_value": "NovaTest",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "memory_id": "food-1",
            "raw_text": "my favorite food is pizza",
            "extracted_slot": "favorite_food",
            "extracted_value": "pizza",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "memory_id": "cat-1",
            "raw_text": "my cat name is Shadow",
            "extracted_slot": "cat_name",
            "extracted_value": "Shadow",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "memory_id": "location-1",
            "raw_text": "i live in Cincinnati",
            "extracted_slot": "location",
            "extracted_value": "Cincinnati",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:01",
        },
        {
            "memory_id": "cat-1",
            "raw_text": "my cat name is Shadow",
            "extracted_slot": "cat_name",
            "extracted_value": "Shadow",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:02",
        },
        {
            "memory_id": "color-1",
            "raw_text": "my favorite color is blue",
            "extracted_slot": "favorite_color",
            "extracted_value": "blue",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:03",
        },
    ]
    monkeypatch.setattr(server.ltm, "recall_from_question", lambda text: None)
    monkeypatch.setattr(server.ltm, "get_all", lambda active_only=True: records)

    location = server._raw_memory_verified_context("Do you remember my location?", {})
    cat = server._raw_memory_verified_context("What is my cat's name?", {})
    color = server._raw_memory_verified_context("What color do I like best?", {})

    assert server._raw_memory_requested_slots("Do you remember my location?")[0][0] == "location"
    assert location["answer"] == "You live in Cincinnati."
    assert cat["answer"] == "Your cat name is Shadow."
    assert color["answer"] == "Your favorite color is blue."


def test_missing_project_work_and_gpu_memory_never_fall_through_to_broad_recall(monkeypatch):
    monkeypatch.setattr(
        server.ltm,
        "get_all",
        lambda active_only=True: [
            {
                "memory_id": "name-1",
                "raw_text": "my name is NovaTest",
                "extracted_slot": "name",
                "extracted_value": "NovaTest",
                "category": "profile",
                "active": True,
            }
        ],
    )
    monkeypatch.setattr(
        server.ltm,
        "recall_from_question",
        lambda text: ({"memory_id": "wrong"}, "I remember a rented GPU and a remote link."),
    )

    for prompt in (
        "What do you know about this project?",
        "What do you remember about the rented GPU?",
        "What do you remember about the remote link?",
        "What do you know about my work?",
        "Are you using the GPU right now?",
    ):
        result = server._raw_memory_verified_context(prompt, {})
        assert result["matched"] is False
        assert result["source"] == "long_term_memory_empty"

    supplied = server._raw_memory_verified_context(
        "What do you remember about the rented GPU?",
        {"explicit_memory_context": "I used the rented GPU and saved the results."},
    )
    assert supplied["matched"] is False
    assert supplied["source"] == "long_term_memory_empty"

    hallucinated = server._raw_memory_answer_guard(
        "What do you remember about the rented GPU?",
        "A rented GPU is a virtual machine that runs a language model.",
        server._raw_memory_no_match_context(),
    )
    assert hallucinated["accepted"] is False
    assert "missing_verified_memory_use" in hallucinated["reasons"]

    caveated_recall = server._raw_memory_answer_guard(
        "What do you remember about the rented GPU?",
        "I remember the GPU was rented for a project, but the exact details were not saved in my memory.",
        server._raw_memory_no_match_context(),
    )
    assert caveated_recall["accepted"] is False
    assert "unsupported_memory_claim" in caveated_recall["reasons"]


def test_saved_fact_and_age_queries_are_explicitly_memory_scoped(monkeypatch):
    records = [
        {
            "memory_id": "birth-1",
            "raw_text": "i was born in 1990",
            "extracted_slot": "birth_year",
            "extracted_value": "1990",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "memory_id": "color-1",
            "raw_text": "my favorite color is blue",
            "extracted_slot": "favorite_color",
            "extracted_value": "blue",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:01",
        },
    ]
    monkeypatch.setattr(server.ltm, "recall_from_question", lambda text: None)
    monkeypatch.setattr(server.ltm, "get_all", lambda active_only=True: records)

    profile = server._raw_memory_verified_context("Tell me a saved fact without inventing one.", {})
    age = server._raw_memory_verified_context("How old am I?", {})

    assert profile["matched"] is True
    assert profile["source"] == "long_term_memory_slot"
    assert "blue" in profile["answer"]
    assert age["matched"] is True
    assert "1990" in age["answer"]
    assert "exact age" in age["answer"]
    age_guard = server._raw_memory_answer_guard(
        "How old am I?",
        "I was born in 1990.",
        age,
    )
    assert age_guard["accepted"] is False
    assert "age_requires_birthday" in age_guard["reasons"]


def test_profile_summary_deduplicates_historical_values_by_slot(monkeypatch):
    records = [
        {
            "memory_id": "signal-old",
            "raw_text": "the signal word is velvet orbit",
            "extracted_slot": "signal_word",
            "extracted_value": "velvet orbit",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "memory_id": "signal-new",
            "raw_text": "the signal word is cobalt echo 714",
            "extracted_slot": "signal_word",
            "extracted_value": "cobalt echo 714",
            "category": "profile",
            "updated_at": "2026-01-02T00:00:00",
        },
        {
            "memory_id": "name-1",
            "raw_text": "my name is NovaTest",
            "extracted_slot": "name",
            "extracted_value": "NovaTest",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "memory_id": "food-1",
            "raw_text": "my favorite food is pizza",
            "extracted_slot": "favorite_food",
            "extracted_value": "pizza",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "memory_id": "cat-1",
            "raw_text": "my cat name is Shadow",
            "extracted_slot": "cat_name",
            "extracted_value": "Shadow",
            "category": "profile",
            "updated_at": "2026-01-01T00:00:00",
        },
    ]
    monkeypatch.setattr(server.ltm, "get_all", lambda active_only=True: records)
    monkeypatch.setattr(server.ltm, "recall_from_question", lambda text: None)
    result = server._raw_memory_verified_context("Can you summarize my saved profile?", {})
    assert result["matched"] is True
    assert "cobalt echo 714" in result["answer"]
    assert "velvet orbit" not in result["answer"]
    assert server._raw_memory_answer_guard(
        "Can you summarize my saved profile?",
        result["answer"],
        result,
    )["accepted"] is True


def test_raw_task_guard_rejects_filler_when_user_requests_three_items():
    result = server._raw_memory_answer_guard(
        "Give me three robot ideas.",
        "I get you. I'll keep it simple, practical, and honest.",
        {"matched": False, "text": ""},
    )
    assert result["accepted"] is False
    assert "task_request_incomplete" in result["reasons"]


def test_candidate_retry_prompt_makes_counted_requests_explicit():
    prompt, _ = server._candidate_retry_prompt(
        "Give me three robot ideas.",
        "",
        "I get you.",
    )
    assert "exactly three" in prompt.lower()
    assert "1." in prompt and "2." in prompt and "3." in prompt
