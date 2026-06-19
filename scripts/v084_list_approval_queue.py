#!/usr/bin/env python3
"""v084 — List approval queue."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v084_owner_approval_console import list_pending, list_history, CATEGORIES

def main():
    print("Nova v084 -- Approval Queue\n")
    pending = list_pending()
    history = list_history()
    print(f"Categories: {', '.join(CATEGORIES)}")
    print(f"\nPending: {len(pending)}")
    for p in pending:
        print(f"  {p['id']}: [{p['type']}] {p['description'][:60]}")
    print(f"\nHistory: {len(history)}")
    for h in history:
        print(f"  {h['id']}: [{h['type']}] {h['status']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
