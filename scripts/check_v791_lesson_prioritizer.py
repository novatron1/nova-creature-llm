"""v791_lesson_prioritizer — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v791_lesson_prioritizer import lesson_prioritizer
    r = lesson_prioritizer()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v791_lesson_prioritizer")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v791_lesson_prioritizer: " + str(e))
    raise SystemExit(1)
