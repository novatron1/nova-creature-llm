"""v858_coding_curriculum_builder — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v858_coding_curriculum_builder import coding_curriculum_builder
    r = coding_curriculum_builder()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v858_coding_curriculum_builder")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v858_coding_curriculum_builder: " + str(e))
    raise SystemExit(1)
