"""v796_teach_speed_optimizer — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v796_teach_speed_optimizer import teach_speed_optimizer
    r = teach_speed_optimizer()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v796_teach_speed_optimizer")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v796_teach_speed_optimizer: " + str(e))
    raise SystemExit(1)
