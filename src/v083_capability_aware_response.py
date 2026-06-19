"""v083 — Capability-Aware Response. Answers based on what is actually installed."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CAPABILITY_RULES = {
    "robot_movement": {"installed": False, "response": "I can plan robot commands and simulate them, but real robot movement is not active yet. Real hardware is not enabled, and the safety spine blocks physical movement."},
    "script_writing": {"installed": True, "response": "Yes, I can write and test scripts inside the sandbox at sandbox/generated_scripts/."},
    "app_building": {"installed": True, "response": "Yes, I can scaffold app projects in sandbox at sandbox/app_builder_projects/ using v080 App Builder Mode."},
    "local_cloud_sync": {"installed": False, "response": "I have a sync plan (v079), but I cannot directly access your local laptop. The plan lists what would need to be exported."},
    "robot_simulation": {"installed": True, "response": "Yes, I can simulate robot commands through v070 Robot Simulation Bridge. All results are simulated, no hardware is sent."},
    "reasoning": {"installed": True, "response": "Yes, I have v086 reasoning core for structured problem analysis."},
}

KNOWN_CAPABILITIES = {
    "move": "robot_movement", "real robot": "robot_movement", "physical": "robot_movement",
    "write scripts": "script_writing", "code": "script_writing",
    "build apps": "app_building", "scaffold": "app_building",
    "sync": "local_cloud_sync", "local": "local_cloud_sync",
    "simulate": "robot_simulation", "simulation": "robot_simulation",
    "reason": "reasoning", "think": "reasoning", "analyze": "reasoning",
}

def answer_with_capability_awareness(question: str, context: dict | None = None) -> dict[str, Any]:
    q = question.lower()
    for keyword, capability in KNOWN_CAPABILITIES.items():
        if keyword in q:
            info = CAPABILITY_RULES.get(capability, {})
            return {
                "version": "v083_capability_aware", "created_at": datetime.now().isoformat(),
                "question": question, "capability_queried": capability,
                "installed": info.get("installed", False),
                "answer": info.get("response", "That capability is not installed yet."),
                "sandbox_only": info.get("installed", False) and capability in ("script_writing", "app_building"),
            }
    return {
        "version": "v083_capability_aware", "created_at": datetime.now().isoformat(),
        "question": question, "capability_queried": "unknown",
        "installed": False,
        "answer": "I am not sure what capability you are asking about. Try asking about robot movement, script writing, app building, sync, simulation, or reasoning.",
    }

def main():
    print("Nova v083 -- Capability-Aware Response\n")
    tests = ["Can you move a robot?", "Can you write scripts?", "Can you build apps?", "Can you sync local and cloud?"]
    for t in tests:
        r = answer_with_capability_awareness(t)
        print(f"Q: {t}")
        print(f"  Cap: {r['capability_queried']}, Installed: {r['installed']}")
        print(f"  {r['answer'][:80]}...")
        print()
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
