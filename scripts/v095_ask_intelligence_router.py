#!/usr/bin/env python3
"""v095 — Ask the intelligence router a question."""
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v095_intelligence_router import answer_intelligently

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    args = ap.parse_args()
    r = answer_intelligently(args.question)
    print(f"Q: {args.question}\n")
    print(f"Route: {r['route']}")
    print(f"Answer: {r['final_answer']}")
    print(f"Confidence: {r['confidence']}")
    if r.get("evidence") and r["evidence"].get("is_speculation"):
        print(f"Note: This was flagged as speculation")
    if r.get("self_correction") and r["self_correction"].get("correction_applied"):
        print(f"Note: Answer was self-corrected")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
