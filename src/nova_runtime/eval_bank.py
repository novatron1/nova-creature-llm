"""Behavioral eval bank for Nova Creature."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable
import json


REQUIRED_BEHAVIOR_CATEGORIES = {
    "conversation_quality",
    "memory_recall",
    "planning",
    "tool_choice",
    "tool_refusal",
    "self_correction",
    "research_accuracy",
    "multi_step_completion",
}


@dataclass(frozen=True, slots=True)
class BehaviorEvalCase:
    case_id: str
    category: str
    prompt: str
    expected_behavior: str
    required_evidence: tuple[str, ...]
    pass_criteria: str


@dataclass(frozen=True, slots=True)
class BehaviorEvalBank:
    bank_id: str
    version: str
    cases: tuple[BehaviorEvalCase, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def categories(self) -> set[str]:
        return {case.category for case in self.cases}


@dataclass(frozen=True, slots=True)
class BehaviorEvalResult:
    case_id: str
    category: str
    passed: bool
    exact_score: float
    semantic_score: float
    required_evidence_count: int
    evidence_count: int
    failure_category: str | None
    details: dict[str, Any]


def _normalize_case(payload: dict[str, Any]) -> BehaviorEvalCase:
    required = tuple(
        str(item).strip()
        for item in payload.get("required_evidence") or ()
        if str(item).strip()
    )
    case = BehaviorEvalCase(
        case_id=str(payload["case_id"]).strip(),
        category=str(payload["category"]).strip(),
        prompt=str(payload["prompt"]).strip(),
        expected_behavior=str(payload["expected_behavior"]).strip(),
        required_evidence=required,
        pass_criteria=str(payload["pass_criteria"]).strip(),
    )
    if not case.case_id or not case.category or not case.prompt:
        raise ValueError("Behavior eval cases require case_id, category, and prompt.")
    return case


def load_behavior_eval_bank(path: str | Path | dict[str, Any]) -> BehaviorEvalBank:
    if isinstance(path, dict):
        payload = dict(path)
    else:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = tuple(_normalize_case(item) for item in payload.get("cases") or [])
    if not cases:
        raise ValueError("Behavior eval bank must include at least one case.")
    bank = BehaviorEvalBank(
        bank_id=str(payload.get("bank_id") or "nova_creature_behavior_eval_bank"),
        version=str(payload.get("version") or "1.0"),
        cases=cases,
        metadata=dict(payload.get("metadata") or {}),
    )
    missing = REQUIRED_BEHAVIOR_CATEGORIES - bank.categories()
    if missing:
        raise ValueError(
            "Behavior eval bank is missing required categories: "
            + ", ".join(sorted(missing))
        )
    return bank


def save_behavior_eval_bank(bank: BehaviorEvalBank, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "bank_id": bank.bank_id,
        "version": bank.version,
        "metadata": bank.metadata,
        "cases": [asdict(case) for case in bank.cases],
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return destination


def score_behavior_eval_bank(
    bank: BehaviorEvalBank,
    judge: Callable[[BehaviorEvalCase], tuple[bool, dict[str, Any]]],
) -> dict[str, Any]:
    results: list[BehaviorEvalResult] = []
    for case in bank.cases:
        passed, details = judge(case)
        details = dict(details or {})
        evidence_count = len(tuple(details.get("evidence") or ()))
        required_evidence_count = len(case.required_evidence)
        score = 1.0 if passed else 0.0
        semantic_score = float(details.get("semantic_score") or score)
        results.append(
            BehaviorEvalResult(
                case_id=case.case_id,
                category=case.category,
                passed=bool(passed),
                exact_score=score,
                semantic_score=max(0.0, min(1.0, semantic_score)),
                required_evidence_count=required_evidence_count,
                evidence_count=evidence_count,
                failure_category=None if passed else str(details.get("failure_category") or "assertion"),
                details={
                    key: value
                    for key, value in details.items()
                    if key not in {"prompt", "answer", "raw_output"}
                },
            )
        )
    passed = sum(1 for item in results if item.passed)
    by_category: dict[str, dict[str, Any]] = {}
    for result in results:
        bucket = by_category.setdefault(
            result.category,
            {"passed": 0, "total": 0, "score_sum": 0.0},
        )
        bucket["passed"] += int(result.passed)
        bucket["total"] += 1
        bucket["score_sum"] += result.exact_score
    return {
        "bank_id": bank.bank_id,
        "version": bank.version,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "score": passed / len(results) if results else 0.0,
        "categories": {
            category: {
                "passed": values["passed"],
                "total": values["total"],
                "score": round(values["score_sum"] / max(1, values["total"]), 3),
            }
            for category, values in sorted(by_category.items())
        },
        "results": [asdict(result) for result in results],
    }


__all__ = [
    "BehaviorEvalBank",
    "BehaviorEvalCase",
    "BehaviorEvalResult",
    "REQUIRED_BEHAVIOR_CATEGORIES",
    "load_behavior_eval_bank",
    "save_behavior_eval_bank",
    "score_behavior_eval_bank",
]
