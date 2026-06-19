"""v829_code_understanding_notes — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v829_code_understanding_notes import code_understanding_notes
    r = code_understanding_notes()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v829_code_understanding_notes")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v829_code_understanding_notes: " + str(e))
    raise SystemExit(1)
