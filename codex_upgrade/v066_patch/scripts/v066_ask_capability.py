from __future__ import annotations

import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v066_capability_answerer import answer_capability_question

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True, help="Ask about Nova's capabilities")
    args = ap.parse_args()
    result = answer_capability_question(args.question)
    print(result["answer"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
