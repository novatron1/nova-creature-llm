from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_hyper_training_orchestrator import run_hyper_training


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260622)
    parser.add_argument("--route-epochs", type=int, default=80)
    parser.add_argument("--role-epochs", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        result = run_hyper_training(
            ROOT,
            seed=args.seed,
            route_epochs=args.route_epochs,
            role_epochs=args.role_epochs,
        )
    except Exception as exc:
        result = {
            "verdict": "BLOCKED",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] in {"PROMOTED", "REJECTED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
