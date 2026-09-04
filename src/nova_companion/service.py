"""Companion turn lifecycle used by managed Nova chat."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from .adaptation import adapt_state
from .context_builder import build_companion_context
from .intent import classify_social_intent
from .models import CompanionContext, CompanionState, RelationshipMemory, SocialIntent, SocialPlan
from .social_reasoning import plan_social_response
from .store import CompanionStore


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(token) > 1][:16]


@dataclass
class CompanionTurn:
    enabled: bool
    user_id: str
    conversation_id: str
    state: CompanionState
    intent: SocialIntent
    plan: SocialPlan
    context: CompanionContext
    memories: tuple[RelationshipMemory, ...]

    @property
    def context_block(self) -> dict[str, Any]:
        return self.context.to_prompt_dict()

    @property
    def memory_ids(self) -> tuple[str, ...]:
        return tuple(memory.memory_id for memory in self.memories)


class CompanionService:
    def __init__(self, database: str | None = None, *, persistence: bool = True) -> None:
        self.store = CompanionStore(database)
        self.persistence = bool(persistence)

    def begin_turn(
        self,
        text: str,
        *,
        user_id: str,
        conversation_id: str,
        context: dict[str, Any] | None,
        decision: Any,
    ) -> CompanionTurn:
        del context
        owner = str(user_id or "").strip()[:160]
        enabled = bool(owner) and self.persistence
        state = self.store.load_state(owner) if owner else None
        state = state or CompanionState.new(owner or "anonymous")
        intent = classify_social_intent(text, decision)
        memories = tuple(self.store.search_memories(owner, _tokens(text), limit=4)) if enabled else ()
        plan = plan_social_response(state, intent, memories)
        companion_context = build_companion_context(text, state, intent, plan, memories)
        return CompanionTurn(
            enabled=enabled,
            user_id=owner,
            conversation_id=str(conversation_id or "")[:160],
            state=state,
            intent=intent,
            plan=plan,
            context=companion_context,
            memories=memories,
        )

    @staticmethod
    def _reviewed_memory(turn: CompanionTurn, answer: str) -> RelationshipMemory | None:
        text = " ".join((str(turn.intent.primary_mode), str(answer or ""))).lower()
        if turn.intent.primary_mode not in {"task_execution", "brainstorming", "celebration", "companionship"}:
            return None
        if not re.search(r"\b(?:project|building|working on|goal|we did it|together)\b", text):
            return None
        content = re.sub(r"\s+", " ", str(answer or "")).strip()[:320]
        if not content:
            return None
        return RelationshipMemory.new(
            turn.user_id,
            "project" if "project" in text or "building" in text else "conversation",
            content,
            importance_score=0.65,
            confidence=0.7,
            source_conversation_id=turn.conversation_id,
        )

    def finalize_turn(self, turn: CompanionTurn, answer: str, trace: dict[str, Any] | None) -> dict[str, Any]:
        if not turn.enabled:
            return {
                "enabled": False,
                "state_persisted": False,
                "memory_content_logged": False,
                "memory_count": 0,
            }
        metadata = trace if isinstance(trace, dict) else {}
        accepted = bool(str(answer or "").strip()) and (
            str(metadata.get("source") or "").lower() not in {"answer_firewall_recovery"}
            or bool(metadata.get("companion_continuity_fallback"))
        )
        if accepted:
            self.store.mark_referenced(turn.user_id, turn.memory_ids)
            adapt_state(turn.state, turn.intent, now=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            self.store.save_state(turn.state)
            memory = self._reviewed_memory(turn, answer)
            if memory is not None:
                self.store.add_memory(memory)
        return {
            "enabled": True,
            "state_persisted": bool(accepted),
            "memory_content_logged": False,
            "primary_mode": turn.intent.primary_mode,
            "secondary_modes": list(turn.intent.secondary_modes),
            "intent_confidence": round(turn.intent.confidence, 3),
            "relationship_stage": turn.state.relationship_stage,
            "familiarity_score": round(turn.state.familiarity_score, 3),
            "trust_score": round(turn.state.trust_score, 3),
            "interaction_count": turn.state.interaction_count,
            "memory_count": len(turn.memories),
            "memory_ids": list(turn.memory_ids),
            "reference_memory": bool(turn.plan.reference_memory),
            "social_plan": {
                "tone": turn.plan.tone,
                "directness": round(turn.plan.directness, 2),
                "humor": round(turn.plan.humor, 2),
                "listen_first": turn.plan.listen_first,
                "ask_follow_up": turn.plan.ask_follow_up,
                "challenge_user": turn.plan.challenge_user,
            },
        }
