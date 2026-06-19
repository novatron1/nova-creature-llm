"""v778_question_generator — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def question_generator(lesson=None):
    """Generate test questions for a lesson."""
    if not lesson:
        return {"version": "v778_question_generator", "questions": [], "status": "ok"}
    claim = lesson.get("claim", "")
    topic = lesson.get("topic", "general")
    questions = [
        {"type": "direct_recall", "question": f"What is the claim about {topic}?", "expected": claim, "difficulty": 0.5},
        {"type": "reverse", "question": f"Can you explain {topic} in your own words?", "expected": f"A paraphrase of: {claim}", "difficulty": 0.6},
        {"type": "example_use", "question": f"Give an example related to: {claim}", "expected": "A relevant example", "difficulty": 0.7},
        {"type": "mistake_trap", "question": f"Is it true that the opposite of '{claim}' is correct?", "expected": "No", "difficulty": 0.8},
    ]
    return {"version": "v778_question_generator", "lesson_id": lesson.get("lesson_id"),
            "questions": questions, "question_count": len(questions), "status": "ok"}


def main():
    print(f"Nova v778_question_generator")
    r = question_generator()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
