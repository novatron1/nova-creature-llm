from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v060_memory_manager import list_pending, list_training_candidates

def main():
    print("Nova Creature v060 — Pending Memory Items\n")
    pending = list_pending()
    if not pending:
        print("No pending approval items.")
    else:
        print(f"Pending approval ({len(pending)}):")
        for ev in pending:
            print(f"  [{ev.get('id')}] {ev.get('extracted_fact', ev.get('message',''))[:80]}")
            print(f"    Reason: {ev.get('reason')}")
            print(f"    Tags: {ev.get('tags')}")
    print()
    candidates = list_training_candidates()
    if candidates:
        print(f"Training candidates ({len(candidates)}):")
        for ev in candidates:
            print(f"  [{ev.get('id')}] {ev.get('extracted_fact', ev.get('message',''))[:80]}")
    else:
        print("No training candidates.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
