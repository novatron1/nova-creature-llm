#!/usr/bin/env python3
"""Plan, build, inspect, promote, and clean Nova Release Lock runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
try:
    sys.path.remove(str(SRC))
except ValueError:
    pass
sys.path.insert(0, str(SRC))

from nova_release_lock import NovaReleaseLock, ReleaseRun, ReleaseStatus  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a verified local Nova snapshot")
    parser.add_argument("--repo", default=str(ROOT), help="Nova Git worktree to snapshot")
    parser.add_argument("--temp-root", help="Approved external Release Lock worktree root")
    parser.add_argument("--policy", help="Snapshot policy JSON path")
    commands = parser.add_subparsers(dest="operation")
    commands.add_parser("plan", help="Classify the workspace without creating a worktree")
    build = commands.add_parser("build", help="Build and verify a planned candidate")
    build.add_argument("--run-id", required=True)
    status = commands.add_parser("status", help="Show a persisted run")
    status.add_argument("--run-id", required=True)
    promote = commands.add_parser("promote", help="Merge a verified candidate into local master")
    promote.add_argument("--run-id", required=True)
    cleanup = commands.add_parser("cleanup", help="Remove verified temporary worktrees")
    cleanup.add_argument("--run-id", required=True)
    return parser


def _summary(operation: str, run: ReleaseRun) -> dict[str, object]:
    return {
        "operation": operation,
        "run_id": run.run_id,
        "status": run.status.value,
        "master_before": run.master_before,
        "master_after": run.master_after,
        "candidate_branch": run.candidate_branch,
        "candidate_commit": run.candidate_commit,
        "rollback_ref": run.rollback_ref,
        "promoted": run.status is ReleaseStatus.PROMOTED,
        "report_path": str(run.paths.run_report),
        "failure_gate": run.failure_gate,
    }


def _safe_error_message(error: BaseException, *paths: str | None) -> str:
    message = str(error) or error.__class__.__name__
    for path in paths:
        if path:
            message = message.replace(str(Path(path).absolute()), "[REDACTED_PATH]")
    return message[:1000]


def main(
    argv: Sequence[str] | None = None,
    *,
    controller_factory: Callable[..., NovaReleaseLock] = NovaReleaseLock,
) -> int:
    args = _parser().parse_args(argv)
    operation = args.operation or "plan"
    try:
        controller = controller_factory(
            repo_root=args.repo,
            temp_root=args.temp_root,
            policy_path=args.policy,
        )
        if operation == "plan":
            run = controller.preflight()
        elif operation == "build":
            run = controller.build(args.run_id)
        elif operation == "status":
            run = controller.load_run(args.run_id)
        elif operation == "promote":
            controller.promote(args.run_id)
            run = controller.load_run(args.run_id)
        else:
            run = controller.cleanup(args.run_id)
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "operation": operation,
                    "error": "unsafe_state",
                    "message": _safe_error_message(
                        error,
                        args.repo,
                        args.temp_root,
                        args.policy,
                    ),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(_summary(operation, run), indent=2, sort_keys=True))
    return 1 if run.status is ReleaseStatus.FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
