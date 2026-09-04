"""Local-first evidence and freshness checks for Nova-managed answers.

This module never calls a model, network service, tool, or memory writer.  It
evaluates evidence already supplied by Nova routes plus an optional portable
local evidence store.  Raw adapter output is intentionally handled outside
this module and remains untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any, Iterable, Mapping


GROUNDING_SCHEMA_VERSION = "1.0"

_WORD_RE = re.compile(r"[a-z0-9]+")
_NUMBER_RE = re.compile(r"(?<![a-z])\d[\d,]*(?:\.\d+)?")
_MONTH_RE = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.IGNORECASE,
)
_FRESHNESS_CUES = (
    "current", "latest", "today", "right now", "this week", "this month",
    "breaking", "live news", "live weather", "live score", "news", "weather", "forecast", "price", "stock",
    "president", "prime minister", "mayor", "ceo", "schedule", "score",
    "law", "regulation", "rules", "officeholder",
)
_FACT_QUESTION_PREFIXES = (
    "who ", "what ", "when ", "where ", "which ", "how many ", "how much ",
    "how big ", "how far ", "how fast ", "how old ", "how tall ", "how heavy ",
    "is ", "are ", "did ", "does ", "explain ", "tell me about ",
)
_CREATIVE_OR_OPINION_CUES = (
    "imagine", "write a story", "make up", "poem", "fiction", "roleplay",
    "what do you think", "your opinion", "how do you feel", "do you love",
)
_CONVERSATIONAL_PRESENT_CHECKINS = {
    "how are you",
    "how are you doing",
    "how are you doing now",
    "how are you doing right now",
    "how are you doing today",
    "how are you feeling",
    "how are you feeling now",
    "how are you feeling today",
    "how are u",
    "how are u doing",
    "how are u doing now",
    "how are u doing right now",
    "how are u doing today",
    "how are u feeling",
    "how are u feeling now",
    "how are u feeling today",
    "how r u",
    "how u doing",
    "how u doing now",
    "how u doing right now",
    "how u doing today",
    "what are you doing",
    "what are you doing now",
    "what are you doing right now",
    "what are you doing today",
    "what are you up to",
    "what are you up to now",
    "what are you up to today",
    "what are u doing",
    "what are u doing now",
    "what are u doing right now",
    "what are u doing today",
    "what are u up to",
    "what are u up to now",
    "what are u up to today",
    "what r you doing",
    "what r you doing now",
    "what r you doing right now",
    "what r you doing today",
    "what r u doing",
    "what r u doing now",
    "what r u doing right now",
    "what r u doing today",
    "what you doing",
    "what you doing now",
    "what you doing right now",
    "what you doing today",
    "what you up to",
    "what you up to now",
    "what you up to today",
    "what u doing",
    "what u doing now",
    "what u doing right now",
    "what u doing today",
    "what u up to",
    "what u up to now",
    "what u up to today",
}
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "is", "it", "of", "on", "or", "that", "the", "their",
    "this", "to", "was", "were", "will", "with", "you", "your",
}


def _canonical(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _tokens(value: Any) -> set[str]:
    return {token for token in _WORD_RE.findall(_canonical(value)) if token not in _STOP_WORDS and len(token) > 1}


def _numbers(value: Any) -> set[str]:
    return {item.replace(",", "") for item in _NUMBER_RE.findall(str(value or ""))}


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _conversational_present_checkin(prompt: str) -> bool:
    """Recognize exact social check-ins without weakening real current-fact checks."""

    value = re.sub(r"[^a-z0-9\s]", " ", _canonical(prompt))
    value = re.sub(r"\s+", " ", value).strip()
    if value in _CONVERSATIONAL_PRESENT_CHECKINS:
        return True
    social_patterns = (
        r"how\s+(?:(?:are|r|do)\s+)?(?:you|u)\s+feel(?:ing)?"
        r"(?:\s+(?:today|now|right\s+now))?",
        r"how\s+(?:is|s|has|was)\s+(?:your|ur)\s+day"
        r"(?:\s+(?:going|been))?(?:\s+today)?",
        r"(?:did|do|have|would)\s+(?:you|u)\s+(?:really\s+)?"
        r"miss(?:ed)?\s+(?:me|us)",
    )
    return any(re.fullmatch(pattern, value) for pattern in social_patterns)


@dataclass(frozen=True)
class EvidenceRecord:
    """One portable local evidence record."""

    evidence_id: str
    topic: str
    content: str
    source_name: str
    source_type: str = "local_reference"
    source_url: str = ""
    verified_at: str = ""
    expires_at: str = ""
    trust_level: float = 0.8
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = GROUNDING_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceRecord":
        evidence_id = str(value.get("evidence_id") or "").strip()
        content = str(value.get("content") or "").strip()
        if not evidence_id or not content:
            raise ValueError("Evidence records require evidence_id and content.")
        try:
            trust_level = max(0.0, min(float(value.get("trust_level", 0.8)), 1.0))
        except (TypeError, ValueError):
            trust_level = 0.8
        return cls(
            evidence_id=evidence_id,
            topic=str(value.get("topic") or "").strip(),
            content=content,
            source_name=str(value.get("source_name") or "Local evidence").strip(),
            source_type=str(value.get("source_type") or "local_reference").strip(),
            source_url=str(value.get("source_url") or "").strip(),
            verified_at=str(value.get("verified_at") or "").strip(),
            expires_at=str(value.get("expires_at") or "").strip(),
            trust_level=trust_level,
            tags=tuple(str(item).strip() for item in (value.get("tags") or []) if str(item).strip()),
            metadata=dict(value.get("metadata") or {}),
            schema_version=str(value.get("schema_version") or GROUNDING_SCHEMA_VERSION),
        )

    def is_expired(self, *, now: datetime | None = None) -> bool:
        expires = _parse_time(self.expires_at)
        return bool(expires and expires < _utc_now(now))

    def safe_summary(self) -> dict[str, Any]:
        """Return operational metadata without evidence content."""

        return {
            "evidence_id": self.evidence_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "verified_at": self.verified_at or None,
            "expires_at": self.expires_at or None,
            "trust_level": round(self.trust_level, 3),
            "schema_version": self.schema_version,
        }


class LocalEvidenceStore:
    """Read-only, reloadable JSON evidence store with no secret handling."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = RLock()
        self._records: tuple[EvidenceRecord, ...] = ()
        self._mtime_ns: int | None = None
        self._error = ""

    def _reload_if_needed(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._records = ()
                self._mtime_ns = None
                self._error = ""
                return
            stat = self.path.stat()
            if stat.st_size > 5 * 1024 * 1024:
                self._records = ()
                self._error = "evidence_store_too_large"
                return
            if self._mtime_ns == stat.st_mtime_ns:
                return
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                values = payload.get("records", []) if isinstance(payload, dict) else payload
                if not isinstance(values, list):
                    raise ValueError("Evidence store records must be a list.")
                self._records = tuple(EvidenceRecord.from_mapping(item) for item in values if isinstance(item, dict))
                self._mtime_ns = stat.st_mtime_ns
                self._error = ""
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._records = ()
                self._mtime_ns = stat.st_mtime_ns
                self._error = type(exc).__name__

    def list_records(self, *, include_expired: bool = False, now: datetime | None = None) -> list[EvidenceRecord]:
        self._reload_if_needed()
        return [record for record in self._records if include_expired or not record.is_expired(now=now)]

    def search(self, query: str, *, limit: int = 5, now: datetime | None = None) -> list[EvidenceRecord]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        scored: list[tuple[float, EvidenceRecord]] = []
        for record in self.list_records(now=now):
            record_tokens = _tokens(" ".join((record.topic, record.content, " ".join(record.tags))))
            overlap = len(query_tokens & record_tokens)
            if not overlap:
                continue
            score = overlap / max(1, len(query_tokens)) + (record.trust_level * 0.2)
            scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], item[1].evidence_id))
        return [record for _, record in scored[: max(1, min(int(limit), 20))]]

    def health_check(self) -> dict[str, Any]:
        self._reload_if_needed()
        return {
            "ok": not self._error,
            "path_configured": bool(str(self.path)),
            "exists": self.path.exists(),
            "records": len(self._records),
            "error": self._error or None,
            "schema_version": GROUNDING_SCHEMA_VERSION,
        }


