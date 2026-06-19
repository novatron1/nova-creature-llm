"""v768_encounter_history_viewer — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v768_encounter_history_viewer import encounter_history_viewer
    r = encounter_history_viewer()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v768_encounter_history_viewer")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v768_encounter_history_viewer: " + str(e))
    raise SystemExit(1)
