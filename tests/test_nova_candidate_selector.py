from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_answer_firewall import evaluate_answer  # noqa: E402
from nova_candidate_selector import (  # noqa: E402
    AnswerCandidate,
    choose_candidate,
    score_candidate,
    select_alternate_model,
)


def capability(
    model_id,
    *,
    provider_id="local",
    size=1_000_000_000,
    location="local",
    cost="free",
    health="healthy",
    availability="available",
):
    return SimpleNamespace(
        model_id=model_id,
        provider_id=provider_id,
        display_name=model_id,
        text_input=True,
        text_output=True,
        reasoning=True,
        local_or_remote=location,
        estimated_cost_type=cost,
        health_status=health,
        availability=availability,
        metadata={"size": size},
    )


def test_model_selector_prefers_different_small_healthy_local_free_model():
    models = [
        capability("primary:latest", size=4_000_000_000),
        capability("small-general", size=900_000_000),
        capability("remote-small", location="remote", size=100_000_000),
        capability("paid-small", cost="paid", size=100_000_000),
        capability("unhealthy-small", health="unhealthy", size=100_000_000),
    ]

    selected, trace = select_alternate_model(
        models,
        primary_model="primary",
        maximum_model_bytes=2_500_000_000,
    )

    assert selected.model_id == "small-general"
    assert trace["selected_different_from_primary"] is True
    assert trace["eligible_count"] == 1
    reasons = {item["reason"] for item in trace["rejections"]}
    assert {"over_memory_policy", "remote", "paid", "unhealthy"}.issubset(reasons)


def test_model_selector_can_reuse_primary_only_when_no_independent_model_exists():
    selected, trace = select_alternate_model(
        [capability("only-model:latest", size=800_000_000)],
        primary_model="only-model",
        maximum_model_bytes=2_500_000_000,
    )

    assert selected.model_id == "only-model:latest"
    assert trace["selected_different_from_primary"] is False


def test_model_selector_escalates_to_preferred_larger_local_model():
    models = [
        capability("small-general", size=900_000_000),
        capability("large-general:latest", size=5_000_000_000),
        capability("large-reasoner:latest", size=4_700_000_000),
    ]

    selected, trace = select_alternate_model(
        models,
        primary_model="small-general",
        minimum_model_bytes=3_000_000_000,
        maximum_model_bytes=8_000_000_000,
        preferred_model_ids=("large-reasoner", "large-general"),
        prefer_larger=True,
    )

    assert selected.model_id == "large-reasoner:latest"
    assert trace["selected_different_from_primary"] is True
    assert trace["prefer_larger"] is True
    assert any(item["reason"] == "below_escalation_size" for item in trace["rejections"])


def test_model_selector_can_exclude_failed_middle_tier_before_deep_fallback():
    models = [
        capability("qwen2.5:3b", size=2_000_000_000),
        capability("qwen2.5-coder:7b", size=4_700_000_000),
    ]

    selected, trace = select_alternate_model(
        models,
        primary_model="qwen2.5:1.5b",
        minimum_model_bytes=3_000_000_000,
        maximum_model_bytes=8_000_000_000,
        preferred_model_ids=("qwen2.5-coder:7b",),
        prefer_larger=True,
        excluded_model_ids=("qwen2.5:3b",),
    )

    assert selected.model_id == "qwen2.5-coder:7b"
    assert trace["excluded_model_count"] == 1
    assert any(item["reason"] == "excluded_from_tier" for item in trace["rejections"])


def test_model_selector_middle_tier_requires_configured_model_alias():
    models = [
        capability("moondream:latest", size=1_700_000_000),
        capability("qwen2.5:3b", size=2_000_000_000),
    ]

    selected, trace = select_alternate_model(
        models,
        minimum_model_bytes=1_500_000_000,
        maximum_model_bytes=3_000_000_000,
        preferred_model_ids=("qwen2.5:3b",),
        require_preferred=True,
    )

    assert selected.model_id == "qwen2.5:3b"
    assert trace["require_preferred"] is True
    assert any(item["reason"] == "not_enabled_for_tier" for item in trace["rejections"])


def test_candidate_tournament_selects_firewall_passed_relevant_answer():
    rejected_text = "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app."
    accepted_text = "Mix cream, milk, sugar, and vanilla; chill it, churn it, then freeze until firm."
    rejected = AnswerCandidate(
        candidate_id="primary",
        answer=rejected_text,
        source="cognitive_os",
        provider="existing-nova",
        model="nova",
        firewall=evaluate_answer("How do I make ice cream?", rejected_text),
        relevance_text="How do I make ice cream?",
        trace_confidence=0.85,
    )
    accepted = AnswerCandidate(
        candidate_id="alternate_local",
        answer=accepted_text,
        source="provider_candidate",
        provider="local",
        model="small-general",
        firewall=evaluate_answer("How do I make ice cream?", accepted_text),
        relevance_text="How do I make ice cream?",
        trace_confidence=0.82,
        metadata={"different_model": True},
    )

    winner, ranked = choose_candidate([rejected, accepted])

    assert winner is not None
    assert winner.candidate.candidate_id == "alternate_local"
    assert ranked[0].score > ranked[1].score
    assert ranked[1].score == 0.0


