"""Provider-neutral candidate ranking for Nova-managed responses.

This module is pure policy: it ranks model capabilities and completed answer
candidates. It does not call providers, mutate memory, or execute tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Mapping

from nova_answer_firewall import FirewallDecision


CANDIDATE_SELECTOR_VERSION = "2.5"

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "do", "does",
    "for", "from", "how", "i", "in", "is", "it", "me", "more", "my", "of",
    "on", "or", "that", "the", "this", "to", "u", "what", "when", "where",
    "who", "why", "with", "you", "your",
}


def _normalized_model_id(model_id: str) -> str:
    value = str(model_id or "").strip().lower()
    return value[:-7] if value.endswith(":latest") else value


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def select_alternate_model(
    capabilities: Iterable[Any],
    *,
    primary_model: str = "",
    minimum_model_bytes: int | None = None,
    maximum_model_bytes: int | None = None,
    preferred_model_ids: Iterable[str] = (),
    prefer_larger: bool = False,
    excluded_model_ids: Iterable[str] = (),
    require_preferred: bool = False,
) -> tuple[Any | None, dict[str, Any]]:
    """Choose a healthy, free, local text model using capability metadata."""

    primary = _normalized_model_id(primary_model)
    preferred = {
        _normalized_model_id(model_id): index
        for index, model_id in enumerate(preferred_model_ids)
        if _normalized_model_id(model_id)
    }
    excluded = {
        _normalized_model_id(model_id)
        for model_id in excluded_model_ids
        if _normalized_model_id(model_id)
    }
    eligible: list[tuple[tuple[Any, ...], Any]] = []
    rejected: list[dict[str, str]] = []
    for capability in capabilities:
        model_id = str(getattr(capability, "model_id", "") or "")
        provider_id = str(getattr(capability, "provider_id", "") or "")
        reason = ""
        if not model_id or not provider_id:
            reason = "missing_identity"
        elif _normalized_model_id(model_id) in excluded:
            reason = "excluded_from_tier"
        elif require_preferred and _normalized_model_id(model_id) not in preferred:
            reason = "not_enabled_for_tier"
        elif getattr(capability, "availability", "available") != "available":
            reason = "unavailable"
        elif str(getattr(capability, "health_status", "unknown")) not in {"healthy", "unknown"}:
            reason = "unhealthy"
        elif str(getattr(capability, "local_or_remote", "local")) != "local":
            reason = "remote"
        elif str(getattr(capability, "estimated_cost_type", "free")) != "free":
            reason = "paid"
        elif not bool(getattr(capability, "text_input", True)) or not bool(getattr(capability, "text_output", True)):
            reason = "no_text_support"

        metadata = getattr(capability, "metadata", {}) or {}
        try:
            size = int(metadata.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if not reason and maximum_model_bytes and size and size > maximum_model_bytes:
            reason = "over_memory_policy"
        if not reason and minimum_model_bytes and size and size < minimum_model_bytes:
            reason = "below_escalation_size"

        if reason:
            rejected.append({"provider": provider_id, "model": model_id, "reason": reason})
            continue

        is_primary = bool(primary and _normalized_model_id(model_id) == primary)
        preferred_rank = preferred.get(_normalized_model_id(model_id), len(preferred))
        healthy_rank = 0 if getattr(capability, "health_status", "unknown") == "healthy" else 1
        reasoning_rank = 0 if bool(getattr(capability, "reasoning", False)) else 1
        if prefer_larger:
            size_rank = -size if size > 0 else 0
        else:
            size_rank = size if size > 0 else 2**63 - 1
        eligible.append(
            (
                (
                    1 if is_primary else 0,
                    preferred_rank,
                    healthy_rank,
                    reasoning_rank,
                    size_rank,
                    provider_id,
                    model_id,
                ),
                capability,
            )
        )

    eligible.sort(key=lambda item: item[0])
    selected = eligible[0][1] if eligible else None
    return selected, {
        "version": CANDIDATE_SELECTOR_VERSION,
        "eligible_count": len(eligible),
        "rejected_count": len(rejected),
        "selected_different_from_primary": bool(
            selected and primary and _normalized_model_id(getattr(selected, "model_id", "")) != primary
        ),
        "preferred_model_count": len(preferred),
        "prefer_larger": bool(prefer_larger),
        "excluded_model_count": len(excluded),
        "require_preferred": bool(require_preferred),
        "rejections": rejected[:12],
    }


@dataclass(frozen=True)
class AnswerCandidate:
    """One completed answer considered by Nova's response tournament."""

    candidate_id: str
    answer: str
    source: str
    provider: str
    model: str
    firewall: FirewallDecision
    relevance_text: str = ""
    trace_confidence: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: AnswerCandidate
    score: float
    signals: tuple[str, ...]

    def safe_summary(self) -> dict[str, Any]:
        """Return privacy-safe metadata without prompt or answer content."""

        summary = {
            "candidate_id": self.candidate.candidate_id,
            "source": self.candidate.source,
            "provider": self.candidate.provider,
            "model": self.candidate.model,
            "accepted": self.candidate.firewall.accepted,
            "firewall_score": round(self.candidate.firewall.score, 3),
            "quality_score": round(self.score, 3),
            "reasons": list(self.candidate.firewall.reasons),
            "signals": list(self.signals),
            "answer_length": len(str(self.candidate.answer or "")),
        }
        coverage = self.candidate.metadata.get("requested_aspect_coverage")
        if isinstance(coverage, Mapping) and coverage.get("applied"):
            summary["requested_aspect_coverage"] = {
                "required_count": int(coverage.get("required_count") or 0),
                "covered_count": int(coverage.get("covered_count") or 0),
                "coverage_ratio": round(float(coverage.get("coverage_ratio") or 0.0), 3),
                "complete": bool(coverage.get("complete")),
            }
        return summary


