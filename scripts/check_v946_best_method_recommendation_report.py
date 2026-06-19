"""v946_best_method_recommendation_report — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v946_best_method_recommendation_report import best_method_recommendation_report
    r = best_method_recommendation_report()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v946_best_method_recommendation_report")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v946_best_method_recommendation_report: " + str(e))
    raise SystemExit(1)
