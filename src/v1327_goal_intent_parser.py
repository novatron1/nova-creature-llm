"""vv1327_goal_intent_parser — Autonomous Skill Use + Permissioned Will Controller"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def goal_intent_parser():
    """Parse user goals into task types: learn, code, draw, animate, make video timeline, remember person, answer science, run benchmark, test system, display face, use sensor, package/export, unknown"""
    task_types = {
        "learn": ["teach", "learn", "train", "study", "lesson", "remember this"],
        "code": ["code", "fix", "debug", "patch", "program", "refactor", "build app"],
        "draw": ["draw", "paint", "sketch", "create art", "picture", "svg", "canvas"],
        "animate": ["animate", "animation", "motion", "loop", "sprite"],
        "make_video": ["video", "timeline", "film", "render"],
        "remember_person": ["hi my name is", "i am", "remember me", "introduce", "meet"],
        "answer_science": ["physics", "chemistry", "biology", "science", "what is", "how does"],
        "run_benchmark": ["benchmark", "test yourself", "evaluate", "score", "assess"],
        "test_system": ["test", "check", "verify", "validate", "run tests"],
        "display_face": ["show face", "face", "display", "look at me", "wake up"],
        "use_sensor": ["camera", "mic", "speaker", "see", "hear", "listen", "watch"],
        "package_export": ["package", "export", "zip", "download", "release"],
        "unknown": [],
    }
    examples = []
    for task, triggers in task_types.items():
        if triggers:
            examples.append({"task": task, "triggers": triggers[:3]})
    return {"version": "v1327_goal_intent_parser", "created_at": datetime.now().isoformat(),
            "module": "Parse user goals into task types: learn, code, draw, animate, make video timeline, remember person, answer science, run benchmark, test system, display face, use sensor, package/export, unknown", "task_types": list(task_types.keys()),
            "detection_examples": examples, "status": "ok"}


def main():
    print(f"Nova v1327_goal_intent_parser")
    r = goal_intent_parser()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
