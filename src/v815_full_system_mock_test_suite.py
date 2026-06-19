"""v815_full_system_mock_test_suite — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def full_system_mock_test_suite():
    """Comprehensive system integration tests."""
    tests = []; passed = 0; failed = 0
    # 1. Text input routing
    try:
        from v809_master_input_router import master_input_router
        r = master_input_router("Hello, how are you?", "plain_text")
        ok = r.get("status") == "ok"
        tests.append({"test": "text_input_routing", "passed": ok, "detail": f"type: {r.get('input_type')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "text_input_routing", "passed": False, "detail": str(e)}); failed += 1
    # 2. Introduction to people memory
    try:
        from v805_people_learning_bridge import people_learning_bridge
        r = people_learning_bridge("My name is Test User")
        ok = r.get("profiles_created", 0) > 0
        tests.append({"test": "intro_to_people_memory", "passed": ok, "detail": f"profiles: {r.get('profiles_created')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "intro_to_people_memory", "passed": False, "detail": str(e)}); failed += 1
    # 3. Teaching to rapid learning
    try:
        from v776_learning_intake import learning_intake
        r = learning_intake("text", "Test teaching content.")
        ok = r.get("status") == "ok"
        tests.append({"test": "teaching_to_rapid_learning", "passed": ok, "detail": f"id: {r.get('intake_id','')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "teaching_to_rapid_learning", "passed": False, "detail": str(e)}); failed += 1
    # 4. Permission denial
    try:
        from v803_master_permission_bridge import master_permission_bridge
        from v704_permission_gate import permission_gate
        permission_gate("camera", False)
        r = master_permission_bridge("camera", "check")
        ok = r.get("allowed") == False
        tests.append({"test": "permission_denial", "passed": ok, "detail": f"allowed: {r.get('allowed')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "permission_denial", "passed": False, "detail": str(e)}); failed += 1
    # 5. Permission approval
    try:
        from v704_permission_gate import permission_gate
        permission_gate("camera", True)
        r = master_permission_bridge("camera", "check")
        ok = r.get("allowed") == True
        tests.append({"test": "permission_approval", "passed": ok, "detail": f"allowed: {r.get('allowed')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "permission_approval", "passed": False, "detail": str(e)}); failed += 1
    # 6. Brain role routing
    try:
        from v807_brain_router_integration import brain_router_integration
        r = brain_router_integration("math", "What is 12 times 12?")
        ok = r.get("primary_route") == "left_hemisphere"
        tests.append({"test": "brain_role_routing", "passed": ok, "detail": f"route: {r.get('primary_route')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "brain_role_routing", "passed": False, "detail": str(e)}); failed += 1
    # 7. Output routing
    try:
        from v810_master_output_router import master_output_router
        r = master_output_router("Test output", "spoken_answer")
        ok = r.get("spoken") == True
        tests.append({"test": "output_routing", "passed": ok, "detail": f"spoken: {r.get('spoken')}, route: {r.get('route')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "output_routing", "passed": False, "detail": str(e)}); failed += 1
    # 8. Full loop demo
    try:
        from v813_full_loop_demo_script import full_loop_demo_script
        r = full_loop_demo_script()
        ok = r.get("steps_passed", 0) >= 5
        tests.append({"test": "full_loop_simulation", "passed": ok, "detail": f"passed: {r.get('steps_passed')}/{r.get('total_steps')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "full_loop_simulation", "passed": False, "detail": str(e)}); failed += 1
    # 9. Event bus
    try:
        from v802_unified_event_bus import unified_event_bus
        r = unified_event_bus("test", {"msg": "test event"})
        ok = r.get("status") == "ok"
        tests.append({"test": "event_bus", "passed": ok, "detail": f"event: {r.get('event',{}).get('event_id','')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "event_bus", "passed": False, "detail": str(e)}); failed += 1
    # 10. Memory bridge
    try:
        from v804_unified_memory_bridge import unified_memory_bridge
        r = unified_memory_bridge("test", {"confidence": 0.9, "subsystem": "integration_test", "route": "memory_transformer", "status": "test"})
        ok = r.get("stored") == True
        tests.append({"test": "memory_bridge", "passed": ok, "detail": f"stored: {r.get('stored')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "memory_bridge", "passed": False, "detail": str(e)}); failed += 1
    # 11. Conflict guard
    try:
        from v811_conflict_and_truth_guard import conflict_and_truth_guard
        r = conflict_and_truth_guard("Nova has five brains.", ["Nova has seven brains."])
        ok = r.get("verdict") == "needs_review"
        tests.append({"test": "conflict_guard", "passed": ok, "detail": f"verdict: {r.get('verdict')}, route: {r.get('route')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "conflict_guard", "passed": False, "detail": str(e)}); failed += 1
    # 12. Auto test builder
    try:
        from v812_auto_test_builder import auto_test_builder
        r = auto_test_builder("lesson", {"topic": "integration"})
        ok = r.get("count", 0) > 0
        tests.append({"test": "auto_test_builder", "passed": ok, "detail": f"tests: {r.get('count')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "auto_test_builder", "passed": False, "detail": str(e)}); failed += 1
    return {"version": "v815_full_system_mock_test_suite", "created_at": datetime.now().isoformat(),
            "total_tests": len(tests), "passed": passed, "failed": failed,
            "tests": tests, "status": "ok" if failed == 0 else "partial"}


def main():
    print(f"Nova v815_full_system_mock_test_suite")
    r = full_system_mock_test_suite()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
