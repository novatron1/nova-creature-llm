#!/usr/bin/env python3
"""Export targeted role training sets."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v182_targeted_role_training_exporter import export_targeted_training
def main():
    r = export_targeted_training()
    print(f"Exported to {len(r['role_counts'])} role files")
    for role, count in r["role_counts"].items():
        if count > 0: print(f"  {role}: {count} items")
    print(f"Total exported: {r['total_exported']}")
    (ROOT/"reports"/"v182_targeted_role_training_export_status.json").write_text(json.dumps(r, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
