"""Risk-based deterministic verification for Nova answers and actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable

from nova_gateway.structured import validate_json_schema


VERIFIER_VERSION = "1.0"


@dataclass
class VerificationResult:
    passed: bool
    confidence: float
    unsupported_claims: list[str] = field(default_factory=list)
    conflicting_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    failed_actions: list[str] = field(default_factory=list)
    recommended_repair: str | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)
    skipped: bool = False
    version: str = VERIFIER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def safe_trace(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "passed": self.passed,
            "confidence": round(float(self.confidence), 3),
            "unsupported_claim_count": len(self.unsupported_claims),
            "conflicting_evidence_count": len(self.conflicting_evidence),
            "missing_evidence_count": len(self.missing_evidence),
            "failed_action_count": len(self.failed_actions),
            "recommended_repair": self.recommended_repair,
            "checks": [dict(item) for item in self.checks],
            "skipped": self.skipped,
            "answer_content_logged": False,
            "private_reasoning_logged": False,
        }


def _valid_iso_dates(text: str) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    for value in set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", str(text or ""))):
        try:
            date.fromisoformat(value)
            valid.append(value)
        except ValueError:
            invalid.append(value)
    return sorted(valid), sorted(invalid)


def _citation_ids(sources: Iterable[Any]) -> set[str]:
    available: set[str] = set()
    for source in sources:
        citation = getattr(source, "citation", None)
        if citation:
            available.add(str(citation))
        if isinstance(source, dict):
            if source.get("citation"):
                available.add(str(source["citation"]))
            source_id = source.get("source_id")
            chunk = source.get("chunk_number")
            if source_id is not None and chunk is not None:
                available.add(f"[{source_id}:{chunk}]")
    return available


def _duplicated_sentences(text: str) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    sentences = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    for sentence in sentences:
        canonical = re.sub(r"\W+", " ", sentence.lower()).strip()
        if len(canonical) < 24:
            continue
        if canonical in seen:
            duplicates.append(sentence[:160])
        seen.add(canonical)
    return duplicates


def _simple_conflicts(text: str) -> list[str]:
    positive: set[str] = set()
    negative: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", str(text or "")):
        match = re.match(
            r"\s*(?P<subject>[A-Za-z][A-Za-z0-9 _-]{1,60})\s+is\s+(?P<neg>not\s+)?(?P<value>[^.!?]{1,80})",
            sentence,
            flags=re.I,
        )
        if not match:
            continue
        claim = re.sub(
            r"\W+",
            " ",
            f"{match.group('subject')} is {match.group('value')}".lower(),
        ).strip()
        (negative if match.group("neg") else positive).add(claim)
    return sorted(positive & negative)


def _math_check(user_text: str, answer: str) -> dict[str, Any] | None:
    try:
        from nova_deterministic_verifier import solve_deterministic_request

        solution = solve_deterministic_request(user_text)
    except Exception:
        solution = None
    if solution is None:
        return None
    expected = str(solution.expected_value)
    return {
        "check": "calculation_recomputed",
        "passed": bool(re.search(rf"(?<![\d.]){re.escape(expected)}(?!\d)", answer)),
        "domain": solution.domain,
        "rule_id": solution.rule_id,
    }


class NovaVerifier:
    """Prefer deterministic checks; optionally call a critic only afterwards."""

    def verify(
        self,
        *,
        user_text: str,
        answer: str,
        sources: Iterable[Any] = (),
        response_schema: dict[str, Any] | None = None,
        expected_actions: Iterable[dict[str, Any]] = (),
        observed_actions: Iterable[dict[str, Any]] = (),
        expected_files: Iterable[str | Path] = (),
        require_sources: bool = False,
        model_critic: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> VerificationResult:
        checks: list[dict[str, Any]] = []
        unsupported: list[str] = []
        conflicting: list[str] = []
        missing: list[str] = []
        failed_actions: list[str] = []

        math_check = _math_check(user_text, answer)
        if math_check:
            checks.append(math_check)
            if not math_check["passed"]:
                unsupported.append("The displayed calculation does not contain the recomputed result.")

        if response_schema is not None:
            try:
                structured = json.loads(answer)
                schema_errors = validate_json_schema(structured, response_schema)
            except (json.JSONDecodeError, TypeError) as error:
                schema_errors = [type(error).__name__]
            checks.append(
                {
                    "check": "json_schema",
                    "passed": not schema_errors,
                    "error_count": len(schema_errors),
                }
            )
            if schema_errors:
                unsupported.append("Structured output did not satisfy its JSON Schema.")

        available = _citation_ids(sources)
        cited = set(re.findall(r"\[[A-Za-z0-9_.:/-]+:\d+\]", answer))
        missing_citations = sorted(cited - available)
        if cited or available or require_sources:
            citation_passed = not missing_citations and (bool(cited) or not require_sources)
            checks.append(
                {
                    "check": "citation_existence",
                    "passed": citation_passed,
                    "cited": len(cited),
                    "available": len(available),
                    "missing": len(missing_citations),
                }
            )
            if missing_citations:
                missing.extend(f"Unknown citation {item}" for item in missing_citations)
            if require_sources and not cited:
                missing.append("The answer requires evidence but contains no source citation.")

        expected_file_list = list(expected_files)
        missing_files = [str(path) for path in expected_file_list if not Path(path).exists()]
        if expected_file_list:
            checks.append(
                {
                    "check": "file_existence",
                    "passed": not missing_files,
                    "missing": len(missing_files),
                }
            )
            missing.extend(f"Expected file does not exist: {item}" for item in missing_files)

        expected_list = list(expected_actions)
        observed_list = list(observed_actions)
        expected_by_id = {
            str(item.get("action_id") or item.get("tool_name") or index): item
            for index, item in enumerate(expected_list)
        }
        observed_by_id = {
            str(item.get("action_id") or item.get("tool_name") or index): item
            for index, item in enumerate(observed_list)
        }
        if expected_by_id:
            for action_id in expected_by_id:
                observed = observed_by_id.get(action_id)
                if not observed or not bool(
                    observed.get("verified")
                    or observed.get("status") in {"verified", "verified_result", "completed"}
                ):
                    failed_actions.append(action_id)
            checks.append(
                {
                    "check": "expected_vs_observed_actions",
                    "passed": not failed_actions,
                    "expected": len(expected_by_id),
                    "verified": len(expected_by_id) - len(failed_actions),
                }
            )

        _valid_dates, invalid_dates = _valid_iso_dates(answer)
        checks.append(
            {
                "check": "date_consistency",
                "passed": not invalid_dates,
                "invalid_count": len(invalid_dates),
            }
        )
        unsupported.extend(f"Invalid calendar date: {item}" for item in invalid_dates)

        duplicates = _duplicated_sentences(answer)
        checks.append(
            {
                "check": "duplicate_claims",
                "passed": not duplicates,
                "duplicate_count": len(duplicates),
            }
        )
        conflicting.extend(f"Duplicated claim: {item}" for item in duplicates)

        contradictions = _simple_conflicts(answer)
        checks.append(
            {
                "check": "internal_contradictions",
                "passed": not contradictions,
                "conflict_count": len(contradictions),
            }
        )
        conflicting.extend(f"Contradictory claim: {item}" for item in contradictions)

        deterministic_passed = not (unsupported or conflicting or missing or failed_actions)
        if model_critic is not None:
            critic = model_critic(
                {
                    "deterministic_passed": deterministic_passed,
                    "checks": checks,
                    "unsupported_claim_count": len(unsupported),
                    "missing_evidence_count": len(missing),
                    "failed_action_count": len(failed_actions),
                }
            )
            checks.append(
                {
                    "check": "bounded_model_critic",
                    "passed": bool(critic.get("passed", True)),
                    "summary": str(critic.get("summary") or "")[:200],
                }
            )
            if not bool(critic.get("passed", True)):
                unsupported.append("A bounded critic flagged a load-bearing claim.")

        passed = not (unsupported or conflicting or missing or failed_actions)
        confidence = 0.98 if passed and checks else 0.75 if passed else 0.35
        repair = None
        if failed_actions:
            repair = "Report only actions with observed and verified results."
        elif missing:
            repair = "Retrieve valid source evidence or state that evidence is insufficient."
        elif unsupported:
            repair = "Recalculate or regenerate only the unsupported load-bearing claim."
        elif conflicting:
            repair = "Remove the duplicated or contradictory claim and verify the retained version."
        return VerificationResult(
            passed=passed,
            confidence=confidence,
            unsupported_claims=unsupported,
            conflicting_evidence=conflicting,
            missing_evidence=missing,
            failed_actions=failed_actions,
            recommended_repair=repair,
            checks=checks,
        )


def skipped_verification() -> VerificationResult:
    return VerificationResult(
        passed=True,
        confidence=0.75,
        checks=[{"check": "risk_router", "passed": True, "status": "skipped_low_risk"}],
        skipped=True,
    )


def verify_answer(**kwargs: Any) -> VerificationResult:
    return NovaVerifier().verify(**kwargs)


__all__ = [
    "VERIFIER_VERSION",
    "VerificationResult",
    "NovaVerifier",
    "skipped_verification",
    "verify_answer",
]
