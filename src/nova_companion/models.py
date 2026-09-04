"""Typed, bounded data models for Nova's Companion Layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping
import uuid


SCHEMA_VERSION = "1.0"
PERSONALITY_VERSION = "nova-core-1"
RELATIONSHIP_STAGES = ("new", "familiar", "trusted", "established")
PREFERRED_TONES = ("neutral", "warm", "direct", "playful", "reflective")
HUMOR_STYLES = ("unknown", "light", "dry", "silly", "restrained")
AFFECTION_STYLES = ("restrained", "warm", "playful")
DISAGREEMENT_STYLES = ("gentle", "direct", "evidence_first")
ADVICE_STYLES = ("listen_first", "practical", "balanced")
MEMORY_CATEGORIES = (
    "joke",
    "project",
    "preference",
    "goal",
    "commitment",
    "decision",
    "conversation",
    "frustration",
    "pattern",
)
MEMORY_VALIDITY = ("active", "superseded", "forgotten", "disputed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()
    return text[:limit].rstrip()


def _clamp(value: Any, low: float = 0.0, high: float = 1.0, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _count(value: Any, maximum: int = 10_000_000) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, min(maximum, number))


def _choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    item = _clean(value, 80).lower()
    return item if item in allowed else default


def _json_object(value: Any, *, maximum: int = 24) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = {}
    if not isinstance(value, Mapping):
        return {}
    output: dict[str, Any] = {}
    for key, item in list(value.items())[:maximum]:
        safe_key = _clean(key, 80)
        if not safe_key or isinstance(item, (dict, list, tuple)):
            continue
        output[safe_key] = _clean(item, 240)
    return output


def _json_list(value: Any, *, maximum: int = 24, item_limit: int = 240) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for item in value[:maximum]:
        safe = _clean(item, item_limit)
        key = safe.lower()
        if safe and key not in seen:
            output.append(safe)
            seen.add(key)
    return output


def _row_value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


@dataclass
class MoodState:
    energy: float = 0.5
    playfulness: float = 0.5
    curiosity: float = 0.5
    seriousness: float = 0.5
    warmth: float = 0.5

    @classmethod
    def from_mapping(cls, value: Any) -> "MoodState":
        source = value if isinstance(value, Mapping) else {}
        return cls(
            energy=_clamp(source.get("energy"), default=0.5),
            playfulness=_clamp(source.get("playfulness"), default=0.5),
            curiosity=_clamp(source.get("curiosity"), default=0.5),
            seriousness=_clamp(source.get("seriousness"), default=0.5),
            warmth=_clamp(source.get("warmth"), default=0.5),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "energy": _clamp(self.energy, default=0.5),
            "playfulness": _clamp(self.playfulness, default=0.5),
            "curiosity": _clamp(self.curiosity, default=0.5),
            "seriousness": _clamp(self.seriousness, default=0.5),
            "warmth": _clamp(self.warmth, default=0.5),
        }


@dataclass
class CompanionState:
    schema_version: str = SCHEMA_VERSION
    user_id: str = ""
    relationship_stage: str = "new"
    familiarity_score: float = 0.0
    trust_score: float = 0.0
    interaction_count: int = 0
    first_interaction_at: str = ""
    last_interaction_at: str = ""
    preferred_tone: str = "neutral"
    humor_style: str = "unknown"
    conversational_energy: float = 0.5
    affection_style: str = "restrained"
    disagreement_style: str = "gentle"
    advice_style: str = "balanced"
    known_user_preferences: dict[str, Any] = field(default_factory=dict)
    recurring_topics: list[str] = field(default_factory=list)
    shared_history_summary: list[str] = field(default_factory=list)
    active_projects: list[str] = field(default_factory=list)
    important_people: list[str] = field(default_factory=list)
    unfinished_conversations: list[str] = field(default_factory=list)
    recent_emotional_context: list[str] = field(default_factory=list)
    nova_current_mood: MoodState = field(default_factory=MoodState)
    nova_personality_state: dict[str, Any] = field(default_factory=dict)
    personality_version: str = PERSONALITY_VERSION
    updated_at: str = ""

    @classmethod
    def new(cls, user_id: str, *, now: str | None = None) -> "CompanionState":
        timestamp = _clean(now or _now(), 80)
        return cls(
            user_id=_clean(user_id, 160),
            first_interaction_at=timestamp,
            last_interaction_at=timestamp,
            updated_at=timestamp,
            nova_personality_state={"expression_version": "1"},
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CompanionState":
        mood_value = _row_value(row, "nova_current_mood_json", {})
        if isinstance(mood_value, str):
            try:
                mood_value = json.loads(mood_value)
            except (TypeError, ValueError):
                mood_value = {}
        personality_value = _row_value(row, "nova_personality_state_json", {})
        if isinstance(personality_value, str):
            try:
                personality_value = json.loads(personality_value)
            except (TypeError, ValueError):
                personality_value = {}
        return cls(
            schema_version=_clean(_row_value(row, "schema_version", SCHEMA_VERSION), 40) or SCHEMA_VERSION,
            user_id=_clean(_row_value(row, "user_id", ""), 160),
            relationship_stage=_choice(_row_value(row, "relationship_stage"), RELATIONSHIP_STAGES, "new"),
            familiarity_score=_clamp(_row_value(row, "familiarity_score"), default=0.0),
            trust_score=_clamp(_row_value(row, "trust_score"), default=0.0),
            interaction_count=_count(_row_value(row, "interaction_count")),
            first_interaction_at=_clean(_row_value(row, "first_interaction_at", ""), 80),
            last_interaction_at=_clean(_row_value(row, "last_interaction_at", ""), 80),
            preferred_tone=_choice(_row_value(row, "preferred_tone"), PREFERRED_TONES, "neutral"),
            humor_style=_choice(_row_value(row, "humor_style"), HUMOR_STYLES, "unknown"),
            conversational_energy=_clamp(_row_value(row, "conversational_energy"), default=0.5),
            affection_style=_choice(_row_value(row, "affection_style"), AFFECTION_STYLES, "restrained"),
            disagreement_style=_choice(_row_value(row, "disagreement_style"), DISAGREEMENT_STYLES, "gentle"),
            advice_style=_choice(_row_value(row, "advice_style"), ADVICE_STYLES, "balanced"),
            known_user_preferences=_json_object(_row_value(row, "known_user_preferences_json", {})),
            recurring_topics=_json_list(_row_value(row, "recurring_topics_json", []), maximum=16, item_limit=80),
            shared_history_summary=_json_list(_row_value(row, "shared_history_summary_json", []), maximum=12, item_limit=240),
            active_projects=_json_list(_row_value(row, "active_projects_json", []), maximum=12, item_limit=120),
            important_people=_json_list(_row_value(row, "important_people_json", []), maximum=12, item_limit=120),
            unfinished_conversations=_json_list(_row_value(row, "unfinished_conversations_json", []), maximum=8, item_limit=160),
            recent_emotional_context=_json_list(_row_value(row, "recent_emotional_context_json", []), maximum=8, item_limit=80),
            nova_current_mood=MoodState.from_mapping(mood_value),
            nova_personality_state=_json_object(personality_value, maximum=12),
            personality_version=_clean(_row_value(row, "personality_version", PERSONALITY_VERSION), 80) or PERSONALITY_VERSION,
            updated_at=_clean(_row_value(row, "updated_at", ""), 80),
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "user_id": _clean(self.user_id, 160),
            "relationship_stage": _choice(self.relationship_stage, RELATIONSHIP_STAGES, "new"),
            "familiarity_score": _clamp(self.familiarity_score),
            "trust_score": _clamp(self.trust_score),
            "interaction_count": _count(self.interaction_count),
            "first_interaction_at": _clean(self.first_interaction_at, 80),
            "last_interaction_at": _clean(self.last_interaction_at, 80),
            "preferred_tone": _choice(self.preferred_tone, PREFERRED_TONES, "neutral"),
            "humor_style": _choice(self.humor_style, HUMOR_STYLES, "unknown"),
            "conversational_energy": _clamp(self.conversational_energy, default=0.5),
            "affection_style": _choice(self.affection_style, AFFECTION_STYLES, "restrained"),
            "disagreement_style": _choice(self.disagreement_style, DISAGREEMENT_STYLES, "gentle"),
            "advice_style": _choice(self.advice_style, ADVICE_STYLES, "balanced"),
            "known_user_preferences_json": json.dumps(_json_object(self.known_user_preferences), ensure_ascii=False),
            "recurring_topics_json": json.dumps(_json_list(self.recurring_topics, maximum=16, item_limit=80), ensure_ascii=False),
            "shared_history_summary_json": json.dumps(_json_list(self.shared_history_summary, maximum=12, item_limit=240), ensure_ascii=False),
            "active_projects_json": json.dumps(_json_list(self.active_projects, maximum=12, item_limit=120), ensure_ascii=False),
            "important_people_json": json.dumps(_json_list(self.important_people, maximum=12, item_limit=120), ensure_ascii=False),
            "unfinished_conversations_json": json.dumps(_json_list(self.unfinished_conversations, maximum=8, item_limit=160), ensure_ascii=False),
            "recent_emotional_context_json": json.dumps(_json_list(self.recent_emotional_context, maximum=8, item_limit=80), ensure_ascii=False),
            "nova_current_mood_json": json.dumps(MoodState.from_mapping(self.nova_current_mood).to_dict(), ensure_ascii=False),
            "nova_personality_state_json": json.dumps(_json_object(self.nova_personality_state, maximum=12), ensure_ascii=False),
            "personality_version": _clean(self.personality_version, 80) or PERSONALITY_VERSION,
            "updated_at": _clean(self.updated_at, 80) or _now(),
        }


@dataclass
class RelationshipMemory:
    memory_id: str
    user_id: str
    category: str
    content: str
    importance_score: float = 0.5
    confidence: float = 0.5
    created_at: str = ""
    last_referenced_at: str = ""
    reference_count: int = 0
    source_conversation_id: str = ""
    validity_status: str = "active"

    @classmethod
    def new(cls, user_id: str, category: str, content: str, *, now: str | None = None, **kwargs: Any) -> "RelationshipMemory":
        timestamp = _clean(now or _now(), 80)
        return cls(
            memory_id="rel_" + uuid.uuid4().hex,
            user_id=_clean(user_id, 160),
            category=_choice(category, MEMORY_CATEGORIES, "conversation"),
            content=_clean(content, 500),
            importance_score=_clamp(kwargs.get("importance_score"), default=0.5),
            confidence=_clamp(kwargs.get("confidence"), default=0.5),
            created_at=timestamp,
            last_referenced_at=timestamp,
            reference_count=_count(kwargs.get("reference_count"), 100_000),
            source_conversation_id=_clean(kwargs.get("source_conversation_id", ""), 160),
            validity_status=_choice(kwargs.get("validity_status"), MEMORY_VALIDITY, "active"),
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "RelationshipMemory":
        return cls(
            memory_id=_clean(_row_value(row, "memory_id", ""), 100),
            user_id=_clean(_row_value(row, "user_id", ""), 160),
            category=_choice(_row_value(row, "category"), MEMORY_CATEGORIES, "conversation"),
            content=_clean(_row_value(row, "content", ""), 500),
            importance_score=_clamp(_row_value(row, "importance_score"), default=0.5),
            confidence=_clamp(_row_value(row, "confidence"), default=0.5),
            created_at=_clean(_row_value(row, "created_at", ""), 80),
            last_referenced_at=_clean(_row_value(row, "last_referenced_at", ""), 80),
            reference_count=_count(_row_value(row, "reference_count"), 100_000),
            source_conversation_id=_clean(_row_value(row, "source_conversation_id", ""), 160),
            validity_status=_choice(_row_value(row, "validity_status"), MEMORY_VALIDITY, "active"),
        )


@dataclass(frozen=True)
class SocialIntent:
    primary_mode: str
    secondary_modes: tuple[str, ...] = ()
    confidence: float = 0.0
    seriousness: float = 0.5
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class SocialPlan:
    primary_mode: str
    secondary_modes: tuple[str, ...] = ()
    tone: str = "neutral"
    directness: float = 0.7
    humor: float = 0.0
    affection: float = 0.0
    challenge_user: bool = False
    listen_first: bool = False
    ask_follow_up: bool = False
    reference_memory: bool = False
    response_length: str = "normal"
    intensity: float = 0.4
    reason_codes: tuple[str, ...] = ()

    @classmethod
    def neutral(cls) -> "SocialPlan":
        return cls(primary_mode="casual_chat")


@dataclass(frozen=True)
class CompanionContext:
    schema_version: str
    relationship_stage: str
    familiarity_score: float
    trust_score: float
    personality: dict[str, float]
    mood: dict[str, float]
    social_plan: SocialPlan
    memories: tuple[RelationshipMemory, ...] = ()
    unfinished_count: int = 0

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "relationship_stage": self.relationship_stage,
            "familiarity_score": round(self.familiarity_score, 3),
            "trust_score": round(self.trust_score, 3),
            "personality": dict(self.personality),
            "mood": dict(self.mood),
            "social_plan": {
                "primary_mode": self.social_plan.primary_mode,
                "secondary_modes": list(self.social_plan.secondary_modes),
                "tone": self.social_plan.tone,
                "directness": round(self.social_plan.directness, 2),
                "humor": round(self.social_plan.humor, 2),
                "affection": round(self.social_plan.affection, 2),
                "challenge_user": self.social_plan.challenge_user,
                "listen_first": self.social_plan.listen_first,
                "ask_follow_up": self.social_plan.ask_follow_up,
                "reference_memory": self.social_plan.reference_memory,
                "response_length": self.social_plan.response_length,
            },
            "memories": [
                {
                    "memory_id": memory.memory_id,
                    "category": memory.category,
                    "content": memory.content,
                }
                for memory in self.memories[:4]
            ],
            "unfinished_count": max(0, min(int(self.unfinished_count), 8)),
        }
