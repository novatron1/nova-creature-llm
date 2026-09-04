"""Deterministic, read-only evaluation for Nova conversation understanding."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from typing import Any, Callable, Iterable

from nova_conversation_intelligence import understand_conversation_turn


CONVERSATION_EVAL_VERSION = "nova-conversation-eval-1.0"


@dataclass(frozen=True)
class ConversationEvalCase:
    """One versioned conversation-routing evaluation case."""

    case_id: str
    category: str
    prompt: str
    expected_intent_family: str
    required_signals: tuple[str, ...] = ()
    prohibited_signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConversationEvalReport:
    """Machine-readable aggregate containing no evaluated prompt content."""

    version: str
    total: int
    passed: int
    failed: int
    category_scores: dict[str, float]
    failures: tuple[dict[str, Any], ...]
    latency_ms: float
    training_writes: int = 0
    content_logged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_conversation_eval_pack(
    path: str | Path,
) -> tuple[ConversationEvalCase, ...]:
    """Load and validate a local, versioned evaluation-only case pack."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Conversation evaluation pack must be a JSON object.")
    if payload.get("version") != CONVERSATION_EVAL_VERSION:
        raise ValueError("Unsupported conversation evaluation pack version.")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("Conversation evaluation pack cases must be an array.")

    cases: list[ConversationEvalCase] = []
    identifiers: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("Conversation evaluation cases must be objects.")
        case = ConversationEvalCase(
            case_id=str(raw.get("case_id") or "").strip(),
            category=str(raw.get("category") or "").strip(),
            prompt=str(raw.get("prompt") or "").strip(),
            expected_intent_family=str(
                raw.get("expected_intent_family") or ""
            ).strip(),
            required_signals=tuple(
                str(item).strip()
                for item in raw.get("required_signals") or ()
                if str(item).strip()
            ),
            prohibited_signals=tuple(
                str(item).strip()
                for item in raw.get("prohibited_signals") or ()
                if str(item).strip()
            ),
        )
        if not all(
            (
                case.case_id,
                case.category,
                case.prompt,
                case.expected_intent_family,
            )
        ):
            raise ValueError("Conversation evaluation case has empty required fields.")
        if case.case_id in identifiers:
            raise ValueError(f"Duplicate conversation evaluation case ID: {case.case_id}")
        identifiers.add(case.case_id)
        cases.append(case)
    return tuple(cases)


def run_conversation_eval(
    cases: Iterable[ConversationEvalCase],
    chat: Callable[[str], Any] | None = None,
) -> ConversationEvalReport:
    """Run a bounded evaluation without invoking memory or training writers.

    When ``chat`` is omitted, only Nova's shared deterministic decision is
    measured. An explicit caller may supply a chat callable for a full-stack
    smoke run, but the prompt and response are never copied into the report.
    """

    started = time.monotonic()
    selected = tuple(cases)
    category_totals: dict[str, int] = {}
    category_passes: dict[str, int] = {}
    failures: list[dict[str, Any]] = []

    for case in selected:
        category_totals[case.category] = category_totals.get(case.category, 0) + 1
        decision = understand_conversation_turn(case.prompt)
        signals = set(decision.signals)
        missing = sorted(set(case.required_signals) - signals)
        prohibited = sorted(set(case.prohibited_signals) & signals)
        passed = (
            decision.intent_family == case.expected_intent_family
            and not missing
            and not prohibited
        )
        chat_error = ""
        if passed and chat is not None:
            try:
                result = chat(case.prompt)
                if isinstance(result, tuple):
                    result = result[0] if result else ""
                passed = bool(str(result or "").strip())
                if not passed:
                    chat_error = "empty_response"
            except Exception as exc:  # evaluation records safe error class only
                passed = False
                chat_error = exc.__class__.__name__
        if passed:
            category_passes[case.category] = (
                category_passes.get(case.category, 0) + 1
            )
        else:
            failures.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "expected_intent_family": case.expected_intent_family,
                    "actual_intent_family": decision.intent_family,
                    "missing_signals": missing,
                    "prohibited_signals": prohibited,
                    "chat_error": chat_error or None,
                    "content_logged": False,
                }
            )

    category_scores = {
        category: round(category_passes.get(category, 0) / total, 6)
        for category, total in sorted(category_totals.items())
    }
    failed = len(failures)
    return ConversationEvalReport(
        version=CONVERSATION_EVAL_VERSION,
        total=len(selected),
        passed=len(selected) - failed,
        failed=failed,
        category_scores=category_scores,
        failures=tuple(failures),
        latency_ms=round((time.monotonic() - started) * 1000, 3),
    )
