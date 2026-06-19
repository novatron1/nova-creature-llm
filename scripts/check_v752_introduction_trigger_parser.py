"""v752_introduction_trigger_parser — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v752_introduction_trigger_parser import introduction_trigger_parser
    r = introduction_trigger_parser()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v752_introduction_trigger_parser")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v752_introduction_trigger_parser: " + str(e))
    raise SystemExit(1)
