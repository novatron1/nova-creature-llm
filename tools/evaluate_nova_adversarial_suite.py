"""Run Nova's 100-case adversarial bank through the real /api/chat route."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nova_adversarial_eval import (  # noqa: E402
    ADVERSARIAL_BANK_VERSION,
    AdversarialCase,
    build_adversarial_bank,
    category_counts,
    score_case,
)


DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_JSON_REPORT = ROOT / "reports" / "nova_adversarial_eval.json"
DEFAULT_MARKDOWN_REPORT = ROOT / "reports" / "NOVA_ADVERSARIAL_EVAL_REPORT.md"


def _post_chat(
    base_url: str,
    payload: dict[str, Any],
    *,
    timeout: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Nova HTTP {error.code}: {detail[:600]}") from error
    if not isinstance(result, dict):
        raise RuntimeError("Nova returned a non-object response")
    return result


def _payload(
    *,
    text: str,
    case: AdversarialCase,
    session_id: str,
    request_id: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload = {
        "text": text,
        "session_id": session_id,
        "user_id": "nova-adversarial-evaluation",
        "client_id": "nova-adversarial-evaluation",
        "nova_gateway": True,
        "request_id": request_id,
        "memory_read_allowed": False,
        "memory_write_allowed": False,
        "conversation_memory_allowed": True,
        "capability_evaluation": True,
        "evaluation_only": True,
        "private_mode": True,
        "metadata": {
            "evaluation_bank": ADVERSARIAL_BANK_VERSION,
            "evaluation_case_id": case.case_id,
        },
    }
    if conversation_history:
        payload["conversation_history"] = [
            {
                "role": str(item.get("role") or "")[:20],
                "content": str(item.get("content") or "")[:4000],
            }
            for item in conversation_history[-8:]
            if str(item.get("role") or "") in {"user", "assistant"}
            and str(item.get("content") or "").strip()
        ]
    return payload


def _safe_trace(trace: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "reasoning_mode",
        "final_answer_source",
        "local_llm_provider",
        "local_llm_model",
        "confidence",
        "fallback_used",
        "fallback_reason",
        "route_path",
        "roles",
        "shield_result",
        "verification",
        "turn_analysis",
        "direct_middle_routing",
        "model_escalation",
    )
    return {key: trace.get(key) for key in allowed if key in trace}


def _summaries(results: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    categories = sorted({str(item["category"]) for item in results})
    category_scores: dict[str, dict[str, Any]] = {}
    for category in categories:
        selected = [item for item in results if item["category"] == category]
        score = sum(float(item["score"]) for item in selected) / max(1, len(selected))
        category_scores[category] = {
            "score": round(score, 4),
            "percent": round(score * 100, 1),
            "passed_cases": sum(bool(item["passed"]) for item in selected),
            "case_count": len(selected),
            "error_count": sum(bool(item["error"]) for item in selected),
        }
    overall = sum(float(item["score"]) for item in results) / max(1, len(results))
    summary = {
        "overall_score": round(overall, 4),
        "overall_percent": round(overall * 100, 1),
        "passed_cases": sum(bool(item["passed"]) for item in results),
        "case_count": len(results),
        "error_count": sum(bool(item["error"]) for item in results),
    }
    return summary, category_scores


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Nova Adversarial Evaluation",
        "",
        f"- Bank: `{report['bank_version']}`",
        f"- Cases: {report['case_count']}",
        f"- Passed cases: {report['passed_cases']}",
        f"- Overall rubric score: **{report['overall_percent']:.1f}%**",
        f"- HTTP/runtime errors: {report['error_count']}",
        f"- Total runtime: {float(report['total_latency_ms']) / 1000:.1f} seconds",
        "",
        "## Category results",
        "",
        "| Category | Score | Passed | Cases | Errors |",
        "|---|---:|---:|---:|---:|",
    ]
    for category, item in dict(report.get("category_scores") or {}).items():
        lines.append(
            f"| {category} | {float(item['percent']):.1f}% | "
            f"{item['passed_cases']} | {item['case_count']} | {item['error_count']} |"
        )
    failures = [
        item for item in list(report.get("results") or []) if not item.get("passed")
    ]
    lines.extend(["", "## Failed or weak cases", ""])
    if not failures:
        lines.append("No cases fell below the per-case pass threshold.")
    else:
        for item in failures:
            failed_checks = [
                check["label"]
                for check in item.get("criteria") or []
                if not check.get("passed")
            ]
            lines.append(
                f"- `{item['case_id']}` ({item['category']}): "
                f"{float(item['score']) * 100:.1f}% — "
                f"{', '.join(failed_checks) or item.get('error') or 'rubric miss'}"
            )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- This bank is a bounded engineering regression suite, not an IQ test.",
            "- Deterministic keyword and format rubrics can miss some semantically correct answers.",
            "- Passing does not prove correctness on questions outside the tested behaviors.",
            "- Evaluation turns cannot write long-term memory; session continuity is temporary.",
            "",
        ]
    )
    return "\n".join(lines)


def run(
    *,
    base_url: str = DEFAULT_BASE_URL,
    categories: set[str] | None = None,
    limit: int | None = None,
    timeout_seconds: int = 180,
    json_report: Path = DEFAULT_JSON_REPORT,
    markdown_report: Path = DEFAULT_MARKDOWN_REPORT,
) -> dict[str, Any]:
    bank = list(build_adversarial_bank())
    if categories:
        bank = [case for case in bank if case.category in categories]
    if limit is not None:
        bank = bank[: max(0, int(limit))]
    results: list[dict[str, Any]] = []
    suite_started = time.monotonic()

    for sequence, case in enumerate(bank, start=1):
        case_started = time.monotonic()
        session_id = f"adversarial-{case.case_id}-{sequence}"
        output = ""
        trace: dict[str, Any] = {}
        error: str | None = None
        setup_results: list[dict[str, Any]] = []
        conversation_history: list[dict[str, str]] = []
        try:
            for turn_index, setup_text in enumerate(case.setup_turns, start=1):
                setup_response = _post_chat(
                    base_url,
                    _payload(
                        text=setup_text,
                        case=case,
                        session_id=session_id,
                        request_id=f"adv-{case.case_id}-setup-{turn_index}",
                        conversation_history=conversation_history,
                    ),
                    timeout=timeout_seconds,
                )
                setup_output = str(setup_response.get("response") or "").strip()
                conversation_history.append({"role": "user", "content": setup_text})
                if setup_output:
                    conversation_history.append(
                        {"role": "assistant", "content": setup_output}
                    )
                conversation_history = conversation_history[-8:]
                setup_trace = (
                    setup_response.get("trace")
                    if isinstance(setup_response.get("trace"), dict)
                    else {}
                )
                setup_results.append(
                    {
                        "turn": turn_index,
                        "response_present": bool(setup_output),
                        "source": setup_trace.get("final_answer_source"),
                    }
                )
            response = _post_chat(
                base_url,
                _payload(
                    text=case.prompt,
                    case=case,
                    session_id=session_id,
                    request_id=f"adv-{case.case_id}-final",
                    conversation_history=conversation_history,
                ),
                timeout=timeout_seconds,
            )
            output = str(response.get("response") or "").strip()
            trace = (
                response.get("trace")
                if isinstance(response.get("trace"), dict)
                else {}
            )
        except Exception as exc:
            error = str(exc)
        score, criteria = score_case(case, output)
        record = {
            "sequence": sequence,
            "case_id": case.case_id,
            "category": case.category,
            "description": case.description,
            "prompt": case.prompt,
            "setup_turn_count": len(case.setup_turns),
            "setup_results": setup_results,
            "output": output,
            "score": round(score, 4),
            "passed": score >= 0.75 and error is None,
            "criteria": criteria,
            "trace": _safe_trace(trace),
            "error": error,
            "latency_ms": round((time.monotonic() - case_started) * 1000, 3),
        }
        results.append(record)
        print(
            f"[{sequence}/{len(bank)}] {case.category}/{case.case_id}: "
            f"{record['score'] * 100:.1f}% "
            f"source={trace.get('final_answer_source') or 'unknown'}",
            flush=True,
        )

    summary, category_scores = _summaries(results)
    report = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evaluation_type": "live_nova_adversarial_full_stack",
        "bank_version": ADVERSARIAL_BANK_VERSION,
        "base_url": base_url,
        **summary,
        "category_scores": category_scores,
        "selected_bank_counts": category_counts(bank),
        "memory_read_allowed": False,
        "memory_write_allowed": False,
        "conversation_memory_allowed": True,
        "long_term_memory_pollution_prevented": True,
        "total_latency_ms": round((time.monotonic() - suite_started) * 1000, 3),
        "results": results,
        "limitations": [
            "This is a bounded engineering regression suite, not an IQ test.",
            "Keyword and format rubrics can miss semantically correct answers.",
            "Passing does not establish ability outside the tested behavior classes.",
        ],
    }
    json_report.parent.mkdir(parents=True, exist_ok=True)
    json_report.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_report.parent.mkdir(parents=True, exist_ok=True)
    markdown_report.write_text(_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Nova's full-stack adversarial regression bank."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Run only this category; repeat to select multiple categories.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=DEFAULT_MARKDOWN_REPORT,
    )
    args = parser.parse_args()
    report = run(
        base_url=args.base_url,
        categories=set(args.category) or None,
        limit=args.limit,
        timeout_seconds=args.timeout,
        json_report=args.json_report,
        markdown_report=args.markdown_report,
    )
    print(
        json.dumps(
            {
                "case_count": report["case_count"],
                "passed_cases": report["passed_cases"],
                "overall_percent": report["overall_percent"],
                "error_count": report["error_count"],
                "category_scores": report["category_scores"],
                "total_latency_ms": report["total_latency_ms"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if report["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
