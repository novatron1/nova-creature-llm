from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_consistency_judge import (  # noqa: E402
    TECHNICAL_CONSISTENCY_VERSION,
    evaluate_technical_consistency,
    technical_consistency_guidance,
)


REQUEST = (
    "Compare local SQLite vector memory with a remote vector database for a private "
    "mobile AI app. Analyze privacy, offline behavior, latency, migration risk, and cost."
)


def test_rejects_reversed_local_remote_latency_claim():
    decision = evaluate_technical_consistency(
        REQUEST,
        (
            "Using local SQLite keeps data on the device. It supports offline access but "
            "may have higher latency compared to remote databases."
        ),
    )

    assert decision.version == TECHNICAL_CONSISTENCY_VERSION
    assert decision.accepted is False
    assert "local_remote_latency_reversed" in decision.issues


def test_rejects_reversed_latency_after_discourse_marker_and_pronoun():
    decision = evaluate_technical_consistency(
        REQUEST,
        (
            "Local SQLite keeps data on device and works offline. However, it has "
            "higher latency compared to a remote vector database."
        ),
    )

    assert decision.accepted is False
    assert "local_remote_latency_reversed" in decision.issues


def test_accepts_correct_storage_tradeoff_and_qualified_exception():
    correct = evaluate_technical_consistency(
        REQUEST,
        "Local SQLite normally avoids network latency; remote storage adds synchronization and scaling.",
    )
    qualified = evaluate_technical_consistency(
        REQUEST,
        (
            "A remote edge cache can be faster than a poorly indexed local database when "
            "the device is slow, so benchmark the actual hardware."
        ),
    )

    assert correct.accepted is True
    assert qualified.accepted is True


def test_accepts_compact_labeled_local_and_remote_claims_without_cross_label_leakage():
    answer = (
        "Privacy: Local storage maintains control; remote storage shares responsibility.\n"
        "Offline behavior: Local works offline; remote requires connectivity or caching.\n"
        "Latency: Local is usually lower; remote adds network delay.\n"
        "Recommendation: Keep core data local and synchronize with consent."
    )

    decision = evaluate_technical_consistency(REQUEST, answer)

    assert decision.accepted is True
    assert decision.issues == ()


def test_rejects_reversed_connectivity_claims():
    local = evaluate_technical_consistency(
        REQUEST,
        "Local SQLite requires an active internet connection for every read.",
    )
    remote = evaluate_technical_consistency(
        REQUEST,
        "A remote cloud vector database works entirely offline without any local cache.",
    )

    assert "local_storage_network_dependency_reversed" in local.issues
    assert "remote_storage_offline_dependency_reversed" in remote.issues


def test_irrelevant_answer_is_not_forced_through_storage_rules():
    decision = evaluate_technical_consistency(
        "Tell me a joke.",
        "Why did the byte cross the bus? To get to the other side.",
    )

    assert decision.applied is False
    assert decision.accepted is True


def test_guidance_and_trace_are_public_and_content_free():
    guidance = technical_consistency_guidance(REQUEST)
    trace = evaluate_technical_consistency(
        REQUEST,
        "Local SQLite normally avoids a network round trip.",
    ).as_trace()

    assert guidance
    assert any("network round trips" in item for item in guidance)
    assert REQUEST not in str(trace)
    assert trace["content_logged"] is False
    assert trace["private_reasoning_used"] is False
