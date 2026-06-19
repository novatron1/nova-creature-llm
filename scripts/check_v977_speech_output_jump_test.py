"""v977_speech_output_jump_test — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v977_speech_output_jump_test import speech_output_jump_test
    r = speech_output_jump_test()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v977_speech_output_jump_test")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v977_speech_output_jump_test: " + str(e))
    raise SystemExit(1)
