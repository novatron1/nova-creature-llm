"""Deterministic, privacy-safe claim consensus for Nova web evidence.

This module compares bounded public evidence extracts without calling a model
or network service. It groups sources by publisher, detects comparable numeric,
named-entity, and simple polarity claims, and emits a verified conclusion only
when at least two independent publishers agree and no publisher contradicts it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from statistics import median
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


CONSENSUS_SCHEMA_VERSION = "1.0"
DEFAULT_VOLATILE_TTL_SECONDS = 21_600
DEFAULT_CHANGING_TTL_SECONDS = 604_800
DEFAULT_STABLE_TTL_SECONDS = 2_592_000

_COMMON_SECOND_LEVEL_SUFFIXES = {
    "ac.uk",
    "co.jp",
    "co.nz",
    "co.uk",
    "com.au",
    "com.br",
    "com.mx",
    "edu.au",
    "gov.au",
    "gov.uk",
    "net.au",
    "org.au",
    "org.uk",
}
_PREDICATES = (
    "diameter",
    "radius",
    "circumference",
    "population",
    "height",
    "length",
    "width",
    "distance",
    "speed",
    "temperature",
    "mass",
    "weight",
    "area",
    "age",
    "price",
    "cost",
    "percentage",
    "percent",
    "vote",
    "votes",
    "mayor",
    "president",
    "prime minister",
    "governor",
    "ceo",
    "capital",
    "winner",
)
_NAMED_PREDICATES = (
    "mayor",
    "president",
    "prime minister",
    "governor",
    "ceo",
    "capital",
    "winner",
)
_UNIT_PATTERN = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>kilomet(?:er|re)s?|km|miles?|mi|meters?|metres?|m|feet|foot|ft|"
    r"pounds?|lbs?|kilograms?|kg|degrees?\s+celsius|degrees?\s+fahrenheit|°c|°f|"
    r"percent|percentage|%|mph|km/?h|square\s+kilomet(?:er|re)s?|km²|sq\.?\s*km)\b",
    re.IGNORECASE,
)
_NAME_PATTERN = r"[A-Z][A-Za-z.'’-]+(?:\s+[A-Z][A-Za-z.'’-]+){0,4}"
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "for",
    "from", "has", "have", "in", "into", "is", "it", "of", "on", "or", "that",
    "the", "their", "this", "to", "was", "were", "will", "with",
}
_NEGATIONS = {"no", "not", "never", "neither", "without"}
_QUERY_SCAFFOLD = {
    "according",
    "answer",
    "check",
    "explain",
    "find",
    "how",
    "internet",
    "look",
    "lookup",
    "online",
    "search",
    "source",
    "tell",
    "verify",
    "web",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}
_SEMANTIC_SYNONYMS = {
    "allows": "allow",
    "allowed": "allow",
    "biggest": "large",
    "blocked": "prevent",
    "blocks": "prevent",
    "caused": "cause",
    "causes": "cause",
    "composed": "consist",
    "comprises": "contain",
    "consists": "consist",
    "contained": "contain",
    "contains": "contain",
    "converted": "create",
    "converts": "create",
    "created": "create",
    "creates": "create",
    "decreased": "decrease",
    "decreases": "decrease",
    "deepest": "deep",
    "depended": "require",
    "depends": "require",
    "enabled": "allow",
    "enables": "allow",
    "fastest": "fast",
    "generated": "create",
    "generates": "create",
    "greatest": "large",
    "grew": "increase",
    "grows": "increase",
    "highest": "high",
    "includes": "contain",
    "included": "contain",
    "increased": "increase",
    "increases": "increase",
    "largest": "large",
    "lowest": "low",
    "made": "create",
    "makes": "create",
    "massive": "large",
    "needed": "require",
    "needs": "require",
    "permitted": "allow",
    "permits": "allow",
    "prevents": "prevent",
    "produced": "create",
    "produces": "create",
    "reduced": "decrease",
    "reduces": "decrease",
    "required": "require",
    "requires": "require",
    "retained": "store",
    "retains": "store",
    "rose": "increase",
    "rises": "increase",
    "stored": "store",
    "stores": "store",
    "stopped": "prevent",
    "stops": "prevent",
    "sunlight": "light",
    "transformed": "create",
    "transforms": "create",
    "turned": "create",
    "turns": "create",
    "used": "require",
    "uses": "require",
}
_SEMANTIC_RELATIONS = {
    "allow",
    "cause",
    "consist",
    "contain",
    "create",
    "decrease",
    "deep",
    "fast",
    "high",
    "increase",
    "large",
    "low",
    "prevent",
    "require",
    "store",
}
_VOLATILE_QUERY_TERMS = {
    "breaking",
    "current",
    "currently",
    "latest",
    "live",
    "now",
    "price",
    "score",
    "status",
    "today",
    "tonight",
}
_VOLATILE_PREDICATES = {
    "ceo",
    "cost",
    "governor",
    "mayor",
    "president",
    "price",
    "prime minister",
    "vote",
    "votes",
    "winner",
}
_CHANGING_PREDICATES = {
    "population",
    "temperature",
}
_UNIT_CANONICAL = {
    "kilometer": "kilometers",
    "kilometre": "kilometers",
    "kilometers": "kilometers",
    "kilometres": "kilometers",
    "km": "kilometers",
    "mile": "miles",
    "miles": "miles",
    "mi": "miles",
    "meter": "meters",
    "metre": "meters",
    "meters": "meters",
    "metres": "meters",
    "m": "meters",
    "foot": "feet",
    "feet": "feet",
    "ft": "feet",
    "pound": "pounds",
    "pounds": "pounds",
    "lb": "pounds",
    "lbs": "pounds",
    "kilogram": "kilograms",
    "kilograms": "kilograms",
    "kg": "kilograms",
    "degree celsius": "degrees Celsius",
    "degrees celsius": "degrees Celsius",
    "°c": "degrees Celsius",
    "degree fahrenheit": "degrees Fahrenheit",
    "degrees fahrenheit": "degrees Fahrenheit",
    "°f": "degrees Fahrenheit",
    "percent": "percent",
    "percentage": "percent",
    "%": "percent",
    "mph": "mph",
    "km/h": "km/h",
    "kmh": "km/h",
    "square kilometer": "square kilometers",
    "square kilometre": "square kilometers",
    "square kilometers": "square kilometers",
    "square kilometres": "square kilometers",
    "km²": "square kilometers",
    "sq km": "square kilometers",
    "sq. km": "square kilometers",
}


def _canonical(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _canonical(value))
        if token not in _STOP_WORDS and token not in _NEGATIONS and len(token) > 1
    }


def _semantic_token(token: str) -> str:
    normalized = _SEMANTIC_SYNONYMS.get(token, token)
    if (
        len(normalized) > 4
        and normalized.endswith("s")
        and not normalized.endswith(("sis", "ss", "us"))
    ):
        normalized = normalized[:-1]
    return _SEMANTIC_SYNONYMS.get(normalized, normalized)


def _semantic_tokens(value: Any, *, query: bool = False) -> set[str]:
    tokens = {_semantic_token(token) for token in _tokens(value)}
    if query:
        tokens.difference_update(_QUERY_SCAFFOLD)
    return {token for token in tokens if token}


def _semantic_relations(tokens: Iterable[str]) -> set[str]:
    return set(tokens) & _SEMANTIC_RELATIONS


def publisher_identity(value: str) -> str:
    """Return an organization-level publisher key for a host or URL."""

    text = str(value or "").strip().lower()
    host = (urlparse(text).hostname if "://" in text else text).strip(".") if text else ""
    if not host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two in _COMMON_SECOND_LEVEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def _sentences(value: Any) -> list[str]:
    return [
        re.sub(r"\s+", " ", item).strip(" -\t\r\n")
        for item in re.split(r"(?<=[.!?])\s+|\n+", str(value or ""))
        if re.sub(r"\s+", " ", item).strip(" -\t\r\n")
    ][:20]


def _semantic_segments(value: Any) -> list[str]:
    """Return bounded sentences or relation-centered windows from noisy text."""

    segments: list[str] = []
    seen: set[str] = set()
    for sentence in _sentences(value):
        candidates = [sentence]
        if len(_semantic_tokens(sentence)) > 10:
            candidates = []
            words = re.findall(r"\S+", sentence)
            for index, word in enumerate(words):
                if not _semantic_relations(_semantic_tokens(word)):
                    continue
                start = max(0, index - 4)
                end = min(len(words), index + 7)
                candidates.append(" ".join(words[start:end]))
        for candidate in candidates:
            normalized = re.sub(r"\s+", " ", candidate).strip(" -\t\r\n")
            marker = _canonical(normalized)
            if not marker or marker in seen:
                continue
            seen.add(marker)
            segments.append(normalized)
            if len(segments) >= 20:
                return segments
    return segments


def _unit(value: str) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "").lower()).strip()
    return _UNIT_CANONICAL.get(normalized, normalized)


def _format_number(value: float) -> str:
    if math.isclose(value, round(value), rel_tol=0.0, abs_tol=1e-9):
        return f"{int(round(value)):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _predicate_for(sentence: str, query: str, position: int) -> str:
    lower = sentence.lower()
    candidates: list[tuple[int, str]] = []
    for predicate in _PREDICATES:
        for match in re.finditer(r"\b" + re.escape(predicate) + r"\b", lower):
            candidates.append((abs(match.start() - position), predicate))
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][1]
    query_lower = _canonical(query)
    query_predicates = [predicate for predicate in _PREDICATES if re.search(r"\b" + re.escape(predicate) + r"\b", query_lower)]
    return query_predicates[0] if len(query_predicates) == 1 else ""


@dataclass(frozen=True)
class _Observation:
    claim_type: str
    key: str
    predicate: str
    unit: str
    value_key: str
    numeric_value: float | None
    statement: str
    publisher_id: str
    source_name: str
    source_url: str
    reliability_score: float
    semantic_tokens: tuple[str, ...] = ()
    relation_tokens: tuple[str, ...] = ()
    evidence_method: str = "direct_extraction"
    checked_at: str = ""


@dataclass(frozen=True)
class ConsensusClaim:
    claim_id: str
    claim_type: str
    predicate: str
    unit: str
    status: str
    statement: str
    supporting_publishers: tuple[str, ...]
    conflicting_publishers: tuple[str, ...]
    reliability_score: float
    supporting_methods: tuple[tuple[str, str], ...] = ()
    conflicting_methods: tuple[tuple[str, str], ...] = ()
    freshness_class: str = "stable"
    freshness_status: str = "unknown"
    verified_at: str = ""
    expires_at: str = ""
    freshness_ttl_seconds: int = DEFAULT_STABLE_TTL_SECONDS

    def safe_summary(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "predicate": self.predicate,
            "unit": self.unit or None,
            "status": self.status,
            "supporting_publisher_count": len(self.supporting_publishers),
            "conflicting_publisher_count": len(self.conflicting_publishers),
            "supporting_publishers": [
                {"publisher_id": publisher, "method": method}
                for publisher, method in self.supporting_methods
            ],
            "conflicting_publishers": [
                {"publisher_id": publisher, "method": method}
                for publisher, method in self.conflicting_methods
            ],
            "freshness_class": self.freshness_class,
            "freshness_status": self.freshness_status,
            "verified_at": self.verified_at or None,
            "expires_at": self.expires_at or None,
            "freshness_ttl_seconds": self.freshness_ttl_seconds,
            "reliability_score": round(self.reliability_score, 3),
        }


@dataclass(frozen=True)
class SourceConsensusReport:
    status: str
    coverage: str
    publisher_count: int
    claims: tuple[ConsensusClaim, ...] = ()
    schema_version: str = CONSENSUS_SCHEMA_VERSION

    @property
    def corroborated_claims(self) -> tuple[ConsensusClaim, ...]:
        return tuple(claim for claim in self.claims if claim.status == "corroborated")

    @property
    def conflicting_claims(self) -> tuple[ConsensusClaim, ...]:
        return tuple(claim for claim in self.claims if claim.status == "conflict")

    @property
    def stale_claims(self) -> tuple[ConsensusClaim, ...]:
        return tuple(claim for claim in self.claims if claim.status == "stale")

    def safe_trace(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "coverage": self.coverage,
            "publisher_count": self.publisher_count,
            "claim_count": len(self.claims),
            "corroborated_claim_count": len(self.corroborated_claims),
            "semantic_claim_count": sum(1 for claim in self.claims if claim.claim_type == "semantic"),
            "semantic_corroborated_count": sum(
                1
                for claim in self.corroborated_claims
                if claim.claim_type == "semantic"
            ),
            "conflict_count": len(self.conflicting_claims),
            "stale_claim_count": len(self.stale_claims),
            "next_expiration_at": min(
                (
                    claim.expires_at
                    for claim in self.corroborated_claims
                    if claim.expires_at
                ),
                default=None,
            ),
            "claims": [claim.safe_summary() for claim in self.claims],
            "content_logged": False,
        }

    def conclusion_lines(self) -> list[str]:
        return [
            "  - Corroborated by "
            + str(len(claim.supporting_publishers))
            + " independent publishers: "
            + claim.statement
            for claim in self.corroborated_claims
        ]

    def conflict_lines(self) -> list[str]:
        return [
            "  - Sources disagree on "
            + (claim.predicate or "a comparable claim")
            + " across "
            + str(len(set(claim.supporting_publishers + claim.conflicting_publishers)))
            + " independent publishers. No verified conclusion was issued for that claim."
            for claim in self.conflicting_claims
        ]

    def stale_lines(self) -> list[str]:
        return [
            "  - Independent sources previously agreed on "
            + (claim.predicate or "a comparable claim")
            + ", but that evidence expired"
            + (" at " + claim.expires_at if claim.expires_at else "")
            + ". Nova issued no verified conclusion and requires a fresh lookup."
            for claim in self.stale_claims
        ]

    def grounding_evidence(self, checked_at: str = "") -> list[dict[str, Any]]:
        return [
            {
                "evidence_id": "consensus_" + claim.claim_id,
                "content": claim.statement,
                "source_name": (
                    "Independent publisher consensus ("
                    + str(len(claim.supporting_publishers))
                    + " publishers)"
                ),
                "source_type": "web_consensus",
                "verified_at": checked_at,
                "live": True,
                "trust_level": claim.reliability_score,
            }
            for claim in self.corroborated_claims
        ]


def _numeric_observations(query: str, source: Mapping[str, Any], publisher: str) -> list[_Observation]:
    observations: list[_Observation] = []
    snippet = str(source.get("snippet") or "")
    query_lower = _canonical(query)
    wants_diameter = bool(re.search(r"\bdiameter\b", query_lower))
    wants_radius = bool(re.search(r"\bradius\b", query_lower))
    for sentence in _sentences(snippet):
        for match in _UNIT_PATTERN.finditer(sentence):
            predicate = _predicate_for(sentence, query, match.start())
            if not predicate:
                continue
            try:
                value = float(match.group("value").replace(",", ""))
            except ValueError:
                continue
            unit = _unit(match.group("unit"))
            evidence_method = "numeric_direct"
            # Radius and diameter are directly convertible measurements. Normalize
            # to the one explicitly requested so equivalent source wording can
            # corroborate without treating two subdomains as independent evidence.
            if wants_diameter and not wants_radius and predicate == "radius":
                predicate = "diameter"
                value *= 2.0
                evidence_method = "numeric_derived"
            elif wants_radius and not wants_diameter and predicate == "diameter":
                predicate = "radius"
                value /= 2.0
                evidence_method = "numeric_derived"
            statement = predicate + " is about " + _format_number(value) + " " + unit + "."
            observations.append(
                _Observation(
                    claim_type="numeric",
                    key="numeric:" + predicate + ":" + unit,
                    predicate=predicate,
                    unit=unit,
                    value_key=_format_number(value),
                    numeric_value=value,
                    statement=statement,
                    publisher_id=publisher,
                    source_name=str(source.get("title") or source.get("name") or publisher),
                    source_url=str(source.get("url") or ""),
                    reliability_score=float(source.get("reliability_score") or 0.5),
                    evidence_method=evidence_method,
                    checked_at=str(source.get("checked_at") or ""),
                )
            )
    return observations


def _named_observations(query: str, source: Mapping[str, Any], publisher: str) -> list[_Observation]:
    observations: list[_Observation] = []
    query_lower = _canonical(query)
    predicates = [predicate for predicate in _NAMED_PREDICATES if re.search(r"\b" + re.escape(predicate) + r"\b", query_lower)]
    if not predicates:
        return observations
    for sentence in _sentences(source.get("snippet")):
        for predicate in predicates:
            patterns = (
                re.compile(
                    r"\b(?:the\s+)?(?:current\s+)?"
                    + re.escape(predicate)
                    + r"(?:\s+of\s+[^,.;:]{2,80})?\s+(?:is|was|will be)\s+(?P<name>"
                    + _NAME_PATTERN
                    + r")",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"\b(?P<name>"
                    + _NAME_PATTERN
                    + r")\s+(?:is|was|serves as)\s+(?:the\s+)?(?:current\s+)?"
                    + re.escape(predicate)
                    + r"\b",
                    re.IGNORECASE,
                ),
            )
            for pattern in patterns:
                match = pattern.search(sentence)
                if not match:
                    continue
                name = re.sub(r"\s+", " ", match.group("name")).strip(" ,.;:")
                if not name or not all(
                    token and token[0].isupper()
                    for token in name.split()
                ):
                    continue
                observations.append(
                    _Observation(
                        claim_type="named_entity",
                        key="named:" + predicate,
                        predicate=predicate,
                        unit="",
                        value_key=_canonical(name),
                        numeric_value=None,
                        statement=predicate + " is " + name + ".",
                        publisher_id=publisher,
                        source_name=str(source.get("title") or source.get("name") or publisher),
                        source_url=str(source.get("url") or ""),
                        reliability_score=float(source.get("reliability_score") or 0.5),
                        evidence_method="named_entity_match",
                        checked_at=str(source.get("checked_at") or ""),
                    )
                )
                break
    return observations


def _boolean_observations(query: str, source: Mapping[str, Any], publisher: str) -> list[_Observation]:
    observations: list[_Observation] = []
    query_tokens = _tokens(query)
    for sentence in _sentences(source.get("snippet")):
        lower = _canonical(sentence)
        if not re.search(r"\b(?:is|are|was|were)\b", lower):
            continue
        sentence_tokens = _tokens(sentence)
        relevant = sentence_tokens & query_tokens
        if len(relevant) < 2 or len(sentence_tokens) > 12:
            continue
        polarity = "negative" if any(re.search(r"\b" + word + r"\b", lower) for word in _NEGATIONS) else "positive"
        proposition_tokens = tuple(sorted(sentence_tokens))
        if len(proposition_tokens) < 2:
            continue
        proposition = re.sub(r"\b(?:no|not|never|neither)\b\s*", "", sentence, flags=re.IGNORECASE)
        proposition = re.sub(r"\s+", " ", proposition).strip(" .")
        statement = proposition + (" is not supported." if polarity == "negative" else " is supported.")
        observations.append(
            _Observation(
                claim_type="polarity",
                key="polarity:" + "|".join(proposition_tokens),
                predicate="proposition",
                unit="",
                value_key=polarity,
                numeric_value=None,
                statement=statement,
                publisher_id=publisher,
                source_name=str(source.get("title") or source.get("name") or publisher),
                source_url=str(source.get("url") or ""),
                reliability_score=float(source.get("reliability_score") or 0.5),
                evidence_method="polarity_match",
                checked_at=str(source.get("checked_at") or ""),
            )
        )
    return observations


def _semantic_observations(query: str, source: Mapping[str, Any], publisher: str) -> list[_Observation]:
    """Extract short, query-relevant factual statements for paraphrase matching."""

    observations: list[_Observation] = []
    query_tokens = _semantic_tokens(query, query=True)
    query_relations = _semantic_relations(query_tokens)
    query_entities = query_tokens - query_relations
    if len(query_tokens) < 2:
        return observations
    for sentence in _semantic_segments(source.get("snippet")):
        sentence_tokens = _semantic_tokens(sentence)
        if not 4 <= len(sentence_tokens) <= 32:
            continue
        relation_tokens = _semantic_relations(sentence_tokens)
        if not relation_tokens:
            continue
        if query_relations and not (relation_tokens & query_relations):
            continue
        overlap = sentence_tokens & query_tokens
        required_overlap = max(2, min(4, math.ceil(len(query_tokens) * 0.5)))
        if len(overlap) < required_overlap:
            continue
        if query_entities and len(sentence_tokens & query_entities) < min(2, len(query_entities)):
            continue
        lower = _canonical(sentence)
        polarity = (
            "negative"
            if any(re.search(r"\b" + re.escape(word) + r"\b", lower) for word in _NEGATIONS)
            else "positive"
        )
        statement = re.sub(r"\s+", " ", sentence).strip(" -\t\r\n")
        if len(statement) > 240:
            statement = statement[:237].rstrip() + "..."
        if statement and statement[0].islower():
            statement = statement[0].upper() + statement[1:]
        if statement and statement[-1] not in ".!?":
            statement += "."
        token_tuple = tuple(sorted(sentence_tokens))
        observations.append(
            _Observation(
                claim_type="semantic",
                key="semantic:" + "|".join(token_tuple),
                predicate=sorted(relation_tokens)[0],
                unit="",
                value_key=polarity,
                numeric_value=None,
                statement=statement,
                publisher_id=publisher,
                source_name=str(source.get("title") or source.get("name") or publisher),
                source_url=str(source.get("url") or ""),
                reliability_score=float(source.get("reliability_score") or 0.5),
                semantic_tokens=token_tuple,
                relation_tokens=tuple(sorted(relation_tokens)),
                evidence_method="semantic_match",
                checked_at=str(source.get("checked_at") or ""),
            )
        )
        if len(observations) >= 6:
            break
    return observations


def _semantic_similarity(left: _Observation, right: _Observation) -> float:
    left_tokens = set(left.semantic_tokens)
    right_tokens = set(right.semantic_tokens)
    left_relations = set(left.relation_tokens)
    right_relations = set(right.relation_tokens)
    if not left_tokens or not right_tokens or not (left_relations & right_relations):
        return 0.0
    shared = left_tokens & right_tokens
    if len(shared) < 3:
        return 0.0
    containment = len(shared) / max(1, min(len(left_tokens), len(right_tokens)))
    jaccard = len(shared) / max(1, len(left_tokens | right_tokens))
    return (0.65 * containment) + (0.35 * jaccard)


def _semantic_groups(
    observations: Iterable[_Observation],
    similarity_threshold: float,
) -> list[list[_Observation]]:
    """Cluster only high-similarity statements from independent publishers."""

    groups: list[list[_Observation]] = []
    ordered = sorted(
        observations,
        key=lambda item: (item.key, item.publisher_id, item.value_key),
    )
    for observation in ordered:
        best_group: list[_Observation] | None = None
        best_score = 0.0
        for group in groups:
            score = max(
                _semantic_similarity(observation, member)
                for member in group
            )
            if score >= similarity_threshold and score > best_score:
                best_group = group
                best_score = score
        if best_group is None:
            groups.append([observation])
        else:
            best_group.append(observation)
    return [
        group
        for group in groups
        if len({item.publisher_id for item in group}) >= 2
    ][:20]


def _numeric_bucket(observations: Iterable[_Observation]) -> list[list[_Observation]]:
    buckets: list[list[_Observation]] = []
    for observation in sorted(observations, key=lambda item: float(item.numeric_value or 0.0)):
        placed = False
        for bucket in buckets:
            center = median(float(item.numeric_value or 0.0) for item in bucket)
            tolerance = max(0.01, abs(center) * 0.005)
            if abs(float(observation.numeric_value or 0.0) - center) <= tolerance:
                bucket.append(observation)
                placed = True
                break
        if not placed:
            buckets.append([observation])
    return buckets


def _publisher_methods(
    observations: Iterable[_Observation],
) -> tuple[tuple[str, str], ...]:
    methods: dict[str, str] = {}
    method_priority = {
        "numeric_direct": 0,
        "named_entity_match": 0,
        "polarity_match": 0,
        "direct_extraction": 0,
        "semantic_match": 1,
        "numeric_derived": 2,
    }
    for observation in observations:
        publisher = observation.publisher_id
        method = observation.evidence_method or "direct_extraction"
        current = methods.get(publisher)
        if current is None or method_priority.get(method, 9) < method_priority.get(current, 9):
            methods[publisher] = method
    return tuple(sorted(methods.items()))


def _parse_checked_at(value: str) -> datetime | None:
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


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _claim_freshness_class(query: str, predicate: str) -> str:
    query_tokens = _tokens(query)
    if query_tokens & _VOLATILE_QUERY_TERMS or predicate in _VOLATILE_PREDICATES:
        return "volatile"
    if predicate in _CHANGING_PREDICATES:
        return "changing"
    return "stable"


def _fresh_observations(
    observations: Iterable[_Observation],
    now: datetime,
    ttl_seconds: int,
) -> list[_Observation]:
    fresh: list[_Observation] = []
    future_grace = timedelta(minutes=5)
    ttl = timedelta(seconds=ttl_seconds)
    for observation in observations:
        checked_at = _parse_checked_at(observation.checked_at)
        if checked_at is None or checked_at > now + future_grace:
            continue
        if now - checked_at <= ttl:
            fresh.append(observation)
    return fresh


def _freshness_times(
    observations: Iterable[_Observation],
    ttl_seconds: int,
) -> tuple[str, str]:
    timestamps = [
        checked_at
        for checked_at in (
            _parse_checked_at(item.checked_at)
            for item in observations
        )
        if checked_at is not None
    ]
    if not timestamps:
        return "", ""
    verified_at = max(timestamps)
    expires_at = min(timestamp + timedelta(seconds=ttl_seconds) for timestamp in timestamps)
    return _format_timestamp(verified_at), _format_timestamp(expires_at)


def _claim_from_group(
    index: int,
    key: str,
    observations: list[_Observation],
    minimum_publishers: int,
    *,
    query: str,
    now: datetime,
    volatile_ttl_seconds: int,
    changing_ttl_seconds: int,
    stable_ttl_seconds: int,
) -> ConsensusClaim:
    claim_type = observations[0].claim_type
    freshness_class = _claim_freshness_class(query, observations[0].predicate)
    ttl_seconds = {
        "volatile": volatile_ttl_seconds,
        "changing": changing_ttl_seconds,
        "stable": stable_ttl_seconds,
    }[freshness_class]
    if claim_type == "numeric":
        buckets = _numeric_bucket(observations)
    else:
        values: dict[str, list[_Observation]] = {}
        for observation in observations:
            values.setdefault(observation.value_key, []).append(observation)
        buckets = list(values.values())

    buckets.sort(
        key=lambda bucket: (
            -len(
                {
                    item.publisher_id
                    for item in _fresh_observations(bucket, now, ttl_seconds)
                }
            ),
            -len({item.publisher_id for item in bucket}),
            -sum(item.reliability_score for item in bucket),
            bucket[0].value_key,
        )
    )
    leading = buckets[0]
    fresh_leading = _fresh_observations(leading, now, ttl_seconds)
    fresh_supporting = {item.publisher_id for item in fresh_leading}
    effective_leading = (
        fresh_leading
        if len(fresh_supporting) >= minimum_publishers
        else leading
    )
    representative = sorted(
        effective_leading,
        key=lambda item: (-item.reliability_score, item.publisher_id, item.value_key),
    )[0]
    supporting = tuple(sorted({item.publisher_id for item in effective_leading}))
    fresh_conflicting_observations = [
        item
        for bucket in buckets[1:]
        for item in _fresh_observations(bucket, now, ttl_seconds)
        if item.publisher_id not in fresh_supporting
    ]
    conflicting = tuple(
        sorted({item.publisher_id for item in fresh_conflicting_observations})
    )
    distinct_fresh_publishers = {
        item.publisher_id
        for item in _fresh_observations(observations, now, ttl_seconds)
    }
    has_conflict = bool(
        conflicting
        and fresh_supporting
        and len(distinct_fresh_publishers) >= 2
    )
    if has_conflict:
        status = "conflict"
    elif len(fresh_supporting) >= minimum_publishers:
        status = "corroborated"
    elif len({item.publisher_id for item in leading}) >= minimum_publishers:
        status = "stale"
    else:
        status = "single_source"
    reliability = sum(item.reliability_score for item in effective_leading) / max(1, len(effective_leading))
    supporting_methods = _publisher_methods(effective_leading)
    conflicting_methods = _publisher_methods(fresh_conflicting_observations)
    verified_at, expires_at = _freshness_times(effective_leading, ttl_seconds)
    if status in {"corroborated", "conflict"}:
        freshness_status = "fresh"
    elif verified_at:
        freshness_status = "stale"
    else:
        freshness_status = "unknown"
    return ConsensusClaim(
        claim_id="consensus_claim_" + str(index),
        claim_type=claim_type,
        predicate=representative.predicate,
        unit=representative.unit,
        status=status,
        statement=representative.statement,
        supporting_publishers=supporting,
        conflicting_publishers=conflicting,
        reliability_score=max(0.0, min(reliability, 0.98)),
        supporting_methods=supporting_methods,
        conflicting_methods=conflicting_methods,
        freshness_class=freshness_class,
        freshness_status=freshness_status,
        verified_at=verified_at,
        expires_at=expires_at,
        freshness_ttl_seconds=ttl_seconds,
    )


def analyze_source_consensus(
    query: str,
    sources: Iterable[Mapping[str, Any]],
    *,
    minimum_publishers: int = 2,
    semantic_enabled: bool = True,
    semantic_similarity_threshold: float = 0.62,
    volatile_ttl_seconds: int = DEFAULT_VOLATILE_TTL_SECONDS,
    changing_ttl_seconds: int = DEFAULT_CHANGING_TTL_SECONDS,
    stable_ttl_seconds: int = DEFAULT_STABLE_TTL_SECONDS,
    now: datetime | None = None,
) -> SourceConsensusReport:
    """Compare public source extracts without exposing their content in traces."""

    minimum_publishers = max(2, min(int(minimum_publishers), 5))
    semantic_similarity_threshold = max(
        0.55,
        min(float(semantic_similarity_threshold), 0.9),
    )
    volatile_ttl_seconds = max(300, min(int(volatile_ttl_seconds), 86_400))
    changing_ttl_seconds = max(3_600, min(int(changing_ttl_seconds), 2_592_000))
    stable_ttl_seconds = max(86_400, min(int(stable_ttl_seconds), 31_536_000))
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    observations: list[_Observation] = []
    semantic_observations: list[_Observation] = []
    publishers: set[str] = set()
    for source in list(sources or [])[:10]:
        status = source.get("status")
        if not (isinstance(status, int) and 200 <= status < 400):
            continue
        publisher = publisher_identity(str(source.get("url") or source.get("domain") or ""))
        if not publisher:
            continue
        publishers.add(publisher)
        observations.extend(_numeric_observations(query, source, publisher))
        observations.extend(_named_observations(query, source, publisher))
        observations.extend(_boolean_observations(query, source, publisher))
        if semantic_enabled:
            semantic_observations.extend(
                _semantic_observations(query, source, publisher)
            )

    grouped: dict[str, list[_Observation]] = {}
    seen: set[tuple[str, str, str]] = set()
    for observation in observations:
        marker = (observation.key, observation.value_key, observation.publisher_id)
        if marker in seen:
            continue
        seen.add(marker)
        grouped.setdefault(observation.key, []).append(observation)

    claims_list = [
        _claim_from_group(
            index,
            key,
            grouped[key],
            minimum_publishers,
            query=query,
            now=now_utc,
            volatile_ttl_seconds=volatile_ttl_seconds,
            changing_ttl_seconds=changing_ttl_seconds,
            stable_ttl_seconds=stable_ttl_seconds,
        )
        for index, key in enumerate(sorted(grouped), start=1)
    ]
    semantic_groups = _semantic_groups(
        semantic_observations,
        semantic_similarity_threshold,
    )
    for semantic_index, group in enumerate(
        semantic_groups,
        start=len(claims_list) + 1,
    ):
        claims_list.append(
            _claim_from_group(
                semantic_index,
                "semantic",
                group,
                minimum_publishers,
                query=query,
                now=now_utc,
                volatile_ttl_seconds=volatile_ttl_seconds,
                changing_ttl_seconds=changing_ttl_seconds,
                stable_ttl_seconds=stable_ttl_seconds,
            )
        )
    claims = tuple(claims_list)
    conflict_count = sum(1 for claim in claims if claim.status == "conflict")
    corroborated_count = sum(1 for claim in claims if claim.status == "corroborated")
    stale_count = sum(1 for claim in claims if claim.status == "stale")
    if conflict_count:
        status = "mixed"
    elif corroborated_count:
        status = "corroborated"
    elif stale_count:
        status = "stale"
    else:
        status = "insufficient"
    if claims and all(claim.status == "corroborated" for claim in claims):
        coverage = "full"
    elif claims:
        coverage = "partial"
    else:
        coverage = "none"
    return SourceConsensusReport(
        status=status,
        coverage=coverage,
        publisher_count=len(publishers),
        claims=claims,
    )
