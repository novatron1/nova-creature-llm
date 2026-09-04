"""Repeated, privacy-safe qualification for Nova's local middle model."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nova_capability_eval import (  # noqa: E402
    get_default_capability_evaluation_store,
    qualify_text_model,
)
from nova_gateway.providers import NovaProviderRegistry, OllamaProvider  # noqa: E402
from nova_model_quality import get_default_model_quality_registry  # noqa: E402


DEFAULT_JSON_REPORT = ROOT / "reports" / "nova_middle_model_qualification.json"
DEFAULT_MARKDOWN_REPORT = (
    ROOT / "reports" / "NOVA_MIDDLE_MODEL_QUALIFICATION.md"
)


def _markdown(report: dict[str, Any]) -> str:
    status = "QUALIFIED" if report.get("eligible_for_middle") else "NOT QUALIFIED"
    lines = [
        "# Nova Middle Model Qualification",
        "",
        f"- Status: **{status}**",
        f"- Model: `{report.get('model_id')}`",
        f"- Provider: `{report.get('provider_id')}`",
        f"- Pack: `{report.get('pack_version')}`",
        f"- Repeated runs: {report.get('repeated_runs')}",
        f"- Cases per run: {report.get('case_count_per_run')}",
        f"- Overall score: {float(report.get('overall_score') or 0) * 100:.1f}%",
        f"- Required score: {float(report.get('minimum_score') or 0) * 100:.1f}%",
        f"- Critical capability floor: "
        f"{float(report.get('critical_capability_floor') or 0) * 100:.1f}%",
        f"- Average case latency: {float(report.get('average_latency_ms') or 0):.1f} ms",
        f"- Primary model changed: {bool(report.get('primary_model_changed'))}",
        "",
        "## Capability scores",
        "",
        "| Capability | Score |",
        "|---|---:|",
    ]
    for name, score in dict(report.get("capabilities") or {}).items():
        lines.append(f"| {name} | {float(score) * 100:.1f}% |")
    lines.extend(
        [
            "",
            "## Repeated runs",
            "",
            "| Run | Score | Passed | Cases | Average latency |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for run in list(report.get("runs") or []):
        lines.append(
            f"| {run.get('run')} | {float(run.get('score') or 0) * 100:.1f}% "
            f"| {run.get('passed_cases')} | {run.get('case_count')} "
            f"| {float(run.get('average_latency_ms') or 0):.1f} ms |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- This test never changes Nova's 1.5B primary chat model.",
            "- A pass qualifies the model only as a replaceable local escalation tier.",
            "- Raw adapters are excluded and are never intercepted by this evaluator.",
            "- Prompts and generated model text are not written to the quality registry.",
            "- This bounded test is not an IQ or general-intelligence measurement.",
            "",
        ]
    )
    return "\n".join(lines)


def run(
    *,
    model_id: str = "qwen2.5:3b",
    repeated_runs: int = 3,
    timeout_seconds: int = 60,
    minimum_score: float = 0.85,
    json_report: Path = DEFAULT_JSON_REPORT,
    markdown_report: Path = DEFAULT_MARKDOWN_REPORT,
) -> dict[str, Any]:
    registry = NovaProviderRegistry(default_provider="ollama")
    registry.register_provider(OllamaProvider(timeout=timeout_seconds))
    result = qualify_text_model(
        registry,
        model_id=model_id,
        role="middle",
        quality_registry=get_default_model_quality_registry(ROOT),
        store=get_default_capability_evaluation_store(ROOT),
        repeated_runs=repeated_runs,
        timeout_seconds=timeout_seconds,
        minimum_score=minimum_score,
    )
    report = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evaluation_type": "nova_local_middle_model_qualification",
        **result,
    }
    json_report.parent.mkdir(parents=True, exist_ok=True)
    json_report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_report.parent.mkdir(parents=True, exist_ok=True)
    markdown_report.write_text(_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify a local model for Nova's middle escalation tier."
    )
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--minimum-score", type=float, default=0.85)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=DEFAULT_MARKDOWN_REPORT,
    )
    args = parser.parse_args()
    report = run(
        model_id=args.model,
        repeated_runs=args.runs,
        timeout_seconds=args.timeout,
        minimum_score=args.minimum_score,
        json_report=args.json_report,
        markdown_report=args.markdown_report,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "model_id": report.get("model_id"),
                "overall_score": report.get("overall_score"),
                "capabilities": report.get("capabilities"),
                "eligible_for_middle": report.get("eligible_for_middle"),
                "average_latency_ms": report.get("average_latency_ms"),
                "content_logged": report.get("content_logged"),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if report.get("eligible_for_middle") else 2


if __name__ == "__main__":
    raise SystemExit(main())
