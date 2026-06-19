from __future__ import annotations

import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v061_learning_loop_manager import run_learning_loop


def main() -> int:
    ap = argparse.ArgumentParser(description="v061 Learning Loop — Smart Memory → Training")
    ap.add_argument("--dry-run", action="store_true", help="Preview without changing files")
    ap.add_argument("--approve-all", action="store_true", help="Auto-approve pending items")
    ap.add_argument("--max-items", type=int, default=None, help="Max items to export")
    ap.add_argument("--skip-finetune", action="store_true", help="Skip v055 fine-tune step")
    ap.add_argument("--skip-promote", action="store_true", help="Skip v059 promote check")
    args = ap.parse_args()

    report = run_learning_loop(
        dry_run=args.dry_run,
        approve_all=args.approve_all,
        max_items=args.max_items,
        skip_finetune=args.skip_finetune,
        skip_promote=args.skip_promote,
    )

    print(f"\nReport: reports/v061_learning_loop_status.json")
    return 0 if report["can_promote"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