def test_candidate_tournament_penalizes_self_reported_uncertainty():
    uncertain_text = "I am not sure because I do not have enough information."
    stronger_text = "The larger local model supplies a direct, relevant answer with the available context."
    uncertain = AnswerCandidate(
        candidate_id="primary",
        answer=uncertain_text,
        source="cognitive_os",
        provider="hf_peft_lora",
        model="qwen-small",
        firewall=evaluate_answer("Explain the available context", uncertain_text),
        relevance_text="Explain the available context",
        trace_confidence=0.88,
        metadata={"self_reported_uncertainty": True},
    )
    stronger = AnswerCandidate(
        candidate_id="alternate_local",
        answer=stronger_text,
        source="provider_candidate",
        provider="ollama",
        model="large-general",
        firewall=evaluate_answer("Explain the available context", stronger_text),
        relevance_text="Explain the available context",
        trace_confidence=0.82,
        metadata={"different_model": True},
    )

    winner, ranked = choose_candidate([uncertain, stronger])

    assert winner is not None
    assert winner.candidate.candidate_id == "alternate_local"
    assert "self_reported_uncertainty" in ranked[1].signals


def test_candidate_tournament_penalizes_unverified_exact_claim():
    guessed_answer = (
        "The exact value of the Busy Beaver function BB(100) is 613, "
        "which is the claimed maximum output for that input."
    )
    guessed = AnswerCandidate(
        candidate_id="primary",
        answer=guessed_answer,
        source="cognitive_os",
        provider="ollama",
        model="qwen2.5:1.5b",
        firewall=evaluate_answer(
            "What is the exact Busy Beaver value?",
            guessed_answer,
            trace={"numeric_verification_required": False},
        ),
        relevance_text="What is the exact Busy Beaver value?",
        trace_confidence=0.88,
        metadata={"unverified_exact_claim": True},
    )
    careful = AnswerCandidate(
        candidate_id="alternate_local",
        answer="That exact value is not known; computing it would require resolving an undecidable search.",
        source="provider_candidate",
        provider="ollama",
        model="large-general",
        firewall=evaluate_answer(
            "What is the exact Busy Beaver value?",
            "That exact value is not known; computing it would require resolving an undecidable search.",
        ),
        relevance_text="What is the exact Busy Beaver value?",
        trace_confidence=0.82,
        metadata={"different_model": True},
    )

    winner, ranked = choose_candidate([guessed, careful])

    assert winner is not None
    assert winner.candidate.candidate_id == "alternate_local"
    assert "unverified_exact_claim" in ranked[1].signals


def test_candidate_tournament_rejects_fluid_but_unrelated_answer():
    answer = "The weather tomorrow depends on pressure systems and cloud cover in the region."
    unrelated = AnswerCandidate(
        candidate_id="alternate_local",
        answer=answer,
        source="provider_candidate",
        provider="ollama",
        model="large-general",
        firewall=evaluate_answer("How should I apologize to my friend?", answer),
        relevance_text="How should I apologize to my friend?",
        trace_confidence=0.82,
        metadata={"different_model": True},
    )

    winner, ranked = choose_candidate([unrelated])

    assert winner is None
    assert "missing_topic_overlap" in ranked[0].signals
    assert ranked[0].score < 0.68


def test_candidate_tournament_penalizes_a_shallow_primary_reply():
    shallow_text = "Be honest and kind."
    useful_text = (
        "Say, \"I care about you, and I want to be honest about what happened. "
        "I'm sorry for hurting you.\""
    )
    shallow = AnswerCandidate(
        candidate_id="primary",
        answer=shallow_text,
        source="cognitive_os",
        provider="hf_peft_lora",
        model="qwen-small",
        firewall=evaluate_answer("What should I say to apologize?", shallow_text),
        relevance_text="What should I say to apologize?",
        trace_confidence=0.85,
        metadata={"too_shallow": True},
    )
    useful = AnswerCandidate(
        candidate_id="alternate_local",
        answer=useful_text,
        source="provider_candidate",
        provider="ollama",
        model="large-general",
        firewall=evaluate_answer("What should I say to apologize?", useful_text),
        relevance_text="What should I say to apologize?",
        trace_confidence=0.82,
        metadata={"different_model": True},
    )

    winner, ranked = choose_candidate([shallow, useful])

    assert winner is not None
    assert winner.candidate.candidate_id == "alternate_local"
    assert "too_shallow" in ranked[1].signals


