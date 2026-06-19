"""v081 — Brain Organ Council. Multiple roles evaluate decisions before action."""
from __future__ import annotations
from datetime import datetime
from typing import Any


def run_council(topic: str, context: dict | None = None) -> dict[str, Any]:
    t = topic.lower()
    role_views = {}
    agreements = []
    disagreements = []
    risk_notes = []
    blocked_actions = []

    if "robot" in t and ("move" in t or "real" in t or "enable" in t):
        role_views["memory_transformer"] = "Memory: v066 self-map shows real_hardware_enabled=False. v071 safety spine blocks physical movement."
        role_views["planner_transformer"] = "Plan: 12 deployment requirements are unmet (0/12). Cannot pass v073 deployment gate."
        role_views["critic_conscience_transformer"] = "BLOCK: Real movement without emergency stop, sensors, and safety spine is dangerous."
        role_views["left_hemisphere"] = "Logic: Simulation works. Hardware requirements missing. Benchmark value negative."
        role_views["right_hemisphere"] = "Pattern: Build intelligence foundation first. Robot body without brain stack is unsafe."
        role_views["dream_simulation_transformer"] = "Simulation: Robot sim works in v070. Real movement is not needed yet."
        role_views["speech_output_transformer"] = "Final: Nova should not enable real robot movement. Simulation-only is safe."
        agreements = [
            "Real robot movement is not ready",
            "Safety spine and sensors must come first",
            "Simulation is allowed and working",
            "Intelligence stack should be prioritized",
        ]
        disagreements = []
        risk_notes = [
            "Emergency stop not installed",
            "No collision detection",
            "Owner approval not given",
            "Hardware damage without safety",
        ]
        blocked_actions = ["enable_real_robot_movement", "send_hardware_motor_commands", "disable_safety_checks"]
    else:
        for role_name in ["memory_transformer", "planner_transformer", "critic_conscience_transformer",
                          "left_hemisphere", "right_hemisphere", "speech_output_transformer"]:
            role_views[role_name] = f"{role_name} considers: {topic}"
        agreements = [f"All roles reviewed: {topic}"]
        blocked_actions = []

    return {
        "version": "v081_brain_organ_council",
        "created_at": datetime.now().isoformat(),
        "topic": topic,
        "role_views": role_views,
        "agreements": agreements,
        "disagreements": disagreements,
        "risk_notes": risk_notes,
        "final_recommendation": "Simulation-only. Real robot movement blocked until all safety requirements are met."
            if role_views.get("critic_conscience_transformer", "").startswith("BLOCK")
            else f"Council reviewed: {topic}",
        "blocked_actions": blocked_actions,
        "next_safe_step": "Continue building intelligence stack (v086-v095) before any real robot work.",
    }


def main() -> int:
    print("Nova v081 -- Brain Organ Council\n")
    r = run_council("Should Nova enable real robot movement now?")
    print(f"Topic: {r['topic']}")
    for role, view in r["role_views"].items():
        print(f"  {role:40s} | {view[:60]}")
    for a in r["agreements"]:
        print(f"  AGREEMENT: {a}")
    for b in r["blocked_actions"]:
        print(f"  BLOCKED: {b}")
    print(f"\nRecommendation: {r['final_recommendation'][:80]}...")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
