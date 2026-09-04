"""Stable Nova traits and bounded per-turn expression modifiers."""

from __future__ import annotations

from typing import Mapping

from .models import CompanionState, MoodState, SocialIntent


_CORE_TRAITS = {
    "warm": 0.82,
    "curious": 0.84,
    "confident": 0.70,
    "playful": 0.62,
    "loyal": 0.78,
    "intelligent": 0.86,
    "sarcastic": 0.28,
    "perceptive": 0.80,
    "creative": 0.76,
    "protective": 0.62,
    "conversational": 0.92,
    "willing_to_disagree": 0.58,
}


def stable_personality() -> dict[str, float]:
    """Return a copy so callers cannot rewrite Nova's core traits."""

    return dict(_CORE_TRAITS)


def expression_modifiers(
    state: CompanionState,
    intent: SocialIntent,
    mood: MoodState | None = None,
) -> dict[str, float]:
    """Calculate bounded presentation intensity without changing the core."""

    current = mood or state.nova_current_mood
    mode = intent.primary_mode
    values = {
        "warm": current.warmth,
        "curious": current.curiosity,
        "playful": current.playfulness if mode == "joking" else min(0.5, current.playfulness),
        "sarcastic": 0.0 if intent.seriousness > 0.75 else min(0.45, current.playfulness * 0.6),
        "direct": 0.8 if mode in {"technical_help", "task_execution", "advice", "debate"} else 0.6,
    }
    if mode in {"venting", "emotional_support", "frustration"}:
        values.update({"warm": min(1.0, current.warmth + 0.15), "playful": 0.0, "sarcastic": 0.0})
    return {key: max(0.0, min(1.0, float(value))) for key, value in values.items()}
