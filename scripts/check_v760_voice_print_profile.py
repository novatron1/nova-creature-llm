"""v760_voice_print_profile — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v760_voice_print_profile import voice_print_profile
    r = voice_print_profile()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v760_voice_print_profile")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v760_voice_print_profile: " + str(e))
    raise SystemExit(1)
