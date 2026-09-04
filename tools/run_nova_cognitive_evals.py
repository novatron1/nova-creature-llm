from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from tests.evals.harness import write_eval_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Nova cognitive OS evaluations")
    parser.add_argument(
        "--output",
        default="reports/nova_cognitive_eval_latest.json",
    )
    args = parser.parse_args()
    report = write_eval_report(args.output)
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
