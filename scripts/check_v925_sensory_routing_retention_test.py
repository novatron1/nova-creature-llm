"""v925_sensory_routing_retention_test — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v925_sensory_routing_retention_test import sensory_routing_retention_test
    r = sensory_routing_retention_test()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v925_sensory_routing_retention_test")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v925_sensory_routing_retention_test: " + str(e))
    raise SystemExit(1)
