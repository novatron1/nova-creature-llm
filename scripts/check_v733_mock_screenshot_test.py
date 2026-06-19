"""733 — Check Mock Screenshot Test"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v733_mock_screenshot_test import mock_screenshot_test
    r = mock_screenshot_test()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v733_mock_screenshot_test")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v733_mock_screenshot_test: " + str(e))
    raise SystemExit(1)
