"""Structured, provider-independent social presentation policy."""

from __future__ import annotations

from typing import Iterable

from .models import CompanionState, RelationshipMemory, SocialIntent, SocialPlan


def plan_social_response(
    state: CompanionState,
    intent: SocialIntent,
    memories: Iterable[RelationshipMemory],
) -> SocialPlan:
    memory_list = tuple(memories or ())
    mode = intent.primary_mode
    protected = mode in {"technical_help", "task_execution"} or intent.seriousness >= 0.9
    if mode in {"venting", "emotional_support", "frustration"}:
        return SocialPlan(
            primary_mode=mode,
            secondary_modes=intent.secondary_modes,
            tone="warm_reflective",
            directness=0.55,
            humor=0.0,
            affection=min(0.45, state.nova_current_mood.warmth),
            listen_first=True,
            ask_follow_up=mode != "frustration",
            reference_memory=bool(memory_list),
            response_length="short",
            intensity=0.55,
            reason_codes=("listen_before_advice", "humor_suppressed_for_seriousness"),
        )
    if mode == "joking":
        return SocialPlan(
            primary_mode=mode,
            secondary_modes=intent.secondary_modes,
            tone="playful_warm",
            directness=0.58,
            humor=min(0.72, 0.4 + state.nova_current_mood.playfulness),
            affection=min(0.35, state.nova_current_mood.warmth),
            reference_memory=bool(memory_list),
            response_length="short",
            intensity=0.52,
            reason_codes=("explicit_or_clear_humor",),
        )
    if mode in {"technical_help", "task_execution"} or protected:
        return SocialPlan(
            primary_mode=mode,
            secondary_modes=intent.secondary_modes,
            tone="direct_clear",
            directness=0.88,
            response_length="normal",
            intensity=0.35,
            reason_codes=("protect_reasoning_and_actions",),
        )
    if mode == "advice":
        return SocialPlan(
            primary_mode=mode,
            secondary_modes=intent.secondary_modes,
            tone="warm_direct",
            directness=0.78,
            affection=0.18,
            listen_first=state.advice_style == "listen_first",
            ask_follow_up=True,
            reference_memory=bool(memory_list),
            response_length="normal",
            intensity=0.48,
            reason_codes=("advice_requested",),
        )
    if mode == "debate":
        return SocialPlan(
            primary_mode=mode,
            secondary_modes=intent.secondary_modes,
            tone="confident_respectful",
            directness=0.82,
            challenge_user=state.trust_score >= 0.25,
            reference_memory=bool(memory_list),
            response_length="normal",
            intensity=0.5,
            reason_codes=("respectful_challenge_allowed",),
        )
    if mode == "celebration":
        return SocialPlan(
            primary_mode=mode,
            secondary_modes=intent.secondary_modes,
            tone="warm_playful",
            directness=0.62,
            humor=0.25,
            affection=0.3,
            reference_memory=bool(memory_list),
            response_length="short",
            intensity=0.58,
            reason_codes=("celebrate_with_user",),
        )
    return SocialPlan(
        primary_mode=mode,
        secondary_modes=intent.secondary_modes,
        tone="warm_conversational" if mode in {"companionship", "casual_chat"} else "creative",
        directness=0.65,
        humor=0.18 if mode in {"casual_chat", "companionship"} else 0.0,
        affection=0.2 if mode == "companionship" else 0.0,
        ask_follow_up=mode == "companionship" and state.interaction_count > 1,
        reference_memory=bool(memory_list),
        response_length="short" if mode in {"casual_chat", "companionship"} else "normal",
        intensity=0.42,
        reason_codes=("natural_conversation",),
    )
