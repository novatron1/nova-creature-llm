from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CONSTITUTION = {
    "version": "v064_memory_constitution",
    "created_at": datetime.now().isoformat(),
    "laws": [
        {
            "id": "law_001",
            "title": "Explicit user memory is auto-approved",
            "rule": "Any message containing 'remember', 'save this', 'keep this', 'lock this in', or 'don't forget' is auto-approved and may be exported to dictionary memory.",
            "memory_type": "explicit_user_memory",
            "auto_approve": True,
            "can_train": True,
            "requires_approval": False,
        },
        {
            "id": "law_002",
            "title": "Training candidates are auto-approved",
            "rule": "Any message containing 'the correct answer', 'the right answer', 'correction', 'corrected', or 'the truth is' is auto-approved and may be exported to training sets.",
            "memory_type": "training_candidate_memory",
            "auto_approve": True,
            "can_train": True,
            "requires_approval": False,
        },
        {
            "id": "law_003",
            "title": "Project build facts are auto-captured",
            "rule": "Messages containing version, patch, checkpoint, route, or benchmark keywords are stored as project memory. They are auto-approved but not automatically exported to training.",
            "memory_type": "auto_project_memory",
            "auto_approve": True,
            "can_train": False,
            "requires_approval": False,
        },
        {
            "id": "law_004",
            "title": "Uncertain or speculative claims require approval",
            "rule": "Messages containing 'maybe', 'perhaps', 'could be', 'might be', 'not sure', 'i think', 'possibly', 'guess' are flagged as uncertain and require explicit approval before training.",
            "memory_type": "pending_approval_memory",
            "auto_approve": False,
            "can_train": False,
            "requires_approval": True,
        },
        {
            "id": "law_005",
            "title": "Personal or subjective claims require approval",
            "rule": "Messages containing 'my favorite', 'my name is', 'i like', 'i dislike', 'i feel', 'my opinion' are personal claims and require approval before training.",
            "memory_type": "pending_approval_memory",
            "auto_approve": False,
            "can_train": False,
            "requires_approval": True,
        },
        {
            "id": "law_006",
            "title": "Temporary conversation context is not stored long-term",
            "rule": "Follow-up words ('do that', 'ok', 'go', 'next') and normal conversational turns are temporary. They are logged for context but never exported to training.",
            "memory_type": "temporary_conversation_context",
            "auto_approve": False,
            "can_train": False,
            "requires_approval": False,
        },
        {
            "id": "law_007",
            "title": "Rejected memory is never trained",
            "rule": "Any memory item with status 'rejected' must be excluded from all export, training, and dictionary update operations.",
            "memory_type": "any",
            "auto_approve": False,
            "can_train": False,
            "requires_approval": False,
        },
        {
            "id": "law_008",
            "title": "Benchmark gate must pass before promotion",
            "rule": "No new brain organ, growth stream, or training cycle may be promoted unless v062 benchmark gate passes with 100% on the standard suite.",
            "memory_type": "system",
            "auto_approve": True,
            "can_train": False,
            "requires_approval": False,
        },
        {
            "id": "law_009",
            "title": "Duplicate detection prevents double-training",
            "rule": "Before any memory item is exported to training, normalized text matching must confirm it is not already present in the target training set.",
            "memory_type": "system",
            "auto_approve": True,
            "can_train": False,
            "requires_approval": False,
        },
        {
            "id": "law_010",
            "title": "Backup must precede destructive writes",
            "rule": "Before overwriting dictionary memory or training sets, a timestamped backup of the previous state must be saved.",
            "memory_type": "system",
            "auto_approve": True,
            "can_train": False,
            "requires_approval": False,
        },
    ],
}


def get_constitution() -> dict[str, Any]:
    return CONSTITUTION


def check_law(memory_type: str, status: str | None = None) -> list[dict[str, Any]]:
    """Check which laws apply to a given memory type/status."""
    applicable = []
    for law in CONSTITUTION["laws"]:
        if law["memory_type"] in (memory_type, "any", "system"):
            applicable.append(law)
    return applicable


def can_train(memory_type: str, status: str | None = None) -> bool:
    """Check if a memory type is trainable under the constitution."""
    if status == "rejected":
        return False
    for law in CONSTITUTION["laws"]:
        if law["memory_type"] == memory_type and not law["can_train"]:
            return False
    # Law 007 applies globally only when status is rejected
    return True


def requires_approval(memory_type: str) -> bool:
    """Check if a memory type requires approval."""
    for law in CONSTITUTION["laws"]:
        if law["memory_type"] == memory_type and law.get("requires_approval"):
            return True
    return False


def auto_approve(memory_type: str) -> bool:
    """Check if a memory type is auto-approved."""
    for law in CONSTITUTION["laws"]:
        if law["memory_type"] == memory_type and law.get("auto_approve"):
            return True
    return False


def evaluate_pending_items() -> dict[str, Any]:
    """Evaluate all pending items against the constitution."""
    from v060_memory_manager import list_pending
    pending = list_pending()
    evaluations = []
    for item in pending:
        mem_type = item.get("memory_type", "pending_approval_memory")
        laws = check_law(mem_type)
        can_approve = auto_approve(mem_type)

        evaluations.append({
            "id": item.get("id"),
            "message": (item.get("extracted_fact") or item.get("message", ""))[:60],
            "memory_type": mem_type,
            "can_auto_approve": can_approve,
            "requires_approval": requires_approval(mem_type),
            "can_train": can_train(mem_type, item.get("status")),
        })

    return {
        "version": "v064_memory_constitution",
        "evaluated_at": datetime.now().isoformat(),
        "pending_count": len(pending),
        "evaluations": evaluations,
        "constitution_laws": len(CONSTITUTION["laws"]),
    }


def main() -> int:
    print("Nova Creature v064 — Memory Law / Approval Constitution\n")
    print(f"Laws: {len(CONSTITUTION['laws'])}\n")
    for law in CONSTITUTION["laws"]:
        print(f"  {law['id']}: {law['title']}")
        print(f"      auto_approve={law['auto_approve']}, can_train={law['can_train']}, requires_approval={law['requires_approval']}")
        print(f"      {law['rule'][:80]}...")
        print()

    eval_result = evaluate_pending_items()
    print(f"Pending items evaluated: {eval_result['pending_count']}")
    for ev in eval_result["evaluations"]:
        print(f"  {ev['id']}: auto_approve={ev['can_auto_approve']}, train={ev['can_train']}")

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "v064_memory_constitution_report.json").write_text(json.dumps(eval_result, indent=2))
    print(f"\nReport: reports/v064_memory_constitution_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
