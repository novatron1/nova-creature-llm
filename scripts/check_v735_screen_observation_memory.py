"""735 — Check Screen Observation Memory"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v735_screen_observation_memory import screen_observation_memory
    r = screen_observation_memory()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v735_screen_observation_memory")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v735_screen_observation_memory: " + str(e))
    raise SystemExit(1)
