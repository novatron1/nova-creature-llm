"""726 — Check Speaker Discovery"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v726_speaker_discovery import speaker_discovery
    r = speaker_discovery()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v726_speaker_discovery")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v726_speaker_discovery: " + str(e))
    raise SystemExit(1)
