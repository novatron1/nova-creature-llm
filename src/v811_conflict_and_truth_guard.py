"""v811_conflict_and_truth_guard — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def conflict_and_truth_guard(claim="", existing_memories=None):
    """Route conflicting/uncertain claims through critic before locking."""
    if not claim:
        return {"version": "v811_conflict_and_truth_guard", "status": "no_input"}
    from v788_conflict_detection import conflict_detection
    existing = existing_memories or []
    conflict = conflict_detection(claim, existing)
    verdict = "safe_to_lock" if conflict.get("conflict_count", 0) == 0 else "needs_review"
    route = "critic_conscience_transformer" if verdict == "needs_review" else "memory_transformer"
    return {"version": "v811_conflict_and_truth_guard", "claim": claim[:200],
            "verdict": verdict, "conflicts": conflict.get("conflicts", []),
            "route": route, "status": "ok"}


def main():
    print(f"Nova v811_conflict_and_truth_guard")
    r = conflict_and_truth_guard()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
