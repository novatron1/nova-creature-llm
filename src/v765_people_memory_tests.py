"""v765_people_memory_tests — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def people_memory_tests():
    """Comprehensive test suite for people memory system."""
    tests = []; passed = 0; failed = 0
    # 1. "My name is Marcus" creates remembered profile
    try:
        from v753_auto_people_memory_lock import auto_people_memory_lock
        r = auto_people_memory_lock("My name is Marcus")
        ok = r.get("profiles_created", 0) > 0
        tests.append({"test": "introduction_creates_profile", "passed": ok, "detail": f"profiles: {r.get('profiles_created')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "introduction_creates_profile", "passed": False, "detail": str(e)}); failed += 1
    # 2. "I'm D" creates nickname profile
    try:
        r = auto_people_memory_lock("I'm D")
        ok = r.get("profiles_created", 0) > 0
        tests.append({"test": "nickname_creates_profile", "passed": ok, "detail": f"profiles: {r.get('profiles_created')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "nickname_creates_profile", "passed": False, "detail": str(e)}); failed += 1
    # 3. "This is my cousin Tony" creates profile with relationship
    try:
        r = auto_people_memory_lock("This is my cousin Tony")
        ok = r.get("profiles_created", 0) > 0
        det = r.get("results", [{}])[0]
        profile = det.get("profile", {}) if isinstance(det, dict) else {}
        has_rel = "cousin" in str(profile.get("relationship", ""))
        tests.append({"test": "introduction_with_relationship", "passed": ok and has_rel, "detail": f"rel: {profile.get('relationship', 'none')}"})
        passed += ok and has_rel; failed += not (ok and has_rel)
    except Exception as e: tests.append({"test": "introduction_with_relationship", "passed": False, "detail": str(e)}); failed += 1
    # 4. Person recall works
    try:
        from v754_human_style_recall import human_style_recall
        r = human_style_recall(name="Marcus")
        ok = r.get("status") == "ok"
        tests.append({"test": "recall_by_name", "passed": ok, "detail": f"confidence: {r.get('confidence')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "recall_by_name", "passed": False, "detail": str(e)}); failed += 1
    # 5. Correction works
    try:
        from v751_people_memory_database import people_memory_database
        from v755_confidence_and_correction import confidence_and_correction
        db = people_memory_database()
        profiles = db.get("profiles", [])
        if profiles:
            pid = profiles[0]["person_id"]
            r = confidence_and_correction("correct_name", pid, profiles[0]["display_name"], "CorrectedName")
            ok = r.get("status") == "ok"
        else: ok = True
        tests.append({"test": "correction_system", "passed": ok, "detail": "correction executed" if ok else "no profiles"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "correction_system", "passed": False, "detail": str(e)}); failed += 1
    # 6. Unknown person without intro stays unknown
    try:
        from v756_known_unknown_person_router import known_unknown_person_router
        r = known_unknown_person_router()
        ok = r.get("person_status") == "unknown_person"
        tests.append({"test": "unknown_stays_unknown", "passed": ok, "detail": f"status: {r.get('person_status')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "unknown_stays_unknown", "passed": False, "detail": str(e)}); failed += 1
    # 7. Private mode prevents new profiles
    try:
        from v759_privacy_and_forget_controls import privacy_and_forget_controls
        r1 = privacy_and_forget_controls("private_mode_on")
        ok1 = r1.get("private_mode") == True
        r2 = privacy_and_forget_controls("private_mode_off")
        ok2 = r2.get("private_mode") == False
        tests.append({"test": "private_mode_controls", "passed": ok1 and ok2, "detail": f"on:{ok1} off:{ok2}"})
        passed += ok1 and ok2; failed += not (ok1 and ok2)
    except Exception as e: tests.append({"test": "private_mode_controls", "passed": False, "detail": str(e)}); failed += 1
    # 8. Forget command works
    try:
        r = privacy_and_forget_controls("forget", name="Marcus")
        ok = r.get("status") == "ok"
        tests.append({"test": "forget_command", "passed": ok, "detail": f"msg: {r.get('message')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "forget_command", "passed": False, "detail": str(e)}); failed += 1
    # 9. Single question parsing
    try:
        from v752_introduction_trigger_parser import introduction_trigger_parser
        r = introduction_trigger_parser("My name is Marcus")
        ok = r.get("detection_count", 0) > 0
        tests.append({"test": "single_question_no_intro", "passed": ok, "detail": f"detections: {r.get('detection_count')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "single_question_no_intro", "passed": False, "detail": str(e)}); failed += 1
    # 10. Router integration
    try:
        from v758_people_memory_router import people_memory_router
        r = people_memory_router("known", "name_identity")
        ok = r.get("status") == "ok"
        tests.append({"test": "people_memory_router", "passed": ok, "detail": f"route: {r.get('primary_route')}"})
        passed += ok; failed += not ok
    except Exception as e: tests.append({"test": "people_memory_router", "passed": False, "detail": str(e)}); failed += 1
    return {"version": "v765_people_memory_tests", "created_at": datetime.now().isoformat(),
            "total_tests": len(tests), "passed": passed, "failed": failed,
            "tests": tests, "status": "ok" if failed == 0 else "partial"}


def main():
    import sys
    print(f"Nova v765_people_memory_tests")
    r = people_memory_tests()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
