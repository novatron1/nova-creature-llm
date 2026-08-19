from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import nova_enhanced_server as server  # noqa: E402
from nova_uncertainty_router import decide_model_escalation  # noqa: E402
from nova_local_llm_connector import LocalLLMConfig  # noqa: E402


def test_supported_social_turn_does_not_escalate():
    decision = decide_model_escalation(
        intent_family="relationship",
        difficulty_score=0.08,
        firewall_score=1.0,
        firewall_reasons=(),
        small_answer_available=True,
    )

    assert decision.should_escalate is False
    assert decision.selected_tier == "deterministic"
    assert decision.fallback_tiers == ()


def test_relevant_but_incomplete_small_answer_uses_middle_before_deep():
    decision = decide_model_escalation(
        intent_family="open_ended",
        difficulty_score=0.42,
        firewall_score=0.58,
        firewall_reasons=("incomplete_answer",),
        small_answer_available=True,
    )

    assert decision.should_escalate is True
    assert decision.selected_tier == "middle"
    assert decision.fallback_tiers == ("middle", "deep")


def test_hard_reasoning_uses_deep_then_middle_fallback():
    decision = decide_model_escalation(
        intent_family="stable_reasoning",
        difficulty_score=0.86,
        firewall_score=0.92,
        firewall_reasons=(),
        small_answer_available=True,
    )

    assert decision.should_escalate is True
    assert decision.selected_tier == "deep"
    assert decision.fallback_tiers == ("deep", "middle")
    assert decision.as_trace()["content_logged"] is False


def test_accepted_routine_small_answer_stays_on_small_model():
    decision = decide_model_escalation(
        intent_family="open_ended",
        difficulty_score=0.2,
        firewall_score=1.0,
        firewall_reasons=(),
        small_answer_available=True,
    )

    assert decision.should_escalate is False
    assert decision.selected_tier == "small"


def test_primary_cpu_timeout_covers_measured_qwen_generation_budget():
    # The exact 8K-context/140-token Qwen 1.5B provider workload took 73s on
    # this CPU. A lower timeout falsely marks a healthy primary as failed and
    # starts a much slower multi-model cascade.
    assert LocalLLMConfig().timeout >= 90


def test_cpu_profile_keeps_large_reviewer_warmup_on_demand():
    # A live startup probe showed qwen3:8b monopolizing Ollama for 180s and
    # then failing. The reviewer remains available through normal escalation.
    assert LocalLLMConfig().reviewer_warmup is False
    assert LocalLLMConfig().regular_chat_escalation_enabled is True


def _managed_test_context():
    return {
        "nova_gateway": True,
        "private_mode": True,
        "memory_read_allowed": False,
        "memory_write_allowed": False,
        "conversation_memory_allowed": False,
    }


def test_managed_incomplete_answer_attempts_middle_before_deep(monkeypatch):
    attempted = []
    rejected = "I'm here with you. Tell me what you want to do next."
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            rejected,
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["speech_output_transformer"],
                "skills": [],
                "route_path": ["cognitive_os"],
                "confidence": 0.4,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:1.5b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *args, **kwargs: {
            "selected": False,
            "reason": "below_direct_threshold",
        },
    )

    def unavailable_candidate(*args, reviewer_tier="deep", **kwargs):
        attempted.append(reviewer_tier)
        return {
            "ok": False,
            "reason": "no_eligible_local_model",
            "reviewer_tier": reviewer_tier,
        }

    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        unavailable_candidate,
    )

    _, trace = server._run_nova_chat_turn(
        "Imagine a new kind of city.",
        context=_managed_test_context(),
    )

    assert attempted == ["middle", "deep"]
    assert trace["model_escalation_policy"]["selected_tier"] == "middle"


def test_managed_hard_reasoning_attempts_deep_before_middle(monkeypatch):
    attempted = []
    monkeypatch.setattr(
        server,
        "brain_route",
        lambda text, context=None: (
            "Use layers.",
            {
                "source": "cognitive_os",
                "domain": "general_conversation",
                "roles": ["speech_output_transformer"],
                "skills": [],
                "route_path": ["cognitive_os"],
                "confidence": 0.9,
                "local_llm_synthesis_used": True,
                "local_llm_model": "qwen2.5:1.5b",
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *args, **kwargs: {
            "selected": False,
            "reason": "test_small_primary",
        },
    )

    def unavailable_candidate(*args, reviewer_tier="deep", **kwargs):
        attempted.append(reviewer_tier)
        return {
            "ok": False,
            "reason": "no_eligible_local_model",
            "reviewer_tier": reviewer_tier,
        }

    monkeypatch.setattr(
        server,
        "_generate_alternate_local_candidate",
        unavailable_candidate,
    )
    prompt = (
        "Analyze and recommend an architecture tradeoff from first principles "
        "across privacy, security, latency, cost, reliability, and scalability."
    )

    _, trace = server._run_nova_chat_turn(
        prompt,
        context=_managed_test_context(),
    )

    assert attempted == ["deep", "middle"]
    assert trace["model_escalation_policy"]["selected_tier"] == "deep"
