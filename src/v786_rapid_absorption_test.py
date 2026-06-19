"""v786_rapid_absorption_test — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def rapid_absorption_test(teaching_text=""):
    """Receive new teaching, learn it, and answer questions in same session."""
    if not teaching_text:
        teaching_text = "Nova is an AI creature with seven brain organs: left hemisphere, right hemisphere, memory transformer, planner transformer, critic conscience, dream simulation, and speech output."
    from v777_lesson_chunker import lesson_chunker
    from v778_question_generator import question_generator
    from v779_self_test_engine import self_test_engine
    from v780_rapid_learning_memory_lock import rapid_learning_memory_lock
    chunked = lesson_chunker("text", teaching_text)
    all_passed = True
    lessons_learned = 0
    for lesson in chunked.get("lessons", []):
        questions = question_generator(lesson)
        test = self_test_engine(lesson, questions.get("questions", []))
        lock = rapid_learning_memory_lock(test)
        for r in test.get("results", []):
            if not r.get("passed", False):
                all_passed = False
        if test.get("passed", 0) > 0:
            lessons_learned += 1
    return {"version": "v786_rapid_absorption_test", "teaching_length": len(teaching_text),
            "lessons_chunked": len(chunked.get("lessons", [])),
            "lessons_learned": lessons_learned,
            "all_passed": all_passed, "status": "ok"}


def main():
    print(f"Nova v786_rapid_absorption_test")
    r = rapid_absorption_test()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
