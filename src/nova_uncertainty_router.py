"""Provider-independent request difficulty and small-model review policy.

The router uses bounded surface signals only. It does not generate text, inspect
private chain-of-thought, call a provider, or execute a tool. Its public trace
contains capability labels and scores but never prompt or answer content.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


UNCERTAINTY_ROUTER_VERSION = "1.0"
DEFAULT_DIFFICULTY_THRESHOLD = 0.68

_WORD_RE = re.compile(r"[a-z0-9]+")
_SIMPLE_EXACT = {
    "hi", "hello", "hey", "thanks", "thank you", "tell me a joke", "another one",
    "what is your name", "what is my name", "how are you", "what u doing today",
}
_ADVANCED_REASONING = (
    "analyze", "evaluate", "derive", "prove", "deduce", "root cause", "threat model",
    "reason through", "formal proof", "optimize", "tradeoff analysis",
)
_COMPARISON = ("compare", "versus", " vs ", "tradeoff", "trade-off")
_DECISION = ("recommend", "decide", "choose", "which should", "best approach", "staged")
_DEPTH = (
    "step by step", "go deep", "deeply", "in depth", "thorough", "all the ways",
    "from first principles", "multiple perspectives",
)
_TECHNICAL_COMPLEXITY = (
    "architecture", "migration", "concurrency", "race condition", "deadlock", "stack trace",
    "distributed", "refactor", "security model", "database schema", "performance bottleneck",
    "theorem", "algorithmic complexity", "optimization problem",
)
_CODING = (
    "code", "coding", "debug", "python", "javascript", "typescript", "function", "class ",
    "api", "sql", "stack trace", "repository", "test failure",
)
_DIMENSIONS = (
    "privacy", "offline", "latency", "cost", "security", "risk", "migration", "performance",
    "reliability", "maintainability", "scalability", "compatibility", "memory", "battery",
)
_VOLATILE_ONLY = (
    "current president", "current mayor", "latest news", "weather today", "stock price",
    "live score", "current ceo",
)


def _canonical(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _has_marker(value: str, marker: str) -> bool:
    """Match a word or phrase without finding short markers inside other words."""

    normalized = str(marker or "").strip()
    if not normalized:
        return False
    return bool(
        re.search(
            r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])",
            value,
        )
    )


def _task_type(value: str, trace: Mapping[str, Any]) -> str:
    domain = str(trace.get("domain") or "").lower()
    if "coding" in domain or any(_has_marker(value, marker) for marker in _CODING):
        return "coding"
    if any(marker in domain for marker in ("math", "reason", "science")) or any(
        _has_marker(value, marker) for marker in _ADVANCED_REASONING + _TECHNICAL_COMPLEXITY
    ):
        return "reasoning"
    return "general"


@dataclass(frozen=True)
class DifficultyAssessment:
    """Safe request-level capability assessment."""

    score: float
    tier: str
    task_type: str
    signals: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    larger_local_recommended: bool
    threshold: float = DEFAULT_DIFFICULTY_THRESHOLD
    version: str = UNCERTAINTY_ROUTER_VERSION

    def as_trace(self) -> dict[str, Any]:
        """Return content-free routing metadata."""

        return {
            "version": self.version,
            "difficulty_score": round(self.score, 3),
            "difficulty_tier": self.tier,
            "task_type": self.task_type,
            "signals": list(self.signals),
            "required_capabilities": list(self.required_capabilities),
            "larger_local_recommended": self.larger_local_recommended,
            "threshold": round(self.threshold, 3),
            "content_logged": False,
            "private_reasoning_used": False,
        }


@dataclass(frozen=True)
class EscalationDecision:
    """Explain whether Nova should ask another local model for a candidate."""

    should_escalate: bool
    selected_tier: str
    fallback_tiers: tuple[str, ...]
    reasons: tuple[str, ...]
    version: str = UNCERTAINTY_ROUTER_VERSION

    def as_trace(self) -> dict[str, object]:
        return {
            "version": self.version,
            "should_escalate": self.should_escalate,
            "selected_tier": self.selected_tier,
            "fallback_tiers": list(self.fallback_tiers),
            "reasons": list(self.reasons),
            "content_logged": False,
            "private_reasoning_used": False,
        }


def decide_model_escalation(
    *,
    intent_family: str,
    difficulty_score: float,
    firewall_score: float,
    firewall_reasons: Iterable[str],
    small_answer_available: bool,
) -> EscalationDecision:
    """Choose deterministic, small, middle, or deep using observable quality."""

    family = str(intent_family or "").strip().lower()
    difficulty = max(0.0, min(float(difficulty_score), 1.0))
    quality = max(0.0, min(float(firewall_score), 1.0))
    reasons = tuple(
        dict.fromkeys(
            str(item).strip()
            for item in firewall_reasons
            if str(item).strip()
        )
    )
    if family in {
        "emotional",
        "greeting",
        "nova_self_state",
        "relationship",
        "social",
        "social_checkin",
    }:
        return EscalationDecision(
            False,
            "deterministic",
            (),
            ("reviewed_intent",),
        )
    weak_small_answer = bool(
        not small_answer_available
        or quality < 0.75
        or reasons
    )
    if difficulty >= DEFAULT_DIFFICULTY_THRESHOLD:
        return EscalationDecision(
            True,
            "deep",
            ("deep", "middle"),
            ("high_difficulty",)
            + (("small_answer_quality",) if weak_small_answer else ()),
        )
    if weak_small_answer:
        return EscalationDecision(
            True,
            "middle",
            ("middle", "deep"),
            ("small_answer_quality",),
        )
    return EscalationDecision(
        False,
        "small",
        (),
        ("small_answer_accepted",),
    )


def assess_request_difficulty(
    text: str,
    trace: Mapping[str, Any] | None = None,
    *,
    threshold: float = DEFAULT_DIFFICULTY_THRESHOLD,
) -> DifficultyAssessment:
    """Classify whether a request merits an independent larger-local review."""

    value = _canonical(text)
    trace = trace if isinstance(trace, Mapping) else {}
    threshold = max(0.50, min(float(threshold), 0.95))
    words = _WORD_RE.findall(value)
    score = 0.08
    signals: list[str] = []
    capabilities: list[str] = ["text"]

    if value in _SIMPLE_EXACT or re.fullmatch(
        r"what is \d+\s*(?:\+|-|\*|/|plus|minus|times)\s*\d+\??",
        value,
    ):
        return DifficultyAssessment(0.05, "routine", "general", ("simple_direct",), ("text",), False, threshold)

    advanced_count = sum(1 for marker in _ADVANCED_REASONING if _has_marker(value, marker))
    if advanced_count:
        score += min(0.38, 0.24 + (0.07 * (advanced_count - 1)))
        signals.append("advanced_reasoning")
        capabilities.append("reasoning")

    comparison = any(_has_marker(value, marker) for marker in _COMPARISON)
    decision = any(_has_marker(value, marker) for marker in _DECISION)
    if comparison and decision:
        score += 0.23
        signals.append("comparison_with_decision")
        capabilities.extend(("comparison", "decision_support"))
    elif comparison:
        score += 0.08
        signals.append("comparison")

    dimensions = sum(1 for marker in _DIMENSIONS if _has_marker(value, marker))
    if dimensions >= 3:
        score += min(0.24, 0.15 + (0.02 * (dimensions - 3)))
        signals.append("multi_constraint")
        capabilities.append("constraint_tracking")

    technical_count = sum(1 for marker in _TECHNICAL_COMPLEXITY if _has_marker(value, marker))
    if technical_count:
        score += min(0.28, 0.18 + (0.04 * (technical_count - 1)))
        signals.append("technical_complexity")
        capabilities.append("technical_reasoning")

    if any(_has_marker(value, marker) for marker in _DEPTH):
        score += 0.17
        signals.append("explicit_depth")
        capabilities.append("deep_explanation")

    if len(words) >= 45:
        score += 0.12
        signals.append("long_request")
        capabilities.append("long_context")
    if len(words) >= 100:
        score += 0.08
        signals.append("very_long_request")

    # Changing facts need fresh evidence, not automatically a larger language
    # model. Freshness policy remains authoritative elsewhere in Nova.
    if any(_has_marker(value, marker) for marker in _VOLATILE_ONLY) and not signals:
        score = min(score, 0.20)
        signals.append("freshness_not_model_size")

    task_type = _task_type(value, trace)
    if task_type == "coding" and "coding" not in capabilities:
        capabilities.append("coding")
    score = min(score, 1.0)
    tier = "hard" if score >= threshold else "moderate" if score >= 0.38 else "routine"
    return DifficultyAssessment(
        score=score,
        tier=tier,
        task_type=task_type,
        signals=tuple(dict.fromkeys(signals or ["ordinary_request"])),
        required_capabilities=tuple(dict.fromkeys(capabilities)),
        larger_local_recommended=score >= threshold,
        threshold=threshold,
    )


def primary_answer_needs_larger_review(
    assessment: DifficultyAssessment,
    answer: str,
) -> bool:
    """Decide if a hard request should receive one independent local review."""

    if not assessment.larger_local_recommended:
        return False
    words = _WORD_RE.findall(str(answer or ""))
    if assessment.score >= 0.84:
        return True
    if len(words) < 70:
        return True
    value = _canonical(answer)
    if "comparison" in assessment.required_capabilities and not any(
        marker in value for marker in ("however", "whereas", "tradeoff", "on the other hand", "both")
    ):
        return True
    if "reasoning" in assessment.required_capabilities and not any(
        marker in value for marker in ("because", "therefore", "depends", "reason", "evidence", "tradeoff")
    ):
        return True
    return False
