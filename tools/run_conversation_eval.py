"""Run Nova's evaluation-only conversation bank and save a safe JSON report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_conversation_eval import (  # noqa: E402
    load_conversation_eval_pack,
    run_conversation_eval,
)


DEFAULT_PACK = ROOT / "data" / "evals" / "nova_conversation_variations_v1.json"


def _live_chat(base_url: str):
    endpoint = base_url.rstrip("/") + "/api/chat"

    def call(prompt: str) -> str:
        body = json.dumps(
            {
                "text": prompt,
                "evaluation_only": True,
                "conversation_summary_write_allowed": False,
                "memory_policy": "read_only",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return str(payload.get("response") or "")

    return call


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--live-url", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases = load_conversation_eval_pack(args.pack)
    if args.limit > 0:
        cases = cases[: args.limit]
    report = run_conversation_eval(
        cases,
        chat=_live_chat(args.live_url) if args.live_url else None,
    )
    payload = report.to_dict()
    payload.update(
        {
            "mode": "full_chat" if args.live_url else "decision_only",
            "evaluation_only": True,
            "training_allowed": False,
            "memory_writes_allowed": False,
            "pack": args.pack.name,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"{payload['mode']}: {report.passed}/{report.total} passed; "
        f"report={args.output}"
    )
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
