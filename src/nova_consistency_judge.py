"""High-precision, provider-independent technical consistency checks.

The judge validates a small registry of stable technical invariants. It never
calls a model, executes a tool, stores request content, or inspects private
chain-of-thought. Rules are deliberately conservative: uncertain cases pass.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


TECHNICAL_CONSISTENCY_VERSION = "1.2"

_LOCAL_STORAGE = r"(?:sqlite|local storage|local database|on-device(?: storage| database)?)"
_REMOTE_STORAGE = r"(?:remote|cloud)(?: vector)?(?: storage| database| service)?"
_STORAGE_TOPIC = re.compile(
    rf"\b{_LOCAL_STORAGE}\b[\s\S]{{0,300}}\b{_REMOTE_STORAGE}\b|"
    rf"\b{_REMOTE_STORAGE}\b[\s\S]{{0,300}}\b{_LOCAL_STORAGE}\b",
    flags=re.IGNORECASE,
)
_QUALIFIED_EXCEPTION = re.compile(
    r"\b(?:if|when|depending|cached|cache|edge|poorly indexed|slow device|"
    r"specialized hardware|benchmark|under specific|in some deployments)\b",
    flags=re.IGNORECASE,
)

_LOCAL_SLOWER_THAN_REMOTE = re.compile(
    rf"\b{_LOCAL_STORAGE}\b[\s\S]{{0,260}}?\b(?:has|have|may have|can have|"
    rf"offers?|experiences?)\s+(?:a\s+)?(?:higher|greater|more)\s+"
    rf"(?:access\s+|network\s+)?latency\s+(?:than|compared\s+to)\s+"
    rf"(?:a\s+|an\s+)?{_REMOTE_STORAGE}\b",
    flags=re.IGNORECASE,
)
_REMOTE_FASTER_THAN_LOCAL = re.compile(
    rf"\b{_REMOTE_STORAGE}\b[\s\S]{{0,220}}?\b(?:has|have|offers?|provides?|is)\s+"
    rf"(?:(?:a\s+)?(?:lower|less)\s+(?:access\s+|network\s+)?latency|faster)\s+"
    rf"(?:than|compared\s+to)\s+(?:a\s+|an\s+)?{_LOCAL_STORAGE}\b",
    flags=re.IGNORECASE,
)
_LOCAL_REQUIRES_NETWORK = re.compile(
    rf"\b{_LOCAL_STORAGE}\b[\s\S]{{0,180}}?\b(?:requires?|needs?)\b"
    rf"[\s\S]{{0,35}}?\b(?:internet|network connection|connectivity)\b",
    flags=re.IGNORECASE,
)
_REMOTE_FULLY_OFFLINE = re.compile(
    rf"\b{_REMOTE_STORAGE}\b[\s\S]{{0,160}}?\b(?:works?|operates?|functions?|supports?)\s+"
    rf"(?:entirely|fully|seamlessly)?\s*offline\b",
    flags=re.IGNORECASE,
)

_STORAGE_GUIDANCE = (
    "Local on-device storage usually avoids network round trips, so it usually has lower access latency than comparable remote storage.",
    "Local storage works offline; remote storage needs connectivity unless paired with a local cache or synchronization layer.",
    "Remote storage helps centralized scaling and multi-device sync but adds network, privacy, availability, and operating-cost tradeoffs.",
)


def _canonical(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _storage_rule_applies(text: str) -> bool:
    value = _canonical(text)
    if not _STORAGE_TOPIC.search(value):
        return False
    return bool(
        re.search(
            r"\b(?:latency|offline|privacy|cost|migration|scalability|synchronization|architecture)\b",
            value,
            flags=re.IGNORECASE,
        )
    )


def technical_consistency_guidance(request_text: str) -> tuple[str, ...]:
    """Return stable public constraints relevant to a managed review prompt."""

    if _storage_rule_applies(request_text):
        return _STORAGE_GUIDANCE
    return ()


@dataclass(frozen=True)
class TechnicalConsistencyDecision:
    """Content-free result of validating stable technical invariants."""

    applied: bool
    accepted: bool
    score: float
    issues: tuple[str, ...]
    checked_invariants: tuple[str, ...]
    version: str = TECHNICAL_CONSISTENCY_VERSION

    def as_trace(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "applied": self.applied,
            "accepted": self.accepted,
            "status": "passed" if self.accepted else "blocked",
            "score": round(self.score, 3),
            "issues": list(self.issues),
            "checked_invariants": list(self.checked_invariants),
            "content_logged": False,
            "private_reasoning_used": False,
        }


def bypass_trace() -> dict[str, Any]:
    """Prove that explicit raw adapter output was not consistency-checked."""

    return {
        "version": TECHNICAL_CONSISTENCY_VERSION,
        "applied": False,
        "accepted": True,
        "status": "bypassed_raw",
        "score": None,
        "issues": [],
        "checked_invariants": [],
        "content_logged": False,
        "private_reasoning_used": False,
    }


def _unqualified_match(pattern: re.Pattern[str], answer: str) -> bool:
    for match in pattern.finditer(answer):
        window = answer[max(0, match.start() - 70) : min(len(answer), match.end() + 100)]
        if not _QUALIFIED_EXCEPTION.search(window):
            return True
    return False


def _claim_segments(answer: str) -> tuple[str, ...]:
    """Keep one subject claim from borrowing another label's predicate."""

    segments: list[str] = []
    for line in re.split(r"[\r\n]+", str(answer or "")):
        sentences = [
            segment.strip()
            for segment in re.split(r"(?<=[.!?;])\s+", line)
            if segment.strip()
        ]
        previous = ""
        for sentence in sentences:
            if previous and re.match(
                r"^(?:(?:however|but|also|instead|therefore|so)[,\s]+)?"
                r"(?:it|this|that|they)\b",
                sentence,
                flags=re.IGNORECASE,
            ):
                segments.append(previous + " " + sentence)
            else:
                segments.append(sentence)
            previous = sentence
    return tuple(segments)


