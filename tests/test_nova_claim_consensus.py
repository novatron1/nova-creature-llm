from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nova_claim_consensus import analyze_source_consensus, publisher_identity  # noqa: E402


def _source(
    url: str,
    snippet: str,
    *,
    score: float = 0.8,
    checked_at: str | None = None,
):
    if checked_at is None:
        checked_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return {
        "url": url,
        "title": url,
        "snippet": snippet,
        "status": 200,
        "checked_at": checked_at,
        "reliability_score": score,
    }


def test_publisher_identity_collapses_subdomains_and_handles_public_suffixes():
    assert publisher_identity("https://science.nasa.gov/earth/facts/") == "nasa.gov"
    assert publisher_identity("www1.grc.nasa.gov") == "nasa.gov"
    assert publisher_identity("https://news.bbc.co.uk/story") == "bbc.co.uk"


def test_numeric_claim_is_corroborated_by_independent_publishers():
    report = analyze_source_consensus(
        "search the web for Earth diameter",
        [
            _source(
                "https://science.nasa.gov/earth/facts/",
                "Earth has an equatorial diameter of 7,926 miles (12,756 kilometers).",
                score=0.95,
            ),
            _source(
                "https://example.edu/earth-study",
                "The measured diameter of Earth is approximately 12,753 kilometers.",
                score=0.9,
            ),
            _source(
                "https://reference.org/earth",
                "Earth's equatorial diameter is 12,756 kilometers.",
                score=0.8,
            ),
        ],
    )

    kilometer_claims = [
        claim for claim in report.corroborated_claims if claim.predicate == "diameter" and claim.unit == "kilometers"
    ]
    assert report.status == "corroborated"
    assert report.publisher_count == 3
    assert len(kilometer_claims) == 1
    assert len(kilometer_claims[0].supporting_publishers) == 3
    assert "12,756 kilometers" in kilometer_claims[0].statement
    assert report.conclusion_lines()


def test_radius_measurement_can_corroborate_a_requested_diameter():
    report = analyze_source_consensus(
        "search the web for Earth diameter",
        [
            _source(
                "https://science.nasa.gov/earth/facts/",
                "Earth has an equatorial diameter of 12,756 kilometers.",
                score=0.95,
            ),
            _source(
                "https://space.example.org/earth-size",
                "Earth's radius at the equator is 6,378 kilometers.",
                score=0.85,
            ),
        ],
    )

    kilometer_claims = [
        claim for claim in report.corroborated_claims if claim.predicate == "diameter" and claim.unit == "kilometers"
    ]
    assert report.status == "corroborated"
    assert len(kilometer_claims) == 1
    assert len(kilometer_claims[0].supporting_publishers) == 2
    assert "12,756 kilometers" in kilometer_claims[0].statement
    methods = {
        item["method"]
        for item in kilometer_claims[0].safe_summary()["supporting_publishers"]
    }
    assert methods == {"numeric_direct", "numeric_derived"}


def test_semantic_paraphrases_are_corroborated_across_publishers():
    report = analyze_source_consensus(
        "search the web for the largest animal blue whale",
        [
            _source(
                "https://ocean.example.org/blue-whale",
                "The blue whale is the largest animal known to have ever lived.",
                score=0.92,
            ),
            _source(
                "https://wildlife.example.edu/whales",
                "Blue whales are the biggest animals on Earth.",
                score=0.86,
            ),
            _source(
                "https://reference.example.com/blue-whale",
                "The blue whale is the most massive animal alive today.",
                score=0.82,
            ),
        ],
    )

    semantic = [
        claim for claim in report.corroborated_claims if claim.claim_type == "semantic"
    ]
    assert report.status == "corroborated"
    assert len(semantic) == 1
    assert len(semantic[0].supporting_publishers) == 3
    assert "blue whale" in semantic[0].statement.lower()
    assert report.safe_trace()["semantic_corroborated_count"] == 1
    assert {
        item["method"]
        for item in semantic[0].safe_summary()["supporting_publishers"]
    } == {"semantic_match"}


def test_semantic_match_finds_a_claim_inside_a_noisy_unpunctuated_extract():
    noisy_extract = (
        "Switch to legacy parser From Wikipedia the free encyclopedia "
        "Species of whale largest animal known Blue whale disambiguation "
        "Balaenoptera musculus Size compared to an average human Scientific "
        "classification Conservation references navigation menu"
    )
    report = analyze_source_consensus(
        "search the web for the largest animal blue whale",
        [
            _source(
                "https://fisheries.example.gov/blue-whale",
                "The blue whale is the largest animal on Earth.",
                score=0.95,
            ),
            _source(
                "https://reference.example.org/blue-whale",
                noisy_extract,
                score=0.8,
            ),
        ],
    )

    semantic = [
        claim for claim in report.corroborated_claims if claim.claim_type == "semantic"
    ]
    assert report.status == "corroborated"
    assert len(semantic) == 1
    assert semantic[0].statement == "The blue whale is the largest animal on Earth."


