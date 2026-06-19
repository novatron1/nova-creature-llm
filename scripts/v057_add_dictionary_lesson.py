from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dictionary_memory import DictionaryMemory

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    ap.add_argument("--answer", required=True)
    ap.add_argument("--approve", action="store_true")
    args = ap.parse_args()

    d = DictionaryMemory(ROOT)
    if args.approve:
        item = d.add_approved(args.question, args.answer)
        print("PASS: approved dictionary lesson added.")
    else:
        item = d.add_pending(args.question, args.answer)
        print("PASS: pending dictionary lesson added.")
    print(item)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
