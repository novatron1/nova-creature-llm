from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_fact_grounding import (  # noqa: E402
    LocalEvidenceStore,
    bypass_trace,
    evaluate_grounding,
    grounding_recovery_response,
)


NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def test_local_evidence_store_searches_portable_records_and_hides_content(tmp_path):
    path = tmp_path / "evidence.json"
    secret_evidence_text = "Earth reference diameter is 12,742 kilometers."
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "records": [
                    {
                        "evidence_id": "earth-diameter",
                        "topic": "Earth size and diameter",
                        "content": secret_evidence_text,
                        "source_name": "Trusted Earth reference",
                        "source_type": "local_reference",
                        "verified_at": "2026-01-01T00:00:00+00:00",
                        "trust_level": 0.95,
                        "tags": ["earth", "measurement"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    store = LocalEvidenceStore(path)

    decision = evaluate_grounding(
        "How big is Earth?",
        "Earth's diameter is about 12,742 kilometers.",
        evidence_store=store,
        now=NOW,
    )
    trace = decision.as_trace(now=NOW)

    assert decision.status == "grounded"
    assert decision.blocking is False
    assert store.health_check()["records"] == 1
    assert trace["evidence"][0]["evidence_id"] == "earth-diameter"
    assert secret_evidence_text not in json.dumps(trace)


def test_creative_and_opinion_answers_do_not_require_factual_grounding():
    decision = evaluate_grounding(
        "Imagine a library floating inside a snowflake",
        "Its glass shelves glow under a blue winter sky.",
        now=NOW,
    )

    assert decision.required is False
    assert decision.status == "not_required"
    assert decision.blocking is False


def test_present_moment_social_checkin_does_not_trigger_current_fact_guard():
    decision = evaluate_grounding(
        "What u doing today?",
        "Just chilling, hanging out with you!",
        trace={"source": "reviewed_training"},
        now=NOW,
    )

    assert decision.required is False
    assert decision.status == "not_required"
    assert decision.freshness_required is False
    assert decision.blocking is False


def test_slang_feeling_today_checkin_does_not_trigger_current_fact_guard():
    decision = evaluate_grounding(
        "HOW U FEELING TODAY",
        "I'm here, running steady.",
        trace={"source": "nova_self_state"},
        now=NOW,
    )

    assert decision.required is False
    assert decision.status == "not_required"
    assert decision.freshness_required is False
    assert decision.blocking is False


def test_social_day_checkin_with_today_does_not_trigger_current_fact_guard():
    decision = evaluate_grounding(
        "How's your day going today?",
        "My day is going steady.",
        trace={"source": "nova_self_state"},
        now=NOW,
    )

    assert decision.required is False
    assert decision.status == "not_required"
    assert decision.freshness_required is False
    assert decision.blocking is False


def test_relationship_miss_question_does_not_require_factual_evidence():
    decision = evaluate_grounding(
        "DID YOU MISS ME?",
        "In my own way, yes. I value our conversations.",
        trace={"source": "nova_relationship_boundary"},
        now=NOW,
    )

    assert decision.required is False
    assert decision.status == "not_required"
    assert decision.freshness_required is False
    assert decision.blocking is False


def test_static_price_word_problem_does_not_trigger_live_price_guard():
    decision = evaluate_grounding(
        "Six notebooks cost $42 at the same price each. What do nine notebooks cost?",
        "",
        now=NOW,
    )

    assert decision.freshness_required is False
    assert decision.blocking is False


def test_method_for_checking_current_fact_does_not_require_the_fact_itself():
    decision = evaluate_grounding(
        "Two articles conflict about a current technical fact. "
        "Describe how to answer accurately without pretending certainty.",
        "",
        now=NOW,
    )

    assert decision.freshness_required is False
    assert decision.blocking is False


def test_fresh_official_current_fact_is_grounded():
    answer = "As of July 4, 2026, the President is Example Person."
    decision = evaluate_grounding(
        "Who is the current president?",
        answer,
        trace={
            "source": "current_officeholder_guard",
            "verified_date": "2026-07-04",
            "verified_source": "Official administration record",
        },
        now=NOW,
    )

    assert decision.status == "grounded"
    assert decision.freshness_required is True
    assert decision.blocking is False


def test_unknown_current_fact_without_evidence_is_blocked_honestly():
    decision = evaluate_grounding(
        "Who is the current mayor of Example City?",
        "The current mayor is Jane Example.",
        trace={"source": "cognitive_os"},
        now=NOW,
    )

    assert decision.status == "unverified"
    assert decision.blocking is True
    assert "freshness_required" in decision.reasons
    assert "stopped an unverified current-fact answer" in grounding_recovery_response("", decision)


def test_live_news_route_is_grounded_by_fresh_items():
    decision = evaluate_grounding(
        "What is the latest space news?",
        "Top current headline: Example mission launches successfully.",
        trace={
            "source": "live_news_router",
            "online_checked": True,
            "live_news": [
                {
                    "title": "Example mission launches successfully",
                    "source": "Example News",
                    "published": "Thu, 16 Jul 2026 10:00:00 GMT",
                    "checked_at": "2026-07-16T11:00:00+00:00",
                }
            ],
        },
        now=NOW,
    )

    assert decision.status == "grounded"
    assert decision.blocking is False


def test_stable_numeric_claim_without_evidence_is_labeled_but_not_blocked():
    decision = evaluate_grounding(
        "How big is the test sphere?",
        "Its diameter is 500 kilometers.",
        trace={"source": "cognitive_os"},
        now=NOW,
    )

    assert decision.status == "unverified"
    assert decision.required is True
    assert decision.blocking is False


def test_stale_current_record_does_not_count_as_fresh():
    decision = evaluate_grounding(
        "Who is the current president?",
        "The current president is Example Person.",
        trace={
            "source": "current_officeholder_guard",
            "verified_date": "2025-01-01",
            "verified_source": "Old official record",
        },
        now=NOW,
        maximum_age_days=30,
    )

    assert decision.status == "unverified"
    assert decision.blocking is True
    assert decision.as_trace(now=NOW)["evidence"][0]["fresh"] is False


def test_raw_bypass_trace_is_explicit_and_content_free():
    assert bypass_trace() == {
        "schema_version": "1.0",
        "required": False,
        "status": "bypassed_raw",
        "blocking": False,
        "freshness_required": False,
        "claim_count": 0,
        "supported_claim_count": 0,
        "evidence_count": 0,
        "reasons": [],
        "content_logged": False,
    }
