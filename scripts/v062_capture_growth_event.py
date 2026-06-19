#!/usr/bin/env python3
"""v062 — Capture a growth event from CLI."""

import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v062_growth_engine import capture_growth_event

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="Source text to capture")
    ap.add_argument("--stream", help="Growth stream name (auto-detected if omitted)")
    args = ap.parse_args()
    event = capture_growth_event(args.source, stream_name=args.stream)
    print(json.dumps(event, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
