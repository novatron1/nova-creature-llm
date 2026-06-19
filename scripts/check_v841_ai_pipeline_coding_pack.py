"""v841_ai_pipeline_coding_pack — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v841_ai_pipeline_coding_pack import ai_pipeline_coding_pack
    r = ai_pipeline_coding_pack()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v841_ai_pipeline_coding_pack")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v841_ai_pipeline_coding_pack: " + str(e))
    raise SystemExit(1)
