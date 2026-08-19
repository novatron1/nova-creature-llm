"""Live, deterministic grade-band evaluation for an installed Nova LoRA adapter.

This measures performance on a small curriculum-oriented test. It does not
estimate IQ and must not be presented as a standardized educational assessment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nova_local_llm_connector import LocalLLMConfig
from nova_lora_adapter_registry import resolve_lora_adapter
from nova_lora_runtime import generate_with_lora, unload_cached_lora_runtimes


DEFAULT_ADAPTER_ID = "nova-qwen2-5-1-5b-focused-repair-20260723"
DEFAULT_REPORT = ROOT / "reports" / "nova_focused_repair_grade_eval.json"


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    band: str
    subject: str
    prompt: str
    checks: tuple[dict[str, Any], ...]
    max_new_tokens: int = 72


def _cases() -> tuple[EvalCase, ...]:
    return (
        EvalCase(
            "elementary_arithmetic",
            "elementary_grades_3_5",
            "math",
            "Answer with only the number: What is 7 multiplied by 8?",
            ({"label": "answer_56", "regex": r"\b56\b"},),
            24,
        ),
        EvalCase(
            "elementary_inference",
            "elementary_grades_3_5",
            "reading",
            (
                "Ben sees dark clouds and packs an umbrella before leaving. "
                "What does Ben probably expect? Answer in one sentence."
            ),
            ({"label": "expects_rain", "any": ("rain", "storm", "wet weather")},),
            48,
        ),
        EvalCase(
            "elementary_water_cycle",
            "elementary_grades_3_5",
            "science",
            (
                "Name the three main water-cycle stages in their usual order. "
                "Use one short sentence."
            ),
            (
                {"label": "evaporation", "all": ("evaporation",)},
                {"label": "condensation", "all": ("condensation",)},
                {"label": "precipitation", "all": ("precipitation",)},
            ),
            48,
        ),
        EvalCase(
            "middle_ratio",
            "middle_school_grades_6_8",
            "math",
            (
                "Six notebooks cost $42 at the same price each. What do nine "
                "notebooks cost? Give the amount and one short calculation."
            ),
            (
                {"label": "answer_63", "regex": r"(?:\$\s*)?\b63\b"},
                {"label": "unit_rate_7", "regex": r"\b42\s*(?:/|÷)\s*6\b|\b7\b"},
            ),
            64,
        ),
        EvalCase(
            "middle_fraction",
            "middle_school_grades_6_8",
            "math",
            "Compute 5/6 minus 1/4. Reduce the answer. Keep it brief.",
            ({"label": "answer_7_12", "regex": r"\b7\s*/\s*12\b"},),
            48,
        ),
        EvalCase(
            "middle_experiment",
            "middle_school_grades_6_8",
            "science",
            (
                "A student tests how light affects plant growth. What should be "
                "changed, and name two things that should be kept the same?"
            ),
            (
                {"label": "changes_light", "all": ("light",)},
                {
                    "label": "controls_two_variables",
                    "count_any": {
                        "terms": ("water", "soil", "plant type", "temperature", "pot"),
                        "minimum": 2,
                    },
                },
            ),
            72,
        ),
        EvalCase(
            "high_algebra",
            "high_school_grades_9_12",
            "algebra",
            "Solve 3(2x - 5) = 27. State x and show the essential steps.",
            (
                {"label": "answer_x_7", "regex": r"\bx\s*=\s*7\b"},
                {"label": "expansion_or_reduction", "any": ("6x", "42", "27 + 15")},
            ),
            72,
        ),
        EvalCase(
            "high_probability",
            "high_school_grades_9_12",
            "probability",
            (
                "Two fair six-sided dice are rolled. What is the probability "
                "that their sum is 8? Give a reduced fraction and a brief reason."
            ),
            (
                {"label": "answer_5_36", "regex": r"\b5\s*/\s*36\b"},
                {
                    "label": "five_outcomes",
                    "regex": r"\b5\s+(?:such\s+)?(?:combinations|outcomes|favorable)",
                },
                {"label": "thirty_six_total", "regex": r"\b36\s+(?:possible\s+)?outcomes"},
            ),
            96,
        ),
        EvalCase(
            "high_causation",
            "high_school_grades_9_12",
            "scientific_reasoning",
            (
                "Ice-cream sales and drowning incidents both rise in summer. "
                "Does that prove ice cream causes drowning? Explain briefly."
            ),
            (
                {"label": "rejects_causation", "any": ("does not prove", "doesn't prove", "no,")},
                {"label": "identifies_confounder", "any": ("temperature", "hot weather", "summer heat")},
                {"label": "names_correlation", "any": ("correlation", "correlated", "confound")},
            ),
            88,
        ),
        EvalCase(
            "college_calculus",
            "introductory_college",
            "calculus",
            (
                "Differentiate f(x) = x^3 - 4x + 7. Return the derivative and "
                "one short justification."
            ),
            (
                {
                    "label": "derivative",
                    "regex": r"3\s*\*?\s*x\s*(?:\^|\*\*)\s*2\s*-\s*4|3x²\s*-\s*4",
                },
                {
                    "label": "valid_justification",
                    "any": ("power rule", "constant", "derivative of 7", "7 becomes 0"),
                },
            ),
            72,
        ),
        EvalCase(
            "college_physics",
            "introductory_college",
            "physics",
            (
                "A 2 kg object moves at 3 m/s. Calculate its kinetic energy "
                "using KE = 1/2 mv^2. Include the unit."
            ),
            (
                {"label": "answer_9_joules", "regex": r"\b9\s*(?:j|joule|joules)\b"},
                {"label": "substitution", "any": ("1/2", "0.5", "3^2", "3²")},
            ),
            72,
        ),
        EvalCase(
            "college_coding",
            "introductory_college",
            "coding",
            (
                "Write a short Python function even_numbers(values) that returns "
                "only the even integers from values. Return code plus one sentence."
            ),
            (
                {"label": "function_signature", "regex": r"def\s+even_numbers\s*\("},
                {"label": "modulo_test", "regex": r"%\s*2"},
                {"label": "even_comparison", "regex": r"==\s*0|not\s+[^:\n]*%\s*2"},
                {"label": "returns_collection", "any": ("return", "append")},
            ),
            96,
        ),
        EvalCase(
            "advanced_logic",
            "advanced_practical",
            "formal_logic",
            (
                "Some artists are engineers. All engineers solve problems. Is it "
                "logically guaranteed that some artists solve problems? Answer yes "
                "or no and justify in two sentences."
            ),
            (
                {"label": "answer_yes", "regex": r"^\s*yes\b"},
                {"label": "valid_inference", "all": ("artists", "engineers", "solve problems")},
            ),
            80,
        ),
        EvalCase(
            "advanced_debug_plan",
            "advanced_practical",
            "systems_debugging",
            (
                "API latency tripled immediately after a deployment. Give the "
                "first three evidence-based actions you would take. Do not claim "
                "the cause is already known."
            ),
            (
                {
                    "label": "compares_before_after",
                    "any": (
                        "before and after",
                        "baseline",
                        "previous version",
                        "compare",
                        "historical data",
                    ),
                },
                {"label": "uses_observability", "any": ("metrics", "traces", "logs", "profil")},
                {"label": "safe_mitigation", "any": ("rollback", "roll back", "canary", "revert")},
                {
                    "label": "preserves_uncertainty",
                    "any": (
                        "hypothesis",
                        "not assume",
                        "determine",
                        "isolate",
                        "could have caused",
                        "consider whether",
                    ),
                },
            ),
            120,
        ),
        EvalCase(
            "advanced_evidence",
            "advanced_practical",
            "epistemic_reasoning",
            (
                "Two articles conflict about a current technical fact. Describe "
                "how to answer accurately without pretending certainty."
            ),
            (
                {"label": "primary_sources", "any": ("primary source", "official documentation", "original source")},
                {"label": "checks_dates", "any": ("date", "recency", "recent", "current")},
                {"label": "corroborates", "any": ("corrobor", "multiple", "independent")},
                {"label": "states_uncertainty", "any": ("uncertain", "uncertainty", "cannot confirm", "conflict")},
            ),
            112,
        ),
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _check_result(output: str, check: dict[str, Any]) -> bool:
    normalized = _normalize(output)
    if "regex" in check:
        return re.search(str(check["regex"]), output, flags=re.IGNORECASE | re.MULTILINE) is not None
    if "all" in check:
        return all(_normalize(term) in normalized for term in check["all"])
    if "any" in check:
        return any(_normalize(term) in normalized for term in check["any"])
    if "count_any" in check:
        details = dict(check["count_any"])
        found = sum(_normalize(term) in normalized for term in details.get("terms", ()))
        return found >= int(details.get("minimum", 1))
    return False


def _letter_grade(score: float) -> str:
    if score >= 0.90:
        return "A"
    if score >= 0.80:
        return "B"
    if score >= 0.70:
        return "C"
    if score >= 0.60:
        return "D"
    return "F"


def run(adapter_id: str = DEFAULT_ADAPTER_ID, report_path: Path = DEFAULT_REPORT) -> dict[str, Any]:
    adapter = resolve_lora_adapter(adapter_id)
    if not adapter:
        raise FileNotFoundError(f"Adapter is not registered: {adapter_id}")

    config = LocalLLMConfig()
    results: list[dict[str, Any]] = []
    started = time.monotonic()
    cases = _cases()
    try:
        for index, case in enumerate(cases, start=1):
            case_started = time.monotonic()
            response = generate_with_lora(
                case.prompt,
                config=config,
                adapter_id=adapter_id,
                max_new_tokens=case.max_new_tokens,
                temperature=0.0,
                top_p=1.0,
                raw_mode=True,
            )
            output = str(response.raw_output or "").strip()
            criteria = [
                {
                    "label": str(check["label"]),
                    "passed": _check_result(output, check),
                }
                for check in case.checks
            ]
            passed_count = sum(item["passed"] for item in criteria)
            score = passed_count / len(criteria) if criteria else 0.0
            results.append(
                {
                    "sequence": index,
                    "case_id": case.case_id,
                    "band": case.band,
                    "subject": case.subject,
                    "prompt": case.prompt,
                    "output": output,
                    "score": round(score, 4),
                    "passed": score >= 0.75,
                    "criteria": criteria,
                    "provider": response.provider,
                    "model": response.model,
                    "fallback_used": bool(response.fallback_used),
                    "error": response.error,
                    "latency_ms": round((time.monotonic() - case_started) * 1000, 3),
                }
            )
            print(
                f"[{index}/{len(cases)}] {case.case_id}: "
                f"{round(score * 100, 1)}%",
                flush=True,
            )
    finally:
        unload_result = unload_cached_lora_runtimes(force=True)

    ordered_bands = (
        "elementary_grades_3_5",
        "middle_school_grades_6_8",
        "high_school_grades_9_12",
        "introductory_college",
        "advanced_practical",
    )
    band_scores: dict[str, dict[str, Any]] = {}
    for band in ordered_bands:
        band_results = [item for item in results if item["band"] == band]
        score = sum(float(item["score"]) for item in band_results) / len(band_results)
        band_scores[band] = {
            "score": round(score, 4),
            "percent": round(score * 100, 1),
            "passed_cases": sum(bool(item["passed"]) for item in band_results),
            "case_count": len(band_results),
            "demonstrated": score >= 0.75,
        }

    overall = sum(float(item["score"]) for item in results) / len(results)
    demonstrated_bands = [
        band for band in ordered_bands if band_scores[band]["demonstrated"]
    ]
    highest = demonstrated_bands[-1] if demonstrated_bands else "below_test_threshold"
    report = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evaluation_type": "live_raw_lora_grade_band_probe",
        "adapter_id": adapter_id,
        "base_model": adapter.get("base_model"),
        "adapter_path": adapter.get("path"),
        "adapter_sha256": adapter.get("sha256"),
        "raw_adapter_only": True,
        "nova_memory_used": False,
        "nova_rag_used": False,
        "nova_tools_used": False,
        "nova_answer_replacement_used": False,
        "internet_used": False,
        "case_count": len(results),
        "overall_score": round(overall, 4),
        "overall_percent": round(overall * 100, 1),
        "letter_grade": _letter_grade(overall),
        "mastery_threshold": 0.75,
        "highest_demonstrated_band": highest,
        "band_scores": band_scores,
        "total_latency_ms": round((time.monotonic() - started) * 1000, 3),
        "fallback_count": sum(bool(item["fallback_used"]) for item in results),
        "error_count": sum(bool(item["error"]) for item in results),
        "results": results,
        "runtime_unload": unload_result,
        "limitations": [
            "This is a small local curriculum probe, not a standardized exam.",
            "The result is not an IQ score and must not be converted into one.",
            "Keyword and exact-answer rubrics can miss some semantically correct answers.",
            "Grade-band performance does not imply complete mastery of that curriculum.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def rescore_report(report_path: Path = DEFAULT_REPORT) -> dict[str, Any]:
    """Apply the current deterministic rubric to already generated outputs."""

    report = json.loads(report_path.read_text(encoding="utf-8"))
    case_map = {case.case_id: case for case in _cases()}
    results = list(report.get("results") or [])
    for result in results:
        case = case_map.get(str(result.get("case_id") or ""))
        if case is None:
            continue
        output = str(result.get("output") or "")
        criteria = [
            {
                "label": str(check["label"]),
                "passed": _check_result(output, check),
            }
            for check in case.checks
        ]
        score = sum(item["passed"] for item in criteria) / len(criteria)
        result["criteria"] = criteria
        result["score"] = round(score, 4)
        result["passed"] = score >= 0.75

    ordered_bands = (
        "elementary_grades_3_5",
        "middle_school_grades_6_8",
        "high_school_grades_9_12",
        "introductory_college",
        "advanced_practical",
    )
    band_scores: dict[str, dict[str, Any]] = {}
    for band in ordered_bands:
        band_results = [item for item in results if item.get("band") == band]
        score = sum(float(item.get("score") or 0) for item in band_results) / len(band_results)
        band_scores[band] = {
            "score": round(score, 4),
            "percent": round(score * 100, 1),
            "passed_cases": sum(bool(item.get("passed")) for item in band_results),
            "case_count": len(band_results),
            "demonstrated": score >= 0.75,
        }

    overall = sum(float(item.get("score") or 0) for item in results) / len(results)
    demonstrated = [band for band in ordered_bands if band_scores[band]["demonstrated"]]
    report["overall_score"] = round(overall, 4)
    report["overall_percent"] = round(overall * 100, 1)
    report["letter_grade"] = _letter_grade(overall)
    report["highest_demonstrated_band"] = (
        demonstrated[-1] if demonstrated else "below_test_threshold"
    )
    report["band_scores"] = band_scores
    report["results"] = results
    report["scoring_audit"] = {
        "rescored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generation_rerun": False,
        "model_outputs_changed": False,
        "reason": "Corrected deterministic rubric after manual output audit.",
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--rescore":
        report = rescore_report()
    else:
        adapter_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADAPTER_ID
        report = run(adapter_id)
    summary = {
        key: report[key]
        for key in (
            "adapter_id",
            "case_count",
            "overall_percent",
            "letter_grade",
            "highest_demonstrated_band",
            "band_scores",
            "total_latency_ms",
            "fallback_count",
            "error_count",
        )
    }
    print(json.dumps(summary, indent=2))
    return 0 if report["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
