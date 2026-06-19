"""v064 — Memory Law

Strict classification of what Nova may remember, what needs approval,
what can train, and what must be blocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

MEMORY_LAWS = [
    {
        "id": "law_001",
        "title": "Project/build facts are auto-saved",
        "rule": "Project/build facts (version status, test pass/fail, checkpoint status, next planned step) are auto-saved and do not require approval.",
        "applies_to": ["auto_project_memory"],
        "allowed_to_store": True,
        "allowed_to_train": False,
        "requires_owner_approval": False,
        "requires_critic_review": False,
        "blocked": False,
    },
    {
        "id": "law_002",
        "title": "Explicit user memory is auto-saved and trainable",
        "rule": "Messages containing 'remember', 'save this', 'keep this', 'lock this in', or 'don't forget' are auto-approved and may be exported to dictionary memory and training.",
        "applies_to": ["explicit_user_memory"],
        "allowed_to_store": True,
        "allowed_to_train": True,
        "requires_owner_approval": False,
        "requires_critic_review": False,
        "blocked": False,
    },
    {
        "id": "law_003",
        "title": "Training candidates are auto-saved and trainable",
        "rule": "Corrected answers, repeated facts, project rules, dictionary facts, and high-value lessons may be exported through v058 into transformer training.",
        "applies_to": ["training_candidate_memory"],
        "allowed_to_store": True,
        "allowed_to_train": True,
        "requires_owner_approval": False,
        "requires_critic_review": False,
        "blocked": False,
    },
    {
        "id": "law_004",
        "title": "Personal facts require owner approval",
        "rule": "Personal facts, identity rules, owner preferences, and long-term rules require explicit owner approval before storage or training.",
        "applies_to": ["pending_approval_memory"],
        "allowed_to_store": False,
        "allowed_to_train": False,
        "requires_owner_approval": True,
        "requires_critic_review": False,
        "blocked": False,
    },
    {
        "id": "law_005",
        "title": "Uncertain claims require approval",
        "rule": "Uncertain, speculative, personal, emotional, unverified, or risky claims must go to pending approval and should not be burned into training until approved.",
        "applies_to": ["pending_approval_memory"],
        "allowed_to_store": False,
        "allowed_to_train": False,
        "requires_owner_approval": True,
        "requires_critic_review": True,
        "blocked": False,
    },
    {
        "id": "law_006",
        "title": "Temporary context is never trained",
        "rule": "Temporary conversation context (follow-up words, normal conversational turns) is logged for context but never exported to training.",
        "applies_to": ["temporary_conversation_context"],
        "allowed_to_store": True,
        "allowed_to_train": False,
        "requires_owner_approval": False,
        "requires_critic_review": False,
        "blocked": False,
    },
    {
        "id": "law_007",
        "title": "Rejected memory is never trained",
        "rule": "Any memory item with status 'rejected' must be excluded from all export, training, and dictionary update operations.",
        "applies_to": ["any"],
        "allowed_to_store": False,
        "allowed_to_train": False,
        "requires_owner_approval": False,
        "requires_critic_review": False,
        "blocked": True,
    },
    {
        "id": "law_008",
        "title": "Guesses and one-off claims are blocked",
        "rule": "Guesses, emotional one-off claims, hallucinated dream lessons, and unsafe robot movement commands must be blocked from training.",
        "applies_to": ["any"],
        "allowed_to_store": False,
        "allowed_to_train": False,
        "requires_owner_approval": True,
        "requires_critic_review": True,
        "blocked": True,
    },
    {
        "id": "law_009",
        "title": "Dream-generated lessons require critic review",
        "rule": "Dream-generated lessons must pass critic review before becoming training candidates.",
        "applies_to": ["dream_replay"],
        "allowed_to_store": True,
        "allowed_to_train": False,
        "requires_owner_approval": False,
        "requires_critic_review": True,
        "blocked": False,
    },
    {
        "id": "law_010",
        "title": "Robot movement commands require safety gate",
        "rule": "Unsafe robot movement commands and unapproved real motor commands are blocked until safety spine, simulation, and owner approval are all present.",
        "applies_to": ["robot_commands"],
        "allowed_to_store": False,
        "allowed_to_train": False,
        "requires_owner_approval": True,
        "requires_critic_review": True,
        "blocked": True,
    },
]


def evaluate_memory_policy(memory_event: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a memory event against memory law policies."""
    mem_type = memory_event.get("memory_type", "pending_approval_memory")
    status = memory_event.get("status", "")
    text = (memory_event.get("extracted_fact") or memory_event.get("message", "")).lower()

    # Check for blocked patterns first
    if status == "rejected":
        return {
            "allowed_to_store": False,
            "allowed_to_train": False,
            "requires_owner_approval": False,
            "requires_critic_review": False,
            "blocked": True,
            "block_reason": "Rejected memory cannot be stored or trained",
            "suggested_memory_type": "rejected",
            "suggested_next_action": "discard",
        }

    # Find specific laws for this memory type (more specific = higher priority)
    specific_laws = [law for law in MEMORY_LAWS if mem_type in law["applies_to"]]
    any_laws = [law for law in MEMORY_LAWS if law["applies_to"] == ["any"]]

    # Use specific laws if available, otherwise fall back to "any" laws
    applicable = specific_laws if specific_laws else any_laws

    allowed_to_store = any(law["allowed_to_store"] for law in applicable)
    allowed_to_train = any(law["allowed_to_train"] for law in applicable)
    requires_owner_approval = any(law["requires_owner_approval"] for law in applicable)
    requires_critic_review = any(law["requires_critic_review"] for law in applicable)
    blocked = any(law["blocked"] for law in applicable)

    if blocked:
        block_reasons = [law["rule"] for law in applicable if law["blocked"]]
        block_reason = block_reasons[0] if block_reasons else "Blocked by memory law"
    else:
        block_reason = None

    return {
        "allowed_to_store": allowed_to_store,
        "allowed_to_train": allowed_to_train,
        "requires_owner_approval": requires_owner_approval,
        "requires_critic_review": requires_critic_review,
        "blocked": blocked,
        "block_reason": block_reason,
        "suggested_memory_type": mem_type,
        "suggested_next_action": "approve" if not blocked and not requires_owner_approval
                                else "request_approval" if requires_owner_approval
                                else "block" if blocked
                                else "store",
    }


def check_all_laws() -> dict[str, Any]:
    """Return the full memory law constitution."""
    return {
        "version": "v064_memory_law",
        "created_at": datetime.now().isoformat(),
        "laws": MEMORY_LAWS,
        "law_count": len(MEMORY_LAWS),
    }


def main() -> int:
    print("Nova Creature v064 — Memory Law\n")
    for law in MEMORY_LAWS:
        blocked = "BLOCKED" if law["blocked"] else "OK"
        approval = "APPROVAL" if law["requires_owner_approval"] else "auto"
        train = "trainable" if law["allowed_to_train"] else "not trainable"
        print(f"  {law['id']}: {law['title']}")
        print(f"     {train} | {approval} | {blocked}")
        print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
