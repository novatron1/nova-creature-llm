"""729 — Check Mock Speaker Test"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v729_mock_speaker_test import mock_speaker_test
    r = mock_speaker_test()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v729_mock_speaker_test")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v729_mock_speaker_test: " + str(e))
    raise SystemExit(1)