def evaluate_technical_consistency(
    request_text: str,
    answer: str,
    *,
    enabled: bool = True,
) -> TechnicalConsistencyDecision:
    """Reject only high-confidence contradictions of registered invariants."""

    if not enabled:
        return TechnicalConsistencyDecision(False, True, 1.0, (), ())
    if not _storage_rule_applies(str(request_text or "") + " " + str(answer or "")):
        return TechnicalConsistencyDecision(False, True, 1.0, (), ())

    issues: list[str] = []
    segments = _claim_segments(answer)
    checks = (
        "local_remote_storage_latency",
        "local_remote_storage_connectivity",
    )
    if any(
        _unqualified_match(_LOCAL_SLOWER_THAN_REMOTE, segment)
        or _unqualified_match(_REMOTE_FASTER_THAN_LOCAL, segment)
        for segment in segments
    ):
        issues.append("local_remote_latency_reversed")
    if any(_unqualified_match(_LOCAL_REQUIRES_NETWORK, segment) for segment in segments):
        issues.append("local_storage_network_dependency_reversed")
    remote_offline_without_cache = any(
        bool(
            _REMOTE_FULLY_OFFLINE.search(segment)
            and re.search(
                r"\boffline\b[\s\S]{0,45}\bwithout\b[\s\S]{0,30}\b(?:local\s+)?cache\b",
                segment,
                flags=re.IGNORECASE,
            )
        )
        for segment in segments
    )
    if remote_offline_without_cache or any(
        _unqualified_match(_REMOTE_FULLY_OFFLINE, segment)
        for segment in segments
    ):
        issues.append("remote_storage_offline_dependency_reversed")

    accepted = not issues
    return TechnicalConsistencyDecision(
        applied=True,
        accepted=accepted,
        score=1.0 if accepted else 0.2,
        issues=tuple(dict.fromkeys(issues)),
        checked_invariants=checks,
    )