def test_semantic_match_rejects_a_different_relationship():
    report = analyze_source_consensus(
        "search the web for the largest animal blue whale",
        [
            _source(
                "https://ocean.example.org/blue-whale",
                "The blue whale is the largest animal known to have ever lived.",
            ),
            _source(
                "https://wildlife.example.edu/whales",
                "The blue whale is the deepest diving animal in this study.",
            ),
        ],
    )

    assert report.status == "insufficient"
    assert not [
        claim for claim in report.corroborated_claims if claim.claim_type == "semantic"
    ]


def test_semantic_match_requires_the_queried_entity_not_only_a_pronoun():
    report = analyze_source_consensus(
        "search the web for the largest animal blue whale",
        [
            _source(
                "https://one.example.org/record",
                "It is the largest animal known to have ever existed.",
            ),
            _source(
                "https://two.example.edu/record",
                "It remains the biggest animal ever documented.",
            ),
        ],
    )

    assert report.status == "insufficient"
    assert report.safe_trace()["semantic_corroborated_count"] == 0


def test_semantic_negation_is_reported_as_a_conflict():
    report = analyze_source_consensus(
        "is the blue whale the largest animal on Earth",
        [
            _source(
                "https://ocean.example.org/blue-whale",
                "The blue whale is the largest animal on Earth.",
            ),
            _source(
                "https://wildlife.example.edu/whales",
                "The blue whale is not the largest animal on Earth.",
            ),
        ],
    )

    assert report.status == "mixed"
    assert any(
        claim.claim_type == "semantic"
        for claim in report.conflicting_claims
    )
    assert report.conclusion_lines() == []
    semantic_conflict = next(
        claim
        for claim in report.conflicting_claims
        if claim.claim_type == "semantic"
    )
    assert semantic_conflict.safe_summary()["supporting_publishers"]
    assert semantic_conflict.safe_summary()["conflicting_publishers"]


def test_two_subdomains_of_one_publisher_do_not_create_consensus():
    report = analyze_source_consensus(
        "Earth diameter",
        [
            _source("https://science.nasa.gov/earth", "Earth's diameter is 12,756 kilometers."),
            _source("https://www1.grc.nasa.gov/earth", "Earth's diameter is 12,756 kilometers."),
        ],
    )

    assert report.publisher_count == 1
    assert report.status == "insufficient"
    assert report.corroborated_claims == ()


def test_configurable_minimum_publishers_can_require_three_sources():
    sources = [
        _source("https://one.example.org/earth", "Earth's diameter is 12,756 kilometers."),
        _source("https://two.example.edu/earth", "Earth's diameter is 12,756 kilometers."),
    ]

    default_report = analyze_source_consensus("Earth diameter", sources)
    strict_report = analyze_source_consensus("Earth diameter", sources, minimum_publishers=3)

    assert default_report.status == "corroborated"
    assert strict_report.status == "insufficient"


def test_materially_different_numeric_values_are_reported_as_conflict():
    report = analyze_source_consensus(
        "Earth diameter",
        [
            _source("https://science.nasa.gov/earth", "Earth's diameter is 12,756 kilometers."),
            _source("https://example.edu/earth", "Earth's diameter is 14,000 kilometers."),
        ],
    )

    assert report.status == "mixed"
    assert len(report.conflicting_claims) == 1
    assert report.conclusion_lines() == []
    assert "No verified conclusion" in report.conflict_lines()[0]


def test_named_current_fact_requires_independent_matching_publishers():
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    report = analyze_source_consensus(
        "look up who is the current mayor of Cincinnati",
        [
            _source(
                "https://cincinnati-oh.gov/mayor",
                "The current mayor of Cincinnati is Aftab Pureval.",
                score=0.95,
                checked_at="2026-07-17T11:00:00Z",
            ),
            _source(
                "https://localnews.example.com/city-hall",
                "Aftab Pureval is the current mayor.",
                score=0.8,
                checked_at="2026-07-17T11:30:00Z",
            ),
        ],
        now=now,
    )

    named = [claim for claim in report.corroborated_claims if claim.claim_type == "named_entity"]
    assert report.status == "corroborated"
    assert len(named) == 1
    assert named[0].statement == "mayor is Aftab Pureval."


