from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ROLES = [
    "left_hemisphere", "right_hemisphere", "memory_transformer",
    "planner_transformer", "critic_conscience_transformer",
    "dream_simulation_transformer", "speech_output_transformer",
]

MEMORY_TYPES = [
    "auto_project_memory",
    "explicit_user_memory",
    "temporary_conversation_context",
    "pending_approval_memory",
    "training_candidate_memory",
]

EXPLICIT_SAVE_TRIGGERS = [
    r"\bremember\b", r"\bsave this\b", r"\bkeep this\b",
    r"\block this in\b", r"\bdon'?t forget\b",
]

PERSONAL_SUBJECTS = [
    "my favorite", "my name is", "i like", "i dislike", "i feel", "i think",
    "my opinion", "my pet", "my family", "my job", "my age",
]

UNCERTAIN_TRIGGERS = [
    "maybe", "perhaps", "could be", "might be", "not sure",
    "i think it's", "possibly", "guess",
]

TRAINING_TRIGGERS = [
    "the correct answer", "the right answer", "the answer is",
    "should be", "always answer", "never answer", "the proper",
    "correction", "corrected", "the truth is",
]


def normalize(text: str) -> str:
    s = str(text or "").lower().strip()
    s = re.sub(r"[^a-z0-9+\-*x ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def classify_memory_event(
    message: str,
    answer: str | None = None,
    route: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Classify a message into one of five memory types.
    Returns a dict with memory_type, confidence, reason, storage decisions, and extracted fact.
    """
    msg_raw = str(message or "").strip()
    msg_norm = normalize(msg_raw)
    ans_norm = normalize(answer or "")
    ctx = context or {}
    tags: list[str] = []
    extracted_fact = ""
    should_auto_save = False
    should_require_approval = False
    should_export_to_training = False

    # ── 1. Explicit user memory ────────────────────────────────────────────
    for pattern in EXPLICIT_SAVE_TRIGGERS:
        if re.search(pattern, msg_raw, re.IGNORECASE):
            extracted_fact = re.sub(r"(?i)\b(remember|save this|keep this|lock this in|don'?t forget)\b\s*", "", msg_raw, count=1).strip().rstrip(".,!")
            return {
                "memory_type": "explicit_user_memory",
                "confidence": 0.95,
                "reason": f"Explicit save trigger matched: {pattern}",
                "should_auto_save": True,
                "should_require_approval": False,
                "should_export_to_training": False,
                "suggested_storage_path": "data/smart_memory/explicit_user_memory.jsonl",
                "extracted_fact": extracted_fact or msg_raw,
                "tags": ["explicit", "user_requested"],
            }

    # ── 2. Training candidate ──────────────────────────────────────────────
    for trigger in TRAINING_TRIGGERS:
        if trigger in msg_norm:
            extracted_fact = re.sub(r"(?i)(the correct answer|the right answer|the answer is|correction|corrected)\b\s*", "", msg_raw, count=1).strip().rstrip(".,!")
            return {
                "memory_type": "training_candidate_memory",
                "confidence": 0.90,
                "reason": f"Training trigger matched: {trigger}",
                "should_auto_save": True,
                "should_require_approval": False,
                "should_export_to_training": True,
                "suggested_storage_path": "data/smart_memory/training_candidate_memory.jsonl",
                "extracted_fact": extracted_fact or msg_raw,
                "tags": ["training_candidate", "v058_export_ready"],
            }

    # ── 3. Pending approval (uncertain/personal) ────────────────────────────
    is_uncertain = any(t in msg_norm for t in UNCERTAIN_TRIGGERS)
    is_personal = any(t in msg_norm for t in PERSONAL_SUBJECTS)
    if is_uncertain or is_personal:
        mem_type = "pending_approval_memory"
        reason_parts = []
        if is_uncertain:
            reason_parts.append("uncertain/speculative language")
        if is_personal:
            reason_parts.append("personal/subjective claim")
        return {
            "memory_type": mem_type,
            "confidence": 0.60 if is_uncertain else 0.70,
            "reason": "; ".join(reason_parts),
            "should_auto_save": False,
            "should_require_approval": True,
            "should_export_to_training": False,
            "suggested_storage_path": "data/smart_memory/pending_approval_memory.jsonl",
            "extracted_fact": msg_raw,
            "tags": reason_parts,
        }

    # ── 4. Auto project memory ─────────────────────────────────────────────
    project_keywords = [
        "v05", "v06", "passed", "failed", "checkpoint", "route", "router",
        "brain slot", "fine.tune", "training set", "promoted",
        "live route", "priority", "patch", "upgrade", "build plan",
        "architecture", "installed", "deployed",
    ]
    project_hit = any(kw in msg_norm for kw in project_keywords)
    is_followup = ctx.get("is_followup", False) or msg_norm in {
        "do that", "ok", "okay", "go", "continue", "next", "what next",
    }

    if project_hit and not is_followup:
        return {
            "memory_type": "auto_project_memory",
            "confidence": 0.85,
            "reason": "Contains project/build keywords",
            "should_auto_save": True,
            "should_require_approval": False,
            "should_export_to_training": False,
            "suggested_storage_path": "data/smart_memory/auto_project_memory.jsonl",
            "extracted_fact": msg_raw,
            "tags": ["project", "auto_capture"],
        }

    # ── 5. Temporary conversation context (default) ────────────────────────
    return {
        "memory_type": "temporary_conversation_context",
        "confidence": 0.95,
        "reason": "Default — normal conversation, no save trigger",
        "should_auto_save": False,
        "should_require_approval": False,
        "should_export_to_training": False,
        "suggested_storage_path": "data/smart_memory/temporary_conversation_context.jsonl",
        "extracted_fact": msg_raw,
        "tags": ["conversation", "temporary"],
    }
