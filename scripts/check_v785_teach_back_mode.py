"""v785_teach_back_mode — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v785_teach_back_mode import teach_back_mode
    r = teach_back_mode()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v785_teach_back_mode")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v785_teach_back_mode: " + str(e))
    raise SystemExit(1)
