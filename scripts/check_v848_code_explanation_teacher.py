"""v848_code_explanation_teacher — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v848_code_explanation_teacher import code_explanation_teacher
    r = code_explanation_teacher()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v848_code_explanation_teacher")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v848_code_explanation_teacher: " + str(e))
    raise SystemExit(1)
