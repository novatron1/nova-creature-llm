#!/usr/bin/env python3
"""v084 — Reject an item by ID."""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v084_owner_approval_console import reject_item

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    args = ap.parse_args()
    r = reject_item(args.id)
    print(json.dumps(r, indent=2))
    return 0 if r["success"] else 1
if __name__ == "__main__":
    raise SystemExit(main())
