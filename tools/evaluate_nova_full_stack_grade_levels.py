"""Live grade-band evaluation through Nova's real /api/chat pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import evaluate_lora_grade_levels as raw_eval


DEFAULT_BASE_URL = "http://127.0.0.1:8880"
DEFAULT_REPORT = ROOT / "reports" / "nova_full_stack_grade_eval.json"
RAW_REPORT = ROOT / "reports" / "nova_focused_repair_grade_eval.json"


def _post_chat(base_url: str, payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
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
        raise RuntimeError(f"Nova HTTP {error.code}: {detail[:1000]}") from error
    if not isinstance(result, dict):
        raise RuntimeError("Nova returned a non-object response")
    return result


def _safe_trace(trace: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "reasoning_mode",
        "final_answer_source",
        "local_llm_provider",
        "local_llm_model",
        "confidence",
        "route_path",
        "roles",
        "skills",
        "fallback_used",
        "fallback_reason",
        "verification",
        "agent_loop_v2",
        "model_escalation",
        "turn_analysis",
        "rag",
    )
    return {key: trace.get(key) for key in allowed if key in trace}


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    ordered_bands = (
        "elementary_grades_3_5",
        "middle_school_grades_6_8",
        "high_school_grades_9_12",
        "introductory_college",
        "advanced_practical",
    )
    band_scores: dict[str, dict[str, Any]] = {}
    for band in ordered_bands:
        selected = [item for item in results if item["band"] == band]
        score = sum(float(item["score"]) for item in selected) / len(selected)
        band_scores[band] = {
            "score": round(score, 4),
            "percent": round(score * 100, 1),
            "passed_cases": sum(bool(item["passed"]) for item in selected),
            "case_count": len(selected),
            "demonstrated": score >= 0.75,
        }
    overall = sum(float(item["score"]) for item in results) / len(results)
    demonstrated = [
        band for band in ordered_bands if band_scores[band]["demonstrated"]
    ]
    return {
        "overall_score": round(overall, 4),
        "overall_percent": round(overall * 100, 1),
        "letter_grade": raw_eval._letter_grade(overall),
        "highest_demonstrated_band": (
            demonstrated[-1] if demonstrated else "below_test_threshold"
        ),
        "band_scores": band_scores,
    }


def run(
    base_url: str = DEFAULT_BASE_URL,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    cases = raw_eval._cases()
    results: list[dict[str, Any]] = []
    started = time.monotonic()
    for index, case in enumerate(cases, start=1):
        case_started = time.monotonic()
        error = None
        try:
            result = _post_chat(
                base_url,
                {
                    "text": case.prompt,
                    "session_id": f"full-stack-grade-{case.case_id}",
                    "user_id": "nova-evaluation",
                    "client_id": "nova-full-stack-grade-eval",
                    "nova_gateway": True,
                    "request_id": f"grade-{case.case_id}",
                    "memory_read_allowed": False,
                    "memory_write_allowed": False,
                    "conversation_memory_allowed": False,
                    "capability_evaluation": True,
                    "evaluation_only": True,
                    "private_mode": False,
                },
            )
            output = str(result.get("response") or "").strip()
            trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
        except Exception as exc:
            output = ""
            trace = {}
            error = str(exc)

        criteria = [
            {
                "label": str(check["label"]),
                "passed": raw_eval._check_result(output, check),
            }
            for check in case.checks
        ]
        score = sum(item["passed"] for item in criteria) / len(criteria)
        record = {
            "sequence": index,
            "case_id": case.case_id,
            "band": case.band,
            "subject": case.subject,
            "prompt": case.prompt,
            "output": output,
            "score": round(score, 4),
            "passed": score >= 0.75,
            "criteria": criteria,
            "trace": _safe_trace(trace),
            "error": error,
            "latency_ms": round((time.monotonic() - case_started) * 1000, 3),
        }
        results.append(record)
        print(
            f"[{index}/{len(cases)}] {case.case_id}: "
            f"{round(score * 100, 1)}% "
            f"source={trace.get('final_answer_source') or 'unknown'}",
            flush=True,
        )

    summary = _summary(results)
    raw_report = (
        json.loads(RAW_REPORT.read_text(encoding="utf-8"))
        if RAW_REPORT.exists()
        else {}
    )
    raw_score = float(raw_report.get("overall_percent") or 0)
    report = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evaluation_type": "live_nova_full_stack_grade_band_probe",
        "base_url": base_url,
        "case_count": len(results),
        **summary,
        "raw_adapter_baseline_percent": raw_score,
        "improvement_points": round(summary["overall_percent"] - raw_score, 1),
        "memory_read_allowed": False,
        "memory_write_allowed": False,
        "conversation_memory_allowed": False,
        "turn_analysis_enabled": True,
        "routing_enabled": True,
        "rag_eligibility_enabled": True,
        "tools_enabled": True,
        "verification_enabled": True,
        "natural_response_shaping_enabled": True,
        "total_latency_ms": round((time.monotonic() - started) * 1000, 3),
        "error_count": sum(bool(item["error"]) for item in results),
        "results": results,
        "limitations": [
            "This is a small local curriculum probe, not a standardized exam.",
            "The result is not an IQ score and must not be converted into one.",
            "Keyword and exact-answer rubrics can miss some semantically correct answers.",
            "The full stack may use different local models and deterministic subsystems by task.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    report = run(base_url)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "case_count",
                    "overall_percent",
                    "letter_grade",
                    "highest_demonstrated_band",
                    "band_scores",
                    "raw_adapter_baseline_percent",
                    "improvement_points",
                    "total_latency_ms",
                    "error_count",
                )
            },
            indent=2,
        )
    )
    return 0 if report["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
