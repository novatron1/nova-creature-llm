#!/usr/bin/env python3
"""Run Nova's bounded clean-start release smoke check."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_release_gates import run_clean_start_smoke  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start and smoke-check one isolated Nova release candidate."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()

    result = run_clean_start_smoke(
        args.root,
        args.report,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
