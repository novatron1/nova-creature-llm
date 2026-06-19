"""v777_lesson_chunker — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v777_lesson_chunker import lesson_chunker
    r = lesson_chunker()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v777_lesson_chunker")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v777_lesson_chunker: " + str(e))
    raise SystemExit(1)
