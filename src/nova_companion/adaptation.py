"""Slow, bounded adaptation of relationship state and conversational mood."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import CompanionState, MoodState, SocialIntent


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _step(current: float, target: float, maximum: float = 0.08) -> float:
    delta = max(-maximum, min(maximum, target - current))
    return _clamp(current + delta)


def _stage(familiarity: float) -> str:
    if familiarity < 0.15:
        return "new"
    if familiarity < 0.4:
        return "familiar"
    if familiarity < 0.7:
        return "trusted"
    return "established"


def adapt_state(state: CompanionState, intent: SocialIntent, *, now: str | None = None) -> CompanionState:
    timestamp = str(now or datetime.now(timezone.utc).isoformat(timespec="seconds"))[:80]
    state.interaction_count = min(10_000_000, max(0, int(state.interaction_count)) + 1)
    state.familiarity_score = _clamp(state.familiarity_score + 0.01)
    trust_delta = 0.006 if intent.primary_mode not in {"frustration", "task_execution"} else 0.003
    state.trust_score = _clamp(state.trust_score + trust_delta)
    state.relationship_stage = _stage(state.familiarity_score)
    current = MoodState.from_mapping(state.nova_current_mood)
    targets = {
        "energy": current.energy,
        "playfulness": current.playfulness,
        "curiosity": current.curiosity,
        "seriousness": current.seriousness,
        "warmth": current.warmth,
    }
    if intent.primary_mode in {"venting", "emotional_support", "frustration"}:
        targets.update({"energy": 0.42, "playfulness": 0.15, "seriousness": 0.75, "warmth": 0.82})
    elif intent.primary_mode == "joking":
        targets.update({"energy": 0.7, "playfulness": 0.82, "seriousness": 0.3, "warmth": 0.68})
    elif intent.primary_mode in {"technical_help", "task_execution", "debate"}:
        targets.update({"curiosity": 0.78, "seriousness": 0.72, "playfulness": 0.3})
    elif intent.primary_mode == "celebration":
        targets.update({"energy": 0.82, "playfulness": 0.72, "warmth": 0.84})
    else:
        targets.update({"curiosity": 0.7, "warmth": 0.68})
    state.nova_current_mood = MoodState(
        energy=_step(current.energy, targets["energy"]),
        playfulness=_step(current.playfulness, targets["playfulness"]),
        curiosity=_step(current.curiosity, targets["curiosity"]),
        seriousness=_step(current.seriousness, targets["seriousness"]),
        warmth=_step(current.warmth, targets["warmth"]),
    )
    label = intent.primary_mode
    state.recent_emotional_context = (state.recent_emotional_context + [label])[-8:]
    state.last_interaction_at = timestamp
    state.updated_at = timestamp
    return state
