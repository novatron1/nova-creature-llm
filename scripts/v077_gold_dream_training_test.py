#!/usr/bin/env python3
"""v077 — Gold dream training test."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v077_dream_training_generator import run_generator

def main():
    print("Nova v077 -- Gold Dream Training Test\n")
    result = run_generator("Who created you?", "Mr. Novotron", 20)
    print(f"Seed: Who created you? -> Mr. Novotron")
    print(f"Generated: {result['variants_generated']} (expected >=20)")
    print(f"Approved: {result['approved']} (safe paraphrases)")
    print(f"Rejected: {result['rejected']} (distorted variants)")
    print(f"Exported: {result['exported']} (training candidates)")
    ok = result['variants_generated'] >= 20 and result['approved'] >= 18
    print(f"\n{'PASS' if ok else 'FAIL'}: Gold dream training test")
    (ROOT/"reports"/"v077_dream_training_generator_status.json").write_text(json.dumps(result, indent=2))
    print(f"Report: reports/v077_dream_training_generator_status.json")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
