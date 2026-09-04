from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_runtime.orchestrator import run_proof_job  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Nova Creature proof job.")
    parser.add_argument("--project-root", required=True, help="Path to the project root to modify and verify.")
    parser.add_argument("--output-dir", default=None, help="Optional isolated workspace directory.")
    args = parser.parse_args()

    result = run_proof_job(project_root=Path(args.project_root), output_dir=args.output_dir)
    print(json.dumps(result.to_dict(), indent=2))
    print(result.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
