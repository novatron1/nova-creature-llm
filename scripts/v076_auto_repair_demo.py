#!/usr/bin/env python3
"""v076 — Auto repair demo."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v076_auto_patch_repair import create_broken_script, detect_error, repair_script, run_script

def main():
    print("Nova v076 -- Auto Repair Demo\n")
    path = create_broken_script("broken_test.py")
    print(f"1. Created broken script: {path}")
    err = detect_error(path)
    print(f"2. Detected error: {err['has_error']} ({err.get('error_type','?')})")
    result = repair_script(path)
    print(f"3. Repair: {result['success']}")
    if result.get("repair"):
        print(f"   Backup: {result['repair']['backup']}")
    retest = run_script(path)
    print(f"4. Retest: {retest['success']}")
    print(f"   Output: {retest['stdout'][:100]}")
    (ROOT/"reports"/"v076_auto_patch_repair_status.json").write_text(json.dumps({
        "version": "v076_auto_repair_demo", "created_at": datetime.now().isoformat(),
        "broken_script": path, "error_detected": err["has_error"],
        "repair_success": result["success"], "retest_success": retest["success"]}, indent=2))
    print(f"\nReport: reports/v076_auto_patch_repair_status.json")
    return 0 if retest["success"] else 1
if __name__ == "__main__":
    raise SystemExit(main())
