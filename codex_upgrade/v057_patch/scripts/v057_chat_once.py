from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v057_dictionary_conversation_router import answer

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("--thread-id", default="default")
    args = ap.parse_args()

    result = answer(args.message, thread_id=args.thread_id)
    print(result["answer"])
    print()
    print("Route:", result["route"])
    print("Dictionary found:", result["dictionary_found"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
