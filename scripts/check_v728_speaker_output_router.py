"""728 — Check Speaker Output Router"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v728_speaker_output_router import speaker_output_router
    r = speaker_output_router()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v728_speaker_output_router")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v728_speaker_output_router: " + str(e))
    raise SystemExit(1)
