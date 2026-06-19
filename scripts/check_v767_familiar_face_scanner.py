"""v767_familiar_face_scanner — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v767_familiar_face_scanner import familiar_face_scanner
    r = familiar_face_scanner()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v767_familiar_face_scanner")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v767_familiar_face_scanner: " + str(e))
    raise SystemExit(1)
