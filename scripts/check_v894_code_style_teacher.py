"""v894_code_style_teacher — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v894_code_style_teacher import code_style_teacher
    r = code_style_teacher()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v894_code_style_teacher")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v894_code_style_teacher: " + str(e))
    raise SystemExit(1)
