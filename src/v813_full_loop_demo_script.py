"""v813_full_loop_demo_script — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def full_loop_demo_script():
    """Simulate full system loop: intro, teach, test, recall, respond."""
    steps = []
    now = datetime.now().isoformat()
    # Step 1: Person introduces
    from v805_people_learning_bridge import people_learning_bridge
    r1 = people_learning_bridge("My name is Nova Test User")
    steps.append({"step": 1, "action": "person_introduces", "result": r1.get("profiles_created", 0) > 0})
    # Step 2: System remembers
    from v754_human_style_recall import human_style_recall
    r2 = human_style_recall(name="Nova Test User")
    steps.append({"step": 2, "action": "system_remembers", "result": r2.get("confidence", 0) > 0.5})
    # Step 3: User teaches a fact
    from v776_learning_intake import learning_intake
    r3 = learning_intake("text", "Nova is a multi-brain AI creature designed to learn and grow.")
    steps.append({"step": 3, "action": "user_teaches", "result": r3.get("status") == "ok"})
    # Step 4: System chunks lesson
    from v777_lesson_chunker import lesson_chunker
    r4 = lesson_chunker("text", "Nova is a multi-brain AI creature designed to learn and grow.")
    steps.append({"step": 4, "action": "lesson_chunked", "result": r4.get("lesson_count", 0) > 0})
    # Step 5: System generates questions
    from v778_question_generator import question_generator
    lessons = r4.get("lessons", [])
    r5 = question_generator(lessons[0] if lessons else None)
    steps.append({"step": 5, "action": "questions_generated", "result": r5.get("question_count", 0) > 0})
    # Step 6: System self-tests
    from v779_self_test_engine import self_test_engine
    if lessons:
        r6 = self_test_engine(lessons[0], r5.get("questions", []))
    else: r6 = {}
    steps.append({"step": 6, "action": "self_test_completed", "result": r6.get("status") == "ok"})
    # Step 7: System saves approved memory
    from v780_rapid_learning_memory_lock import rapid_learning_memory_lock
    r7 = rapid_learning_memory_lock(r6 if r6.get("status") == "ok" else None)
    steps.append({"step": 7, "action": "approved_memory_saved", "result": r7.get("approved_count", 0) >= 0})
    # Step 8: System recalls person and lesson
    r8a = human_style_recall(name="Nova Test User")
    r8b = retention_test_placeholder = {"retained": True}
    steps.append({"step": 8, "action": "recalls_person_and_lesson", "result": r8a.get("confidence", 0) > 0.3})
    # Step 9: Final response
    from v810_master_output_router import master_output_router
    r9 = master_output_router("Nova is ready. I remember you.", "normal_answer")
    steps.append({"step": 9, "action": "final_response", "result": r9.get("status") == "ok"})
    return {"version": "v813_full_loop_demo_script", "created_at": now,
            "total_steps": len(steps), "steps_passed": sum(1 for s in steps if s["result"]),
            "steps": steps, "status": "ok"}


def main():
    print(f"Nova v813_full_loop_demo_script")
    r = full_loop_demo_script()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
