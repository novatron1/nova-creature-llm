from __future__ import annotations
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v060_memory_manager import approve_pending

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    args = ap.parse_args()
    result = approve_pending(args.id)
    if result["approved"]:
        print(f"PASS: approved event {args.id}")
    else:
        print(f"FAIL: event {args.id} not found")
    return 0 if result["approved"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
