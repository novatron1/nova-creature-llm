from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v056_conversation_router import answer_with_context

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("--thread-id", default="default")
    args = ap.parse_args()

    result = answer_with_context(args.message, thread_id=args.thread_id)
    print(result["answer"])
    print()
    print("Route:", result["route"])
    print("Topic:", result["state"]["current_topic"])
    print("Goal:", result["state"]["active_goal"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