def score_candidate(candidate: AnswerCandidate) -> ScoredCandidate:
    """Score an already firewalled answer using explainable surface signals."""

    if not candidate.firewall.accepted:
        return ScoredCandidate(candidate, 0.0, ("firewall_rejected",))

    answer = str(candidate.answer or "").strip()
    relevance_tokens = _content_tokens(candidate.relevance_text)
    answer_tokens = _content_tokens(answer)
    overlap = len(relevance_tokens.intersection(answer_tokens))
    overlap_ratio = overlap / max(1, min(len(relevance_tokens), 8))

    score = 0.68
    signals = ["firewall_passed"]
    if overlap:
        score += min(0.18, overlap_ratio * 0.18)
        signals.append("topic_overlap")
    elif len(relevance_tokens) >= 2:
        score -= 0.24
        signals.append("missing_topic_overlap")
    if 24 <= len(answer) <= 1800:
        score += 0.07
        signals.append("useful_length")
    if answer and not answer.endswith("?"):
        score += 0.03
        signals.append("direct_statement")
    confidence = max(0.0, min(float(candidate.trace_confidence or 0.0), 1.0))
    score += confidence * 0.04
    if bool(candidate.metadata.get("different_model")):
        score += 0.02
        signals.append("independent_model")
    if bool(candidate.metadata.get("self_reported_uncertainty")):
        score -= 0.18
        signals.append("self_reported_uncertainty")
    if bool(candidate.metadata.get("unverified_exact_claim")):
        score -= 0.16
        signals.append("unverified_exact_claim")
    if bool(candidate.metadata.get("too_shallow")):
        score -= 0.16
        signals.append("too_shallow")
    if bool(candidate.metadata.get("question_restatement")):
        score -= 0.14
        signals.append("question_restatement")
    if bool(candidate.metadata.get("clarification_deflection")):
        score -= 0.24
        signals.append("clarification_deflection")
    coverage = candidate.metadata.get("requested_aspect_coverage")
    if isinstance(coverage, Mapping) and coverage.get("applied"):
        ratio = max(0.0, min(float(coverage.get("coverage_ratio") or 0.0), 1.0))
        if ratio < 1.0:
            score -= 0.38
            signals.append("incomplete_requested_aspects")
        else:
            signals.append("requested_aspects_covered")
    if bool(candidate.metadata.get("complexity_mismatch")):
        score -= 0.12
        signals.append("complexity_mismatch")
    return ScoredCandidate(candidate, min(score, 1.0), tuple(signals))


def choose_candidate(
    candidates: Iterable[AnswerCandidate],
    *,
    minimum_score: float = 0.68,
) -> tuple[ScoredCandidate | None, list[ScoredCandidate]]:
    """Choose the strongest accepted candidate, or return no winner."""

    scored = [score_candidate(candidate) for candidate in candidates]
    ranked = sorted(scored, key=lambda item: item.score, reverse=True)
    if not ranked or ranked[0].score < minimum_score:
        return None, ranked
    return ranked[0], ranked