def test_current_named_fact_uses_volatile_freshness_and_expires_soon():
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    report = analyze_source_consensus(
        "look up who is the current mayor of Cincinnati",
        [
            _source(
                "https://cincinnati-oh.gov/mayor",
                "The current mayor of Cincinnati is Aftab Pureval.",
                checked_at="2026-07-17T10:30:00Z",
            ),
            _source(
                "https://localnews.example.com/city-hall",
                "Aftab Pureval is the current mayor.",
                checked_at="2026-07-17T11:00:00Z",
            ),
        ],
        now=now,
    )

    claim = next(
        item for item in report.corroborated_claims if item.claim_type == "named_entity"
    )
    assert claim.freshness_class == "volatile"
    assert claim.freshness_status == "fresh"
    assert claim.freshness_ttl_seconds == 21_600
    assert claim.verified_at == "2026-07-17T11:00:00Z"
    assert claim.expires_at == "2026-07-17T16:30:00Z"
    assert report.safe_trace()["next_expiration_at"] == "2026-07-17T16:30:00Z"


def test_expired_current_fact_agreement_is_not_a_verified_conclusion():
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    report = analyze_source_consensus(
        "look up who is the current mayor of Cincinnati",
        [
            _source(
                "https://cincinnati-oh.gov/mayor",
                "The current mayor of Cincinnati is Aftab Pureval.",
                checked_at="2026-07-17T03:00:00Z",
            ),
            _source(
                "https://localnews.example.com/city-hall",
                "Aftab Pureval is the current mayor.",
                checked_at="2026-07-17T04:00:00Z",
            ),
        ],
        now=now,
    )

    assert report.status == "stale"
    assert report.corroborated_claims == ()
    assert len(report.stale_claims) == 1
    assert report.stale_claims[0].freshness_status == "stale"
    assert report.conclusion_lines() == []
    assert "requires a fresh lookup" in report.stale_lines()[0]


def test_stable_claim_remains_fresh_longer_than_a_current_fact():
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    report = analyze_source_consensus(
        "search the web for the largest animal blue whale",
        [
            _source(
                "https://ocean.example.org/blue-whale",
                "The blue whale is the largest animal known to have ever lived.",
                checked_at="2026-07-10T12:00:00Z",
            ),
            _source(
                "https://wildlife.example.edu/whales",
                "Blue whales are the biggest animals on Earth.",
                checked_at="2026-07-11T12:00:00Z",
            ),
        ],
        now=now,
    )

    claim = next(item for item in report.corroborated_claims if item.claim_type == "semantic")
    assert claim.freshness_class == "stable"
    assert claim.freshness_status == "fresh"
    assert claim.freshness_ttl_seconds == 2_592_000


def test_opposite_polarity_claims_are_detected_as_conflicting():
    report = analyze_source_consensus(
        "is Earth flat",
        [
            _source("https://one.example.org/earth", "Earth is flat."),
            _source("https://two.example.edu/earth", "Earth is not flat."),
        ],
    )

    assert report.status == "mixed"
    assert any(claim.claim_type == "polarity" for claim in report.conflicting_claims)


def test_safe_trace_omits_queries_snippets_names_and_values():
    secret_public_query = "PUBLIC-QUERY-MUST-NOT-ENTER-TRACE"
    report = analyze_source_consensus(
        "Earth diameter " + secret_public_query,
        [
            _source("https://one.example.org/earth", "Earth's diameter is 12,756 kilometers."),
            _source("https://two.example.edu/earth", "Earth's diameter is 12,756 kilometers."),
        ],
    )
    trace_text = json.dumps(report.safe_trace())

    assert secret_public_query not in trace_text
    assert "12,756" not in trace_text
    assert "Earth's diameter" not in trace_text
    assert report.safe_trace()["content_logged"] is False


def test_semantic_safe_trace_omits_the_source_wording():
    secret_sentence = "The blue whale is the largest animal known to have ever lived."
    report = analyze_source_consensus(
        "largest animal blue whale",
        [
            _source("https://one.example.org/whale", secret_sentence),
            _source(
                "https://two.example.edu/whale",
                "Blue whales are the biggest animals on Earth.",
            ),
        ],
    )
    trace_text = json.dumps(report.safe_trace())

    assert secret_sentence not in trace_text
    assert "blue whale" not in trace_text.lower()
    assert report.safe_trace()["semantic_corroborated_count"] == 1
