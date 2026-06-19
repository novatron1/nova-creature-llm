"""v967_whole_brain_jump_round_3 — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v967_whole_brain_jump_round_3 import whole_brain_jump_round_3
    r = whole_brain_jump_round_3()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v967_whole_brain_jump_round_3")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v967_whole_brain_jump_round_3: " + str(e))
    raise SystemExit(1)
