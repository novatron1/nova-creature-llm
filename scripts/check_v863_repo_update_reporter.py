"""v863_repo_update_reporter — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v863_repo_update_reporter import repo_update_reporter
    r = repo_update_reporter()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v863_repo_update_reporter")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v863_repo_update_reporter: " + str(e))
    raise SystemExit(1)
