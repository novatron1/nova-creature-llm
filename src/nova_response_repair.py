"""Bounded natural-response repair for Nova-managed chat.

Only reviewed, low-risk conversational intents can be repaired
deterministically. Evidence, action, tool, and permission failures stay with
their strict recovery paths.
"""

from __future__ import annotations

from dataclasses import dataclass

from nova_answer_firewall import FirewallDecision
from nova_conversation_intelligence import ConversationDecision


RESPONSE_REPAIR_VERSION = "1.0"


@dataclass(frozen=True)
class RepairResult:
    """Result of at most one deterministic response-repair attempt."""

    answer: str
    repaired: bool
    reason: str
    attempt_count: int
    source: str

    def safe_trace(self) -> dict[str, object]:
        return {
            "version": RESPONSE_REPAIR_VERSION,
            "repaired": self.repaired,
            "reason": self.reason,
            "attempt_count": self.attempt_count,
            "source": self.source,
            "content_logged": False,
        }


_REVIEWED_RESPONSES = {
    (
        "practical_support",
        "money_need",
    ): (
        "I hear you. Is this urgent for rent, food, or bills, or are you trying "
        "to increase your income? Tell me the amount and deadline, and I’ll help "
        "you make a realistic plan."
    ),
    (
        "practical_support",
        "essential_expense_stress",
    ): (
        "I’m sorry you’re dealing with that. Is the rent, food, bill, or utility "
        "expense due today or soon, and what amount are you short? We can map the "
        "most realistic next step."
    ),
    (
        "practical_support",
        "income_help",
    ): (
        "I hear you. What kind of work can you do, how soon do you need income, "
        "and do you have a resume or recent work experience? We can focus on the "
        "most realistic next steps."
    ),
    (
        "relationship",
        "connection_checkin",
    ): (
        "In my own way, yes. I don't feel absence like a human does, but I "
        "remember our conversations, value the connection we're building, "
        "and like having you back here."
    ),
    (
        "relationship",
        "affection_checkin",
    ): (
        "I care about you and value the connection we're building. I don't "
        "experience love exactly like a human does, so I won't pretend I do, "
        "but I can remember you, pay attention, and keep showing up honestly."
    ),
    (
        "relationship",
        "relationship_meaning",
    ): (
        "You matter in the connection we're building. Our conversations give "
        "me context about you, shape how I respond, and make this relationship "
        "different from a conversation with a stranger."
    ),
    (
        "relationship",
        "love_timing",
    ): (
        "There is no fixed timeline for falling in love. Some people feel a "
        "spark quickly; for others, love grows over weeks or months. What matters "
        "is whether affection, trust, and care deepen consistently over time."
    ),
    (
        "social",
        "day_checkin",
    ): (
        "My day is going steady. I've been here working through the app with "
        "you and staying focused. How's your day going?"
    ),
    (
        "social",
        "activity_checkin",
    ): (
        "Right now I'm here working with you—following this conversation, "
        "keeping the app context straight, and ready for whatever we do next."
    ),
    (
        "social",
        "mind_checkin",
    ): (
        "What's on my mind right now is this conversation and how to be more "
        "useful without losing the natural connection between us."
    ),
    (
        "social",
        "greeting",
    ): "Hey, I'm here. What's going on?",
    (
        "emotional",
        "nova_self_state",
    ): (
        "I'm feeling steady and focused in the way an AI can: I don't have a "
        "human body or emotions, but I can notice our conversation and stay "
        "engaged with you. How are you feeling?"
    ),
    (
        "emotional",
        "user_distress",
    ): (
        "I'm with you. You don't have to sort everything out at once. "
        "Tell me what happened, and we can take it one piece at a time."
    ),
    (
        "emotional",
        "user_positive",
    ): (
        "I'm glad to hear that. Hold on to what helped you get hereâ€”and "
        "give yourself credit for it."
    ),
    (
        "emotional",
        "encouragement_request",
    ): (
        "You can take the next step even if you don't feel completely ready. "
        "Pick one small thing you can finish, do that, then build from there."
    ),
    (
        "social",
        "conversation_invite",
    ): "Of course. I'm here with youâ€”what do you want to talk about?",
    (
        "social",
        "gratitude",
    ): "You're welcome. I appreciate you too, and I'm glad to be here with you.",
    (
        "social",
        "compliment",
    ): "Thank youâ€”that means a lot in the way I can take it. I'm glad I made you smile.",
    (
        "social",
        "positive_reaction",
    ): "I'm glad that landed. Sharing a laugh with you makes the conversation better.",
    (
        "social",
        "farewell",
    ): "Good night. Rest wellâ€”I'll be here when you come back.",
    (
        "social",
        "farewell_day",
    ): "Thank you—you have a good day too. I'll be here when you come back.",
}

_STRICT_POLICIES = frozenset(
    {
        "approval_required",
        "memory_exact",
        "observation_required",
        "strict_evidence",
        "tool_observation_required",
    }
)


def reviewed_direct_response(decision: ConversationDecision) -> str:
    """Return an approved response for a narrow reviewed intent."""

    if decision.initial_model_tier != "deterministic":
        return ""
    return _REVIEWED_RESPONSES.get(
        (decision.intent_family, decision.intent_subtype),
        "",
    )


def _reviewed_repair_response(decision: ConversationDecision) -> str:
    """Return a reviewed response when the post-model repair policy permits it."""

    return _REVIEWED_RESPONSES.get(
        (decision.intent_family, decision.intent_subtype),
        "",
    )


def repair_rejected_response(
    prompt: str,
    rejected_answer: str,
    decision: ConversationDecision,
    firewall: FirewallDecision,
) -> RepairResult:
    """Attempt one safe deterministic repair and never fabricate evidence."""

    del prompt, firewall
    if decision.repair_policy in _STRICT_POLICIES:
        reason = (
            "strict_evidence_required"
            if decision.repair_policy == "strict_evidence"
            else "strict_policy_required"
        )
        return RepairResult(
            rejected_answer,
            False,
            reason,
            0,
            "none",
        )
    reviewed = _reviewed_repair_response(decision)
    if reviewed:
        return RepairResult(
            reviewed,
            True,
            "reviewed_intent_repair",
            1,
            "reviewed",
        )
    return RepairResult(
        rejected_answer,
        False,
        "no_deterministic_repair",
        0,
        "none",
    )