@dataclass(frozen=True)
class ClaimSignal:
    claim_id: str
    text: str
    claim_types: tuple[str, ...]
    numbers: tuple[str, ...] = ()

    def safe_summary(self, supported: bool) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "types": list(self.claim_types),
            "supported": supported,
            "character_count": len(self.text),
        }


@dataclass(frozen=True)
class _EvidenceItem:
    evidence_id: str
    text: str
    source_name: str
    source_type: str
    verified_at: str = ""
    live: bool = False
    trust_level: float = 0.8

    def fresh(self, *, now: datetime, maximum_age_days: int) -> bool:
        checked = _parse_time(self.verified_at)
        if self.live and checked is None:
            return True
        if checked is None:
            return False
        return 0 <= (now - checked).total_seconds() <= maximum_age_days * 86400

    def safe_summary(self, *, fresh: bool) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "verified_at": self.verified_at or None,
            "live": self.live,
            "fresh": fresh,
            "trust_level": round(self.trust_level, 3),
        }


@dataclass(frozen=True)
class FactGroundingDecision:
    required: bool
    status: str
    blocking: bool
    freshness_required: bool
    claims: tuple[ClaimSignal, ...] = ()
    supported_claim_ids: tuple[str, ...] = ()
    evidence: tuple[_EvidenceItem, ...] = ()
    reasons: tuple[str, ...] = ()
    maximum_age_days: int = 30

    def as_trace(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = _utc_now(now)
        supported = set(self.supported_claim_ids)
        return {
            "schema_version": GROUNDING_SCHEMA_VERSION,
            "required": self.required,
            "status": self.status,
            "blocking": self.blocking,
            "freshness_required": self.freshness_required,
            "claim_count": len(self.claims),
            "supported_claim_count": len(supported),
            "claims": [claim.safe_summary(claim.claim_id in supported) for claim in self.claims],
            "evidence_count": len(self.evidence),
            "evidence": [
                item.safe_summary(fresh=item.fresh(now=current, maximum_age_days=self.maximum_age_days))
                for item in self.evidence
            ],
            "reasons": list(self.reasons),
            "content_logged": False,
        }


def bypass_trace() -> dict[str, Any]:
    return {
        "schema_version": GROUNDING_SCHEMA_VERSION,
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


def _freshness_required(prompt: str) -> bool:
    value = _canonical(prompt)
    if _conversational_present_checkin(prompt):
        return False
    if re.search(
        r"\b(?:describe|explain|outline)\s+how\s+to\s+"
        r"(?:answer|check|verify|research|evaluate|resolve|handle|compare|assess)\b",
        value,
    ):
        return False
    if (
        "price" in value
        and bool(_numbers(value))
        and re.search(r"\b(?:same price each|unit price|costs?\s+\$?\d+)\b", value)
        and not any(
            cue in value
            for cue in ("current", "latest", "today", "right now", "this week", "this month")
        )
    ):
        value = re.sub(r"\bprice\b", "", value)
    return any(cue in value for cue in _FRESHNESS_CUES)


def _conversation_decision_field(
    trace: Mapping[str, Any],
    field_name: str,
    default: Any = None,
) -> Any:
    value = trace.get("conversation_decision")
    if isinstance(value, Mapping):
        return value.get(field_name, default)
    return getattr(value, field_name, default)


def _factual_request(prompt: str, trace: Mapping[str, Any]) -> bool:
    decision_family = str(
        _conversation_decision_field(trace, "intent_family", "") or ""
    )
    if decision_family in {"relationship", "emotional", "social", "follow_up"}:
        return False
    decision_requires_evidence = _conversation_decision_field(
        trace,
        "factual_evidence_required",
        None,
    )
    if decision_requires_evidence is not None:
        return bool(decision_requires_evidence)
    value = _canonical(prompt)
    if _conversational_present_checkin(prompt):
        return False
    if any(cue in value for cue in _CREATIVE_OR_OPINION_CUES):
        return False
    if _freshness_required(prompt) or value.startswith(_FACT_QUESTION_PREFIXES):
        return True
    return str(trace.get("domain") or "").lower() in {
        "current_facts", "knowledge_explanation", "math", "news", "research", "science",
    }


def _claim_signals(prompt: str, answer: str, trace: Mapping[str, Any]) -> tuple[ClaimSignal, ...]:
    if not _factual_request(prompt, trace):
        return ()
    name_question = _canonical(prompt).startswith(("who ", "where ", "which "))
    signals: list[ClaimSignal] = []
    consensus_conclusions = [
        str(item).strip()
        for item in (trace.get("consensus_conclusions") or [])
        if str(item).strip()
    ]
    claim_text = "\n".join(consensus_conclusions) if consensus_conclusions else str(answer or "")
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n+", claim_text) if item.strip()]
    for index, sentence in enumerate(sentences[:12], start=1):
        types: list[str] = []
        numbers = tuple(sorted(_numbers(sentence)))
        if numbers:
            types.append("numeric")
        if _MONTH_RE.search(sentence) or any(len(item) == 4 and item.startswith(("19", "20")) for item in numbers):
            types.append("date")
        if _freshness_required(prompt):
            types.append("current")
        if name_question and re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][A-Za-z.]+)+", sentence):
            types.append("named_entity")
        if not types:
            types.append("factual")
        signals.append(
            ClaimSignal(
                claim_id=f"claim_{index}",
                text=sentence,
                claim_types=tuple(dict.fromkeys(types)),
                numbers=numbers,
            )
        )
    return tuple(signals)


