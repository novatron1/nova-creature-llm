"""v933_whole_brain_jump_attempt — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v933_whole_brain_jump_attempt import whole_brain_jump_attempt
    r = whole_brain_jump_attempt()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v933_whole_brain_jump_attempt")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v933_whole_brain_jump_attempt: " + str(e))
    raise SystemExit(1)
