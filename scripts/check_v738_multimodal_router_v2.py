"""738 — Check Multimodal Router V2"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v738_multimodal_router_v2 import multimodal_router_v2
    r = multimodal_router_v2()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v738_multimodal_router_v2")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v738_multimodal_router_v2: " + str(e))
    raise SystemExit(1)