def _trace_evidence(trace: Mapping[str, Any], answer: str, now: datetime) -> list[_EvidenceItem]:
    evidence: list[_EvidenceItem] = []
    for index, item in enumerate(trace.get("grounding_evidence") or []):
        if not isinstance(item, Mapping) or not str(item.get("content") or "").strip():
            continue
        try:
            trust_level = max(0.0, min(float(item.get("trust_level", 0.8)), 1.0))
        except (TypeError, ValueError):
            trust_level = 0.8
        evidence.append(
            _EvidenceItem(
                evidence_id=str(item.get("evidence_id") or f"route_{index + 1}"),
                text=str(item.get("content") or ""),
                source_name=str(item.get("source_name") or "Nova route evidence"),
                source_type=str(item.get("source_type") or "route_evidence"),
                verified_at=str(item.get("verified_at") or ""),
                live=bool(item.get("live")),
                trust_level=trust_level,
            )
        )

    for index, item in enumerate(trace.get("live_news") or []):
        if not isinstance(item, Mapping):
            continue
        text = " ".join(str(item.get(key) or "") for key in ("title", "source", "published"))
        if text.strip():
            evidence.append(
                _EvidenceItem(
                    evidence_id=f"live_news_{index + 1}",
                    text=text,
                    source_name=str(item.get("source") or "Live news"),
                    source_type="live_news",
                    verified_at=str(item.get("checked_at") or ""),
                    live=True,
                    trust_level=0.82,
                )
            )

    for index, item in enumerate(trace.get("live_sources") or []):
        if not isinstance(item, Mapping):
            continue
        status = item.get("status")
        if not (isinstance(status, int) and 200 <= status < 400):
            continue
        text = " ".join(str(item.get(key) or "") for key in ("title", "name", "snippet"))
        if text.strip():
            evidence.append(
                _EvidenceItem(
                    evidence_id=f"live_source_{index + 1}",
                    text=text,
                    source_name=str(item.get("title") or item.get("name") or "Live source"),
                    source_type="live_web",
                    verified_at=str(item.get("checked_at") or ""),
                    live=True,
                    trust_level=0.85,
                )
            )

    source = str(trace.get("source") or "").lower()
    verified_at = str(trace.get("verified_date") or "")
    if source == "current_officeholder_guard" and verified_at:
        evidence.append(
            _EvidenceItem(
                evidence_id="official_current_fact",
                text=answer,
                source_name=str(trace.get("verified_source") or "Official verified record"),
                source_type="official_verified_record",
                verified_at=verified_at,
                trust_level=0.98,
            )
        )
    if source == "current_context_guard":
        evidence.append(
            _EvidenceItem(
                evidence_id="local_clock",
                text=answer,
                source_name="Nova local system clock",
                source_type="local_clock",
                verified_at=now.isoformat(),
                trust_level=0.99,
            )
        )
    if source == "sensor_awareness":
        evidence.append(
            _EvidenceItem(
                evidence_id="local_sensor_snapshot",
                text=answer,
                source_name="Nova live local sensor snapshot",
                source_type="local_sensor",
                verified_at=now.isoformat(),
                trust_level=0.96,
            )
        )
    if "math" in source or str(trace.get("domain") or "").lower() == "math":
        evidence.append(
            _EvidenceItem(
                evidence_id="local_calculation",
                text=answer,
                source_name="Nova deterministic math route",
                source_type="local_calculation",
                verified_at=now.isoformat(),
                trust_level=0.99,
            )
        )
    if source in {"dictionary_system", "long_term_memory", "people_memory"}:
        evidence.append(
            _EvidenceItem(
                evidence_id="local_memory_record",
                text=answer,
                source_name="Nova approved local memory",
                source_type="local_memory",
                verified_at=now.isoformat(),
                trust_level=0.72,
            )
        )
    return evidence


