"""748 — Sensory Body Layer: Mock Test Suite"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def mock_test_suite():
    """Comprehensive mock test suite for sensory body layer."""
    tests = []
    passed = 0
    failed = 0

    # Device discovery mock
    try:
        from v701_device_scanner import device_scanner
        r = device_scanner()
        ok = r.get("status") == "ok"
        tests.append({"test": "device_discovery_mock", "passed": ok, "detail": f"devices: cam={len(r.get('cameras',[]))} mic={len(r.get('microphones',[]))} spk={len(r.get('speakers',[]))}"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "device_discovery_mock", "passed": False, "detail": str(e)}); failed += 1

    # Permission denied behavior
    try:
        from v704_permission_gate import permission_gate, check_permission
        pg = permission_gate("camera", False)
        ok = check_permission("camera") == False
        tests.append({"test": "permission_denied", "passed": ok, "detail": "camera permission correctly denied"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "permission_denied", "passed": False, "detail": str(e)}); failed += 1

    # Permission granted behavior
    try:
        from v704_permission_gate import permission_gate, check_permission
        pg = permission_gate("camera", True)
        ok = check_permission("camera") == True
        tests.append({"test": "permission_granted", "passed": ok, "detail": "camera permission correctly granted"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "permission_granted", "passed": False, "detail": str(e)}); failed += 1

    # Mock face detection route
    try:
        from v713_face_detector import face_detector
        r = face_detector()
        ok = r.get("face_count", 0) > 0
        tests.append({"test": "mock_face_detection", "passed": ok, "detail": f"faces: {r.get('face_count')}"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "mock_face_detection", "passed": False, "detail": str(e)}); failed += 1

    # Mock hand tracking route
    try:
        from v718_hand_tracker import hand_tracker
        r = hand_tracker()
        ok = r.get("hand_count", 0) > 0
        tests.append({"test": "mock_hand_tracking", "passed": ok, "detail": f"hands: {r.get('hand_count')}"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "mock_hand_tracking", "passed": False, "detail": str(e)}); failed += 1

    # Mock audio transcript route
    try:
        from v724_speech_to_text_adapter import speech_to_text_adapter
        r = speech_to_text_adapter()
        ok = r.get("status") == "ok"
        tests.append({"test": "mock_audio_transcript", "passed": ok, "detail": "STT adapter exists"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "mock_audio_transcript", "passed": False, "detail": str(e)}); failed += 1

    # Mock speaker output route
    try:
        from v729_mock_speaker_test import mock_speaker_test
        r = mock_speaker_test()
        ok = r.get("test_passed") == True
        tests.append({"test": "mock_speaker_output", "passed": ok, "detail": "speaker test passed"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "mock_speaker_output", "passed": False, "detail": str(e)}); failed += 1

    # Mock screenshot route
    try:
        from v733_mock_screenshot_test import mock_screenshot_test
        r = mock_screenshot_test()
        ok = r.get("test_passed") == True
        tests.append({"test": "mock_screenshot", "passed": ok, "detail": "screenshot test passed"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "mock_screenshot", "passed": False, "detail": str(e)}); failed += 1

    # Sensory memory logging
    try:
        from v707_sensory_memory import sensory_memory
        from v706_sensory_event import sensory_event
        ev = sensory_event("camera", "face_detected", "test face", 0.95, "right_hemisphere", "granted")
        r = sensory_memory(ev)
        ok = r.get("status") == "ok" and r.get("stored") is not None
        tests.append({"test": "sensory_memory_logging", "passed": ok, "detail": "event stored"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "sensory_memory_logging", "passed": False, "detail": str(e)}); failed += 1

    # Multimodal router output
    try:
        from v708_multimodal_router import multimodal_router
        r = multimodal_router("camera", "face")
        ok = "right_hemisphere" in r.get("routes", [])
        tests.append({"test": "multimodal_router", "passed": ok, "detail": f"routes: {r.get('routes')}"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "multimodal_router", "passed": False, "detail": str(e)}); failed += 1

    return {"version": "v748_mock_test_suite", "created_at": datetime.now().isoformat(),
            "total_tests": len(tests), "passed": passed, "failed": failed,
            "tests": tests, "status": "ok" if failed == 0 else "partial"}


def main():
    print(f"Nova v748_mock_test_suite")
    r = mock_test_suite()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
