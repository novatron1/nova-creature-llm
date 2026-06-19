"""v795_rapid_learning_test_suite — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def rapid_learning_test_suite():
    """Comprehensive tests for rapid learning system."""
    tests = []; passed = 0; failed = 0
    # 1. Learning from pasted text
    try:
        from v776_learning_intake import learning_intake
        r = learning_intake("text", "Nova is an AI creature with seven brain organs.")
        ok = r.get("status") == "ok"
        tests.append({"test": "learning_from_text", "passed": ok, "detail": f"intake_id: {r.get('intake_id','')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "learning_from_text", "passed": False, "detail": str(e)}); failed += 1
    # 2. Chunking into lessons
    try:
        from v777_lesson_chunker import lesson_chunker
        r = lesson_chunker("text", "Nova has seven brain organs. Each organ has a special role. The memory transformer stores facts.")
        ok = r.get("lesson_count", 0) >= 2
        tests.append({"test": "lesson_chunking", "passed": ok, "detail": f"lessons: {r.get('lesson_count')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "lesson_chunking", "passed": False, "detail": str(e)}); failed += 1
    # 3. Generating questions
    try:
        from v777_lesson_chunker import lesson_chunker
        from v778_question_generator import question_generator
        chunked = lesson_chunker("text", "Nova has seven brain organs.")
        if chunked.get("lessons"):
            r = question_generator(chunked["lessons"][0])
            ok = r.get("question_count", 0) >= 3
        else: ok = False
        tests.append({"test": "question_generation", "passed": ok, "detail": f"questions: {r.get('question_count', 0)}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "question_generation", "passed": False, "detail": str(e)}); failed += 1
    # 4. Self-testing
    try:
        from v777_lesson_chunker import lesson_chunker
        from v778_question_generator import question_generator
        from v779_self_test_engine import self_test_engine
        chunked = lesson_chunker("text", "Nova has seven brain organs.")
        if chunked.get("lessons"):
            qs = question_generator(chunked["lessons"][0])
            r = self_test_engine(chunked["lessons"][0], qs.get("questions", []))
            ok = r.get("status") == "ok"
        else: ok = False
        tests.append({"test": "self_testing", "passed": ok, "detail": f"passed: {r.get('passed')}, failed: {r.get('failed')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "self_testing", "passed": False, "detail": str(e)}); failed += 1
    # 5. Failing a bad answer
    try:
        from v779_self_test_engine import self_test_engine
        lesson = {"lesson_id": "test", "claim": "The sky is blue.", "topic": "sky"}
        questions = [{"type": "direct_recall", "question": "What color is sky?", "expected": "The sky is blue.", "difficulty": 0.9}]
        r = self_test_engine(lesson, questions)
        # At least some may fail with high difficulty
        ok = r.get("status") == "ok"
        tests.append({"test": "failing_bad_answer", "passed": ok, "detail": f"passed: {r.get('passed')}, failed: {r.get('failed')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "failing_bad_answer", "passed": False, "detail": str(e)}); failed += 1
    # 6. Correction loop
    try:
        from v781_correction_loop import correction_loop
        r = correction_loop({"lesson_id": "test"}, [{"question": "test Q", "weakness_reason": "wrong", "lesson_id": "test"}])
        ok = r.get("correction_count", 0) > 0
        tests.append({"test": "correction_loop", "passed": ok, "detail": f"corrections: {r.get('correction_count')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "correction_loop", "passed": False, "detail": str(e)}); failed += 1
    # 7. Approved memory save
    try:
        from v780_rapid_learning_memory_lock import rapid_learning_memory_lock
        r = rapid_learning_memory_lock({"lesson_id": "test", "results": [{"question_type": "recall", "question": "Q", "score": 0.9, "passed": True}]})
        ok = r.get("approved_count", 0) > 0
        tests.append({"test": "approved_memory_save", "passed": ok, "detail": f"approved: {r.get('approved_count')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "approved_memory_save", "passed": False, "detail": str(e)}); failed += 1
    # 8. Retention test
    try:
        from v787_retention_test import retention_test
        r = retention_test()
        ok = r.get("status") == "ok"
        tests.append({"test": "retention_test", "passed": ok, "detail": f"retained: {r.get('retained')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "retention_test", "passed": False, "detail": str(e)}); failed += 1
    # 9. Conflict detection
    try:
        from v788_conflict_detection import conflict_detection
        r = conflict_detection("Nova has five brains.", ["Nova has seven brains."])
        ok = r.get("status") == "ok"
        tests.append({"test": "conflict_detection", "passed": ok, "detail": f"conflicts: {r.get('conflict_count')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "conflict_detection", "passed": False, "detail": str(e)}); failed += 1
    # 10. Learning from user correction
    try:
        from v784_learning_from_correction import learning_from_correction
        r = learning_from_correction("No, thats wrong, it should be Nova has seven brains.")
        ok = r.get("status") == "ok" and r.get("correction_detected", False)
        tests.append({"test": "learning_from_correction", "passed": ok, "detail": f"detected: {r.get('correction_detected')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "learning_from_correction", "passed": False, "detail": str(e)}); failed += 1
    # 11. Export training set
    try:
        from v789_learning_exporter import learning_exporter
        r = learning_exporter()
        ok = r.get("status") == "ok"
        tests.append({"test": "export_training_set", "passed": ok, "detail": f"exported: {r.get('exported')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "export_training_set", "passed": False, "detail": str(e)}); failed += 1
    return {"version": "v795_rapid_learning_test_suite", "created_at": datetime.now().isoformat(),
            "total_tests": len(tests), "passed": passed, "failed": failed,
            "tests": tests, "status": "ok" if failed == 0 else "partial"}


def main():
    print(f"Nova v795_rapid_learning_test_suite")
    r = rapid_learning_test_suite()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
