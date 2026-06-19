"""v857_targeted_drill_generator — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v857_targeted_drill_generator import targeted_drill_generator
    r = targeted_drill_generator()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v857_targeted_drill_generator")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v857_targeted_drill_generator: " + str(e))
    raise SystemExit(1)
