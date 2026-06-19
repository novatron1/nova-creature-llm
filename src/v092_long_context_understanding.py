"""v092 — Long-Context Understanding. Summarizes project state from version notes."""
from __future__ import annotations
from datetime import datetime
from typing import Any

KNOWN_VERSIONS = {
    "v056": "Conversation Memory Loop",
    "v057": "Dictionary Memory Bridge",
    "v058": "Dictionary to Transformer Learning",
    "v059": "Live Router Promoted to v055 Fine-Tuned Brains",
    "v060": "Smart Memory Capture",
    "v061": "Smart Memory to Training Loop",
    "v062": "Multi-Source Growth Engine + Benchmark Gate",
    "v063": "Inner Voice + Dream Replay Learning",
    "v064": "Memory Law / Approval Constitution",
    "v065": "Skill Hands + Self-Test Nervous System",
    "v066": "Capability Self-Map",
}


def summarize_project_context(items: list[str], context: dict | None = None) -> dict[str, Any]:
    timeline = []
    completed = []
    failed = []
    blockers = []
    decisions = []

    for item in items:
        found = False
        for ver, desc in KNOWN_VERSIONS.items():
            if ver in item:
                timeline.append({"version": ver, "description": desc, "source": item[:80]})
                completed.append(ver)
                found = True
                break
        if not found and "robot" in item.lower() and "real" in item.lower():
            decisions.append(f"Robot real movement not enabled: {item[:80]}")
        elif not found and "fail" in item.lower():
            failed.append(item[:80])

    # Build current state
    current_state_parts = []
    if "v066" in str(items):
        current_state_parts.append("Capability self-map installed")
    if "v061" in str(items):
        current_state_parts.append("Learning loop closed")
    if "v059" in str(items):
        current_state_parts.append("Live router on v055 fine-tuned brains")

    # Robot decisions
    robot_decisions = [d for d in decisions if "robot" in d.lower()]
    if not robot_decisions:
        robot_decisions = ["Real robot movement is not enabled (by default)"]

    return {
        "version": "v092_long_context_understanding", "created_at": datetime.now().isoformat(),
        "timeline": timeline,
        "current_state": "; ".join(current_state_parts) or "Analyzing state...",
        "active_goal": "v086-v095 Intelligence Stack",
        "completed_versions": completed,
        "failed_versions": failed,
        "open_blockers": blockers,
        "important_decisions": robot_decisions + decisions,
        "next_steps": ["Build v086 reasoning core", "Build v087 planner", "Build v088 decomposer",
                       "Build v089 evidence checker", "Build v090 self-correction loop",
                       "Build v091 concept builder", "Build v092 long-context understanding",
                       "Build v093 strategy brain", "Build v094 debate brain",
                       "Build v095 intelligence benchmarks"],
        "contradictions": [f"Robot real hardware not enabled but {'real movement' in str(items) if items else False}"],
        "missing_information": [],
    }


def main() -> int:
    print("Nova v092 -- Long-Context Understanding\n")
    items = [
        "v056 conversation memory loop installed",
        "v057 dictionary memory bridge installed",
        "v059 live router promoted to v055 fine-tuned brains",
        "v060 smart memory capture installed",
        "v061 learning loop closed",
        "v062 benchmark gate passing",
        "v063 dream replay installed",
        "v064 memory law installed",
        "v065 skill hands installed",
        "v066 capability self-map installed",
        "Real robot movement is not active",
    ]
    r = summarize_project_context(items)
    print(f"Timeline entries: {len(r['timeline'])}")
    print(f"Completed: {', '.join(r['completed_versions'][-3:])}...")
    print(f"State: {r['current_state'][:80]}")
    print(f"Decisions: {len(r['important_decisions'])}")
    print(f"Next steps: {len(r['next_steps'])}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