def test_candidate_tournament_penalizes_turning_question_back_on_user():
    answer = (
        "What if your boss says no to your request? You could wait and ask again later."
    )
    candidate = AnswerCandidate(
        candidate_id="primary",
        answer=answer,
        source="cognitive_os",
        provider="ollama",
        model="qwen2.5:1.5b",
        firewall=evaluate_answer("What if they say no?", answer),
        relevance_text="What if they say no? I asked my boss for Friday off.",
        trace_confidence=0.85,
        metadata={"question_restatement": True},
    )

    scored = score_candidate(candidate)

    assert "question_restatement" in scored.signals
    assert scored.score < 0.9


def test_candidate_tournament_penalizes_complexity_mismatch():
    prompt = "Compare two private AI memory architectures and recommend a staged design."
    shallow_text = "Local storage is private, while remote storage can scale."
    deeper_text = (
        "Start with encrypted local storage for privacy, offline access, and predictable cost. "
        "Put a provider-neutral memory interface above it, then add an opt-in remote index only "
        "for synchronized, non-private records; this limits migration risk while preserving a "
        "clear path to scale."
    )
    shallow = AnswerCandidate(
        candidate_id="primary",
        answer=shallow_text,
        source="cognitive_os",
        provider="ollama",
        model="qwen2.5:1.5b",
        firewall=evaluate_answer(prompt, shallow_text),
        relevance_text=prompt,
        trace_confidence=0.88,
        metadata={"complexity_mismatch": True},
    )
    deeper = AnswerCandidate(
        candidate_id="alternate_local",
        answer=deeper_text,
        source="provider_candidate",
        provider="ollama",
        model="deepseek-r1:7b",
        firewall=evaluate_answer(prompt, deeper_text),
        relevance_text=prompt,
        trace_confidence=0.82,
        metadata={"different_model": True},
    )

    winner, ranked = choose_candidate([shallow, deeper])

    assert winner is not None
    assert winner.candidate.candidate_id == "alternate_local"
    primary = next(item for item in ranked if item.candidate.candidate_id == "primary")
    assert "complexity_mismatch" in primary.signals


def test_candidate_tournament_rejects_unnecessary_clarification_deflection():
    prompt = "Compare two private AI memory architectures and recommend a staged design."
    answer = "What specific areas are you most interested in understanding better?"
    candidate = AnswerCandidate(
        candidate_id="primary",
        answer=answer,
        source="cognitive_os",
        provider="ollama",
        model="qwen2.5:1.5b",
        firewall=evaluate_answer(prompt, answer),
        relevance_text=prompt,
        trace_confidence=0.9,
        metadata={"clarification_deflection": True, "complexity_mismatch": True},
    )

    winner, ranked = choose_candidate([candidate])

    assert winner is None
    assert "clarification_deflection" in ranked[0].signals


def test_candidate_tournament_rejects_incomplete_explicit_aspect_list():
    prompt = "Analyze privacy, offline behavior, latency, migration risk, and cost."
    answer = "Local storage improves privacy, works offline, and lowers latency."
    candidate = AnswerCandidate(
        candidate_id="alternate_local",
        answer=answer,
        source="provider_candidate",
        provider="ollama",
        model="large-general",
        firewall=evaluate_answer(prompt, answer),
        relevance_text=prompt,
        trace_confidence=0.82,
        metadata={
            "different_model": True,
            "requested_aspect_coverage": {
                "applied": True,
                "required_count": 5,
                "covered_count": 4,
                "coverage_ratio": 0.8,
                "complete": False,
            },
        },
    )

    winner, ranked = choose_candidate([candidate])

    assert winner is None
    assert "incomplete_requested_aspects" in ranked[0].signals
    assert ranked[0].safe_summary()["requested_aspect_coverage"]["covered_count"] == 4


def test_candidate_tournament_returns_no_winner_when_every_answer_fails_firewall():
    bad_text = "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app."
    bad = AnswerCandidate(
        candidate_id="bad",
        answer=bad_text,
        source="fallback",
        provider="local",
        model="small",
        firewall=evaluate_answer("Why is the sky blue?", bad_text),
        relevance_text="Why is the sky blue?",
    )

    winner, ranked = choose_candidate([bad])

    assert winner is None
    assert ranked[0].score == 0.0


def test_candidate_trace_summary_never_contains_answer_or_prompt_content():
    answer = "A private answer body that must not enter operational trace metadata."
    candidate = AnswerCandidate(
        candidate_id="alternate_local",
        answer=answer,
        source="provider_candidate",
        provider="local",
        model="small",
        firewall=evaluate_answer("Explain privacy", answer),
        relevance_text="private user prompt",
        trace_confidence=0.8,
    )

    summary = score_candidate(candidate).safe_summary()

    assert answer not in str(summary)
    assert "private user prompt" not in str(summary)
    assert summary["answer_length"] == len(answer)