def _claim_supported(
    claim: ClaimSignal,
    item: _EvidenceItem,
    *,
    freshness_required: bool,
    now: datetime,
    maximum_age_days: int,
) -> bool:
    if item.trust_level < 0.6:
        return False
    if freshness_required and not item.fresh(now=now, maximum_age_days=maximum_age_days):
        return False
    if claim.numbers and not set(claim.numbers).issubset(_numbers(item.text)):
        return False
    claim_tokens = _tokens(claim.text)
    evidence_tokens = _tokens(item.text)
    if not claim_tokens:
        return False
    overlap = len(claim_tokens & evidence_tokens) / max(1, min(len(claim_tokens), 10))
    return overlap >= 0.45


def evaluate_grounding(
    prompt: str,
    answer: str,
    *,
    trace: Mapping[str, Any] | None = None,
    evidence_store: LocalEvidenceStore | None = None,
    now: datetime | None = None,
    maximum_age_days: int = 30,
    enabled: bool = True,
    block_unverified_current: bool = True,
) -> FactGroundingDecision:
    """Evaluate factual claims using route evidence and portable local records."""

    maximum_age_days = max(1, min(int(maximum_age_days), 3650))
    if not enabled:
        return FactGroundingDecision(False, "disabled", False, False, maximum_age_days=maximum_age_days)
    trace = trace or {}
    current = _utc_now(now)
    decision_requires_current = _conversation_decision_field(
        trace,
        "current_information_required",
        None,
    )
    freshness = (
        bool(decision_requires_current)
        if decision_requires_current is not None
        else _freshness_required(prompt)
    )
    claims = _claim_signals(prompt, answer, trace)
    required = bool(claims or freshness)
    if not required:
        return FactGroundingDecision(False, "not_required", False, False, maximum_age_days=maximum_age_days)

    evidence = _trace_evidence(trace, answer, current)
    if evidence_store is not None:
        for record in evidence_store.search(prompt, limit=5, now=current):
            evidence.append(
                _EvidenceItem(
                    evidence_id=record.evidence_id,
                    text=record.content,
                    source_name=record.source_name,
                    source_type=record.source_type,
                    verified_at=record.verified_at,
                    live=False,
                    trust_level=record.trust_level,
                )
            )

    supported: list[str] = []
    for claim in claims:
        if any(
            _claim_supported(
                claim,
                item,
                freshness_required=freshness,
                now=current,
                maximum_age_days=maximum_age_days,
            )
            for item in evidence
        ):
            supported.append(claim.claim_id)

    source = str(trace.get("source") or "").lower()
    route_directly_formats_evidence = (
        (source == "live_news_router" and bool(trace.get("online_checked")))
        or source in {"current_context_guard", "current_officeholder_guard", "sensor_awareness"}
        or "math" in source
    )
    if route_directly_formats_evidence and evidence:
        fresh_enough = not freshness or any(
            item.fresh(now=current, maximum_age_days=maximum_age_days) for item in evidence
        )
        if fresh_enough:
            supported = [claim.claim_id for claim in claims]

    if claims and len(supported) == len(claims):
        if evidence and all(item.source_type == "local_memory" for item in evidence):
            status = "locally_grounded"
        else:
            status = "grounded"
        reasons: tuple[str, ...] = ()
    elif supported:
        status = "partial"
        reasons = ("some_claims_lack_evidence",)
    else:
        status = "unverified"
        reasons = ("no_supporting_evidence",) if not evidence else ("evidence_did_not_support_claims",)

    blocking = bool(block_unverified_current and freshness and status not in {"grounded", "locally_grounded"})
    if blocking:
        reasons = tuple(dict.fromkeys(reasons + ("freshness_required",)))
    return FactGroundingDecision(
        required=required,
        status=status,
        blocking=blocking,
        freshness_required=freshness,
        claims=claims,
        supported_claim_ids=tuple(supported),
        evidence=tuple(evidence),
        reasons=reasons,
        maximum_age_days=maximum_age_days,
    )


def grounding_recovery_response(prompt: str, decision: FactGroundingDecision) -> str:
    """Return an honest answer when a changing fact lacks fresh evidence."""

    if decision.freshness_required:
        return (
            "I stopped an unverified current-fact answer instead of guessing. "
            "I do not have fresh supporting evidence for it in this reply. "
            "Ask me to look it up online and I’ll use Nova’s source-checking route, or give me a trusted local evidence record."
        )
    return (
        "I could not ground that factual answer in available evidence, so I left the uncertain claim out. "
        "Give me a source or ask me to research it."
    )
