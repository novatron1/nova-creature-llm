"""v064 — Approval Constitution

Rules for auto-save vs approval-required vs never-train classification.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

APPROVAL_RULES = {
    "auto_save_allowed": {
        "description": "Auto-saved without approval",
        "types": [
            "auto_project_memory",
            "explicit_user_memory",
            "training_candidate_memory",
        ],
        "rule": "Project/build facts, explicit user saves, and training candidates are auto-saved.",
        "needs_approval": False,
        "can_train": True,
        "can_export_dictionary": True,
    },
    "approval_required": {
        "description": "Requires owner approval before storage or training",
        "types": [
            "pending_approval_memory",
        ],
        "rule": "Personal facts, identity rules, owner preferences, long-term rules, uncertain claims, dream-generated lessons, and robot action rules require approval.",
        "needs_approval": True,
        "can_train": False,
        "can_export_dictionary": False,
    },
    "never_train": {
        "description": "Never stored or trained",
        "types": [
            "temporary_conversation_context",
            "rejected",
        ],
        "rule": "Temporary context, rejected memory, unapproved pending memory, guesses, emotional one-off claims, hallucinated dream lessons, and unsafe robot movement commands are never trained.",
        "needs_approval": False,
        "can_train": False,
        "can_export_dictionary": False,
    },
}


def get_approval_rule(memory_type: str) -> dict[str, Any] | None:
    """Get the approval rule for a given memory type."""
    for rule_name, rule in APPROVAL_RULES.items():
        if memory_type in rule["types"]:
            return {**rule, "rule_name": rule_name}
    return None


def needs_approval(memory_type: str) -> bool:
    """Check if a memory type requires approval."""
    rule = get_approval_rule(memory_type)
    return rule["needs_approval"] if rule else True


def can_train(memory_type: str, status: str | None = None) -> bool:
    """Check if a memory type can be trained."""
    if status == "rejected":
        return False
    rule = get_approval_rule(memory_type)
    return rule["can_train"] if rule else False


def can_export_dictionary(memory_type: str, status: str | None = None) -> bool:
    """Check if a memory type can be exported to dictionary."""
    if status == "rejected":
        return False
    rule = get_approval_rule(memory_type)
    return rule["can_export_dictionary"] if rule else False


def check_constitution() -> dict[str, Any]:
    """Return the full constitution report."""
    return {
        "version": "v064_approval_constitution",
        "created_at": datetime.now().isoformat(),
        "rules": APPROVAL_RULES,
        "memory_types_tested": {
            "auto_project_memory": {
                "needs_approval": needs_approval("auto_project_memory"),
                "can_train": can_train("auto_project_memory"),
            },
            "explicit_user_memory": {
                "needs_approval": needs_approval("explicit_user_memory"),
                "can_train": can_train("explicit_user_memory"),
            },
            "training_candidate_memory": {
                "needs_approval": needs_approval("training_candidate_memory"),
                "can_train": can_train("training_candidate_memory"),
            },
            "pending_approval_memory": {
                "needs_approval": needs_approval("pending_approval_memory"),
                "can_train": can_train("pending_approval_memory"),
            },
            "temporary_conversation_context": {
                "needs_approval": needs_approval("temporary_conversation_context"),
                "can_train": can_train("temporary_conversation_context"),
            },
            "rejected": {
                "needs_approval": needs_approval("rejected"),
                "can_train": can_train("rejected"),
            },
        },
    }


def main() -> int:
    report = check_constitution()
    print("Nova Creature v064 — Approval Constitution\n")
    for rule_name, rule in APPROVAL_RULES.items():
        print(f"  {rule_name}:")
        print(f"     {rule['description']}")
        print(f"     Types: {', '.join(rule['types'])}")
        print(f"     Needs approval: {rule['needs_approval']}")
        print(f"     Can train: {rule['can_train']}")
        print()

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "v064_approval_constitution_report.json").write_text(
        json.dumps(report, indent=2))
    print("Report: reports/v064_approval_constitution_report.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
