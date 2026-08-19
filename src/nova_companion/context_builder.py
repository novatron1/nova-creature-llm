"""Build a compact, prompt-safe Companion context block."""

from __future__ import annotations

from typing import Iterable

from .models import CompanionContext, CompanionState, RelationshipMemory, SocialIntent, SocialPlan
from .personality import expression_modifiers, stable_personality


def build_companion_context(
    user_message: str,
    state: CompanionState,
    intent: SocialIntent,
    plan: SocialPlan,
    memories: Iterable[RelationshipMemory],
) -> CompanionContext:
    del user_message  # The deterministic classifier already consumed the bounded input.
    selected = []
    for memory in tuple(memories or ())[:4]:
        selected.append(
            RelationshipMemory(
                memory_id=memory.memory_id,
                user_id=memory.user_id,
                category=memory.category,
                content=str(memory.content or "")[:320],
                importance_score=memory.importance_score,
                confidence=memory.confidence,
                created_at=memory.created_at,
                last_referenced_at=memory.last_referenced_at,
                reference_count=memory.reference_count,
                source_conversation_id=memory.source_conversation_id,
                validity_status=memory.validity_status,
            )
        )
    context = CompanionContext(
        schema_version="1.0",
        relationship_stage=state.relationship_stage,
        familiarity_score=max(0.0, min(1.0, state.familiarity_score)),
        trust_score=max(0.0, min(1.0, state.trust_score)),
        personality={**stable_personality(), **expression_modifiers(state, intent)},
        mood=state.nova_current_mood.to_dict(),
        social_plan=plan,
        memories=tuple(selected),
        unfinished_count=min(8, len(state.unfinished_conversations)),
    )
    # Keep prompt projection bounded even if future fields are added.
    while len(str(context.to_prompt_dict())) > 3000 and selected:
        selected.pop()
        context = CompanionContext(
            schema_version=context.schema_version,
            relationship_stage=context.relationship_stage,
            familiarity_score=context.familiarity_score,
            trust_score=context.trust_score,
            personality=context.personality,
            mood=context.mood,
            social_plan=context.social_plan,
            memories=tuple(selected),
            unfinished_count=context.unfinished_count,
        )
    return context
