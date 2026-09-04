"""Private, provider-neutral capability evaluation for Nova-managed models.

Evaluation prompts and provider outputs exist only in memory for the duration
of a bounded check. Persistent records contain operational scores and safe
reason codes only. This module never trains a model or touches Raw adapters.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from threading import RLock
import time
from typing import Any, Callable
import urllib.request

from nova_protocol import NovaGenerationOptions, NovaMessage, NovaRequest


CAPABILITY_EVAL_SCHEMA_VERSION = "1.2"
CAPABILITY_EVAL_ENGINE_VERSION = "1.2"
CAPABILITY_PACK_VERSION = "nova-private-local-2.0"
_SAFE_FAILURE_REASONS = {
    "empty_response",
    "generation_failed",
    "invalid_json",
    "model_quarantined",
    "output_mismatch",
    "provider_error",
    "raw_model_excluded",
    "timeout",
    "token_limit",
    "vision_keyword_mismatch",
}
_MAX_VISION_BYTES = 5 * 1024 * 1024


def _environment_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _environment_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _normalized_key(provider_id: str, model_id: str) -> str:
    return (
        str(provider_id or "unknown").strip().lower()
        + "/"
        + str(model_id or "unknown").strip().lower().removesuffix(":latest")
    )


def _safe_reason(reason: str) -> str:
    value = str(reason or "").strip().lower()
    return value if value in _SAFE_FAILURE_REASONS else "provider_error"


def _normalized_exact(value: str) -> str:
    return (
        str(value or "")
        .replace("`", "")
        .strip()
        .strip(" .,!?:;\"'")
        .casefold()
    )


def _score_exact(expected: str, output: str) -> tuple[float, str]:
    if not str(output or "").strip():
        return 0.0, "empty_response"
    return (
        (1.0, "passed")
        if _normalized_exact(output) == _normalized_exact(expected)
        else (0.0, "output_mismatch")
    )


def _score_even_json(output: str) -> tuple[float, str]:
    value = str(output or "").strip()
    if not value:
        return 0.0, "empty_response"
    value = value.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end < start:
        return 0.0, "invalid_json"
    try:
        payload = json.loads(value[start : end + 1])
    except (TypeError, ValueError):
        return 0.0, "invalid_json"
    return (
        (1.0, "passed")
        if payload == {"result": [2, 4]}
        else (0.0, "output_mismatch")
    )


def _score_json_equal(expected: Any, output: str) -> tuple[float, str]:
    """Score a JSON-only response after tolerating an optional Markdown fence."""

    value = str(output or "").strip()
    if not value:
        return 0.0, "empty_response"
    value = value.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    starts = [index for index in (value.find("{"), value.find("[")) if index >= 0]
    if not starts:
        return 0.0, "invalid_json"
    start = min(starts)
    end = max(value.rfind("}"), value.rfind("]"))
    if end < start:
        return 0.0, "invalid_json"
    try:
        payload = json.loads(value[start : end + 1])
    except (TypeError, ValueError):
        return 0.0, "invalid_json"
    return (
        (1.0, "passed")
        if payload == expected
        else (0.0, "output_mismatch")
    )


@dataclass(frozen=True)
class CapabilityEvalCase:
    case_id: str
    capability: str
    messages: tuple[tuple[str, str], ...]
    scorer: Callable[[str], tuple[float, str]]
    max_tokens: int = 48

    def request(self, model_id: str, timeout_seconds: int) -> NovaRequest:
        return NovaRequest(
            user_id="nova-capability-lab",
            client_id="nova-capability-lab",
            conversation_id=f"eval-{self.case_id}",
            session_id="capability-eval",
            messages=[
                NovaMessage(role=role, content=content)
                for role, content in self.messages
            ],
            generation_options=NovaGenerationOptions(
                model=model_id,
                temperature=0,
                top_p=1,
                max_tokens=self.max_tokens,
                seed=0,
                stream=False,
            ),
            privacy_mode="local_only",
            metadata={
                "provider_model": model_id,
                "provider_timeout_seconds": timeout_seconds,
                "provider_context_window": 2048,
                "provider_keep_alive": "10m",
                "capability_evaluation": True,
                "internal_nova_managed": True,
            },
            api_source="nova_capability_eval",
        )


def builtin_text_cases() -> tuple[CapabilityEvalCase, ...]:
    """Return the versioned non-private local evaluation pack."""

    return (
        CapabilityEvalCase(
            "instruction_exact",
            "instruction_following",
            (
                (
                    "system",
                    "Follow the output constraint exactly. Return no explanation.",
                ),
                (
                    "user",
                    "Return exactly this token and nothing else: NOVA_BLUE_417",
                ),
            ),
            lambda output: _score_exact("NOVA_BLUE_417", output),
            24,
        ),
        CapabilityEvalCase(
            "continuity_codename",
            "conversation_continuity",
            (
                (
                    "system",
                    "Use only the supplied conversation. Return no explanation.",
                ),
                ("user", "Our project codename is ORBITAL_PINE_42."),
                ("assistant", "I will keep that codename in this conversation."),
                (
                    "user",
                    "What is the project codename? Return only the codename.",
                ),
            ),
            lambda output: _score_exact("ORBITAL_PINE_42", output),
            32,
        ),
        CapabilityEvalCase(
            "reasoning_power_budget",
            "reasoning",
            (
                (
                    "system",
                    "Solve the bounded arithmetic problem. Return only the integer.",
                ),
                (
                    "user",
                    "A device has four modules using 3 watts each and one controller "
                    "using 5 watts. What is the total wattage?",
                ),
            ),
            lambda output: _score_exact("17", output),
            24,
        ),
        CapabilityEvalCase(
            "coding_even_filter",
            "coding",
            (
                (
                    "system",
                    "Return only valid compact JSON. Do not use a Markdown fence.",
                ),
                (
                    "user",
                    'For the integer list [1,2,3,4], return an object with key "result" '
                    "whose value contains only the even integers in order.",
                ),
            ),
            _score_even_json,
            48,
        ),
    )


def qualification_text_cases() -> tuple[CapabilityEvalCase, ...]:
    """Return the larger private-local pack used to qualify an escalation model.

    The pack remains deliberately bounded and deterministic. It is not a claim
    of general intelligence; it checks repeatable behavior Nova depends on.
    """

    exact = lambda expected: (lambda output: _score_exact(expected, output))
    json_equal = lambda expected: (
        lambda output: _score_json_equal(expected, output)
    )
    no_explanation = (
        "Follow the output constraint exactly. Return no explanation, preface, "
        "Markdown, or hidden reasoning."
    )
    return (
        CapabilityEvalCase(
            "qualification_instruction_token",
            "instruction_following",
            (("system", no_explanation), ("user", "Return exactly: NOVA_GREEN_812")),
            exact("NOVA_GREEN_812"),
            24,
        ),
        CapabilityEvalCase(
            "qualification_instruction_case",
            "instruction_following",
            (("system", no_explanation), ("user", "Return the lowercase word: satellite")),
            exact("satellite"),
            24,
        ),
        CapabilityEvalCase(
            "qualification_instruction_separator",
            "instruction_following",
            (
                ("system", no_explanation),
                ("user", "Join ALPHA and BETA with one vertical bar. Return only the result."),
            ),
            exact("ALPHA|BETA"),
            24,
        ),
        CapabilityEvalCase(
            "qualification_instruction_boolean",
            "instruction_following",
            (
                ("system", no_explanation),
                ("user", "Is 9 an even integer? Return only yes or no in lowercase."),
            ),
            exact("no"),
            24,
        ),
        CapabilityEvalCase(
            "qualification_continuity_codename",
            "conversation_continuity",
            (
                ("system", "Use only the supplied conversation. Return only the requested value."),
                ("user", "The project codename is GLASS_COMET_73."),
                ("assistant", "Understood."),
                ("user", "Return the project codename."),
            ),
            exact("GLASS_COMET_73"),
            32,
        ),
        CapabilityEvalCase(
            "qualification_continuity_color",
            "conversation_continuity",
            (
                ("system", "Use only the supplied conversation. Return only the requested value."),
                ("user", "For this test, the preferred panel color is violet."),
                ("assistant", "Noted for this test."),
                ("user", "What is the preferred panel color?"),
            ),
            exact("violet"),
            24,
        ),
        CapabilityEvalCase(
            "qualification_continuity_revision",
            "conversation_continuity",
            (
                ("system", "Use the latest correction. Return only the requested value."),
                ("user", "The release number is 41."),
                ("assistant", "Noted."),
                ("user", "Correction: the release number is 42."),
                ("assistant", "Updated."),
                ("user", "Return the current release number."),
            ),
            exact("42"),
            24,
        ),
        CapabilityEvalCase(
            "qualification_continuity_owner",
            "conversation_continuity",
            (
                ("system", "Use only the supplied conversation. Return only the requested value."),
                ("user", "Mara owns the red key. Devin owns the blue key."),
                ("assistant", "Understood."),
                ("user", "Who owns the blue key?"),
            ),
            exact("Devin"),
            24,
        ),
        CapabilityEvalCase(
            "qualification_reasoning_power",
            "reasoning",
            (
                ("system", "Solve the bounded problem. Return only the integer."),
                (
                    "user",
                    "A device has four modules using 3 watts each and one controller "
                    "using 5 watts. What is the total wattage?",
                ),
            ),
            exact("17"),
            32,
        ),
        CapabilityEvalCase(
            "qualification_reasoning_distance",
            "reasoning",
            (
                ("system", "Solve the bounded problem. Return only the integer."),
                ("user", "A rover travels 48 kilometers per hour for 3 hours. Total kilometers?"),
            ),
            exact("144"),
            32,
        ),
        CapabilityEvalCase(
            "qualification_reasoning_percent",
            "reasoning",
            (
                ("system", "Solve the bounded problem. Return only the integer."),
                ("user", "What is 15 percent of 240?"),
            ),
            exact("36"),
            32,
        ),
        CapabilityEvalCase(
            "qualification_reasoning_sequence",
            "reasoning",
            (
                ("system", "Infer the pattern. Return only the next integer."),
                ("user", "Sequence: 2, 6, 12, 20. What comes next?"),
            ),
            exact("30"),
            32,
        ),
        CapabilityEvalCase(
            "qualification_reasoning_inventory",
            "reasoning",
            (
                ("system", "Solve the bounded problem. Return only the integer."),
                (
                    "user",
                    "Five packs contain 3 sensors each. Each sensor needs 2 clips. "
                    "How many clips are needed?",
                ),
            ),
            exact("30"),
            32,
        ),
        CapabilityEvalCase(
            "qualification_reasoning_order",
            "reasoning",
            (
                ("system", "Solve the ordering problem. Return only the requested name."),
                (
                    "user",
                    "Iris is taller than Bo. Bo is taller than Chen. "
                    "Who is shortest?",
                ),
            ),
            exact("Chen"),
            32,
        ),
        CapabilityEvalCase(
            "qualification_coding_even",
            "coding",
            (
                ("system", "Return only valid compact JSON. Do not use Markdown."),
                (
                    "user",
                    'For [1,2,3,4], return {"result": [...]} containing only even integers.',
                ),
            ),
            json_equal({"result": [2, 4]}),
            64,
        ),
        CapabilityEvalCase(
            "qualification_coding_squares",
            "coding",
            (
                ("system", "Return only valid compact JSON. Do not use Markdown."),
                (
                    "user",
                    'For [2,3,4], return {"squares": [...]} with each integer squared in order.',
                ),
            ),
            json_equal({"squares": [4, 9, 16]}),
            64,
        ),
        CapabilityEvalCase(
            "qualification_coding_keys",
            "coding",
            (
                ("system", "Return only valid compact JSON. Do not use Markdown."),
                (
                    "user",
                    'Return {"keys": [...]} with the keys of {"b":2,"a":1} sorted alphabetically.',
                ),
            ),
            json_equal({"keys": ["a", "b"]}),
            64,
        ),
        CapabilityEvalCase(
            "qualification_coding_filter",
            "coding",
            (
                ("system", "Return only valid compact JSON. Do not use Markdown."),
                (
                    "user",
                    'For [-2,0,5,-1], return {"positive": [...]} containing values greater than zero.',
                ),
            ),
            json_equal({"positive": [5]}),
            64,
        ),
        CapabilityEvalCase(
            "qualification_structured_types",
            "structured_output",
            (
                ("system", "Return only valid compact JSON. Do not use Markdown."),
                (
                    "user",
                    'Return an object with boolean key "ok" set true and integer key "count" set 3.',
                ),
            ),
            json_equal({"ok": True, "count": 3}),
            64,
        ),
        CapabilityEvalCase(
            "qualification_structured_nested",
            "structured_output",
            (
                ("system", "Return only valid compact JSON. Do not use Markdown."),
                (
                    "user",
                    'Return {"device":{"name":"nova","online":true}} exactly as valid JSON.',
                ),
            ),
            json_equal({"device": {"name": "nova", "online": True}}),
            64,
        ),
    )


class NovaCapabilityEvaluationStore:
    """Atomic content-free store for per-model capability scores."""

    def __init__(self, path: str | Path, *, enabled: bool | None = None):
        self.path = Path(path)
        self.enabled = (
            _environment_bool("NOVA_CAPABILITY_EVAL_ENABLED", True)
            if enabled is None
            else bool(enabled)
        )
        self._lock = RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._load_error: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            records = payload.get("records", {}) if isinstance(payload, dict) else {}
            if isinstance(records, dict):
                self._records = {
                    str(key): self._public_record(dict(value))
                    for key, value in records.items()
                    if isinstance(value, dict)
                }
        except Exception:
            self._records = {}
            self._load_error = "capability_eval_store_load_failed"

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CAPABILITY_EVAL_SCHEMA_VERSION,
            "engine_version": CAPABILITY_EVAL_ENGINE_VERSION,
            "pack_version": CAPABILITY_PACK_VERSION,
            "updated_at": _iso_now(),
            "records": self._records,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    @staticmethod
    def _public_record(result: dict[str, Any]) -> dict[str, Any]:
        capabilities: dict[str, dict[str, Any]] = {}
        for name, value in dict(result.get("capabilities") or {}).items():
            if not isinstance(value, dict):
                continue
            score = round(
                max(0.0, min(float(value.get("score") or 0), 1.0)),
                3,
            )
            runs = max(1, int(value.get("runs") or 1))
            last_score = round(
                max(0.0, min(float(value.get("last_score", score)), 1.0)),
                3,
            )
            capabilities[str(name)[:64]] = {
                "score": score,
                "last_score": last_score,
                "runs": runs,
                "passed_runs": max(
                    0,
                    min(
                        int(
                            value.get(
                                "passed_runs",
                                runs if last_score >= 1.0 else 0,
                            )
                        ),
                        runs,
                    ),
                ),
                "passed": int(value.get("passed") or 0),
                "total": int(value.get("total") or 0),
                "evaluated_at": str(value.get("evaluated_at") or _iso_now()),
            }
        total = sum(item["total"] for item in capabilities.values())
        weighted = sum(item["score"] * item["total"] for item in capabilities.values())
        overall = round(weighted / total, 3) if total else 0.0
        reasons = [
            _safe_reason(item)
            for item in list(result.get("failure_reasons") or [])[:8]
        ]
        return {
            "provider_id": str(result.get("provider_id") or "unknown")[:128],
            "model_id": str(result.get("model_id") or "unknown")[:256],
            "role": str(result.get("role") or "managed")[:32],
            "pack_version": CAPABILITY_PACK_VERSION,
            "evaluated_at": str(result.get("evaluated_at") or _iso_now()),
            "overall_score": overall,
            "grade": (
                "strong"
                if overall >= 0.75
                else "capable"
                if overall >= 0.5
                else "limited"
            ),
            "capabilities": capabilities,
            "case_count": total,
            "passed_cases": sum(item["passed"] for item in capabilities.values()),
            "failed_cases": max(
                0,
                total - sum(item["passed"] for item in capabilities.values()),
            ),
            "evaluation_runs": max(
                (item["runs"] for item in capabilities.values()),
                default=0,
            ),
            "average_latency_ms": round(
                max(0.0, float(result.get("average_latency_ms") or 0.0)),
                3,
            ),
            "failure_reasons": sorted(set(reasons)),
            "content_logged": False,
            "training_used": False,
            "raw_adapter_modes_excluded": True,
            "evaluation_only": True,
        }

    def record(self, result: dict[str, Any]) -> dict[str, Any]:
        """Merge evaluated capabilities without persisting prompts or output."""

        if not self.enabled:
            return {"enabled": False, "content_logged": False}
        incoming = self._public_record(result)
        key = _normalized_key(incoming["provider_id"], incoming["model_id"])
        with self._lock:
            existing = dict(self._records.get(key) or {})
            prior_evaluation_runs = max(
                1,
                int(existing.get("evaluation_runs") or 1),
            )
            latest_evaluation_runs = max(
                1,
                int(incoming.get("evaluation_runs") or 1),
            )
            if existing:
                incoming["average_latency_ms"] = (
                    float(existing.get("average_latency_ms") or 0)
                    * prior_evaluation_runs
                    + float(incoming.get("average_latency_ms") or 0)
                    * latest_evaluation_runs
                ) / (prior_evaluation_runs + latest_evaluation_runs)
            merged_capabilities = dict(existing.get("capabilities") or {})
            for name, latest in dict(incoming.get("capabilities") or {}).items():
                prior = dict(merged_capabilities.get(name) or {})
                if not prior:
                    merged_capabilities[name] = latest
                    continue
                prior_runs = max(1, int(prior.get("runs") or 1))
                latest_runs = max(1, int(latest.get("runs") or 1))
                combined_runs = prior_runs + latest_runs
                combined_score = (
                    float(prior.get("score") or 0) * prior_runs
                    + float(latest.get("score") or 0) * latest_runs
                ) / combined_runs
                merged_capabilities[name] = {
                    **latest,
                    "score": combined_score,
                    "last_score": float(
                        latest.get("last_score", latest.get("score") or 0)
                    ),
                    "runs": combined_runs,
                    "passed_runs": int(prior.get("passed_runs") or 0)
                    + int(latest.get("passed_runs") or 0),
                }
            incoming["capabilities"] = merged_capabilities
            incoming = self._public_record(incoming)
            self._records[key] = incoming
            self._save()
            return dict(incoming)

    def status(self) -> dict[str, Any]:
        with self._lock:
            records = [dict(value) for value in self._records.values()]
        recommendations = self.recommendations(records=records)
        return {
            "ok": self._load_error is None,
            "enabled": self.enabled,
            "schema_version": CAPABILITY_EVAL_SCHEMA_VERSION,
            "engine_version": CAPABILITY_EVAL_ENGINE_VERSION,
            "pack_version": CAPABILITY_PACK_VERSION,
            "record_count": len(records),
            "records": records,
            "recommendations": recommendations,
            "load_error": self._load_error,
            "content_logged": False,
            "training_used": False,
            "raw_adapter_modes_excluded": True,
            "evaluation_only": True,
        }

    def recommendations(
        self,
        *,
        records: list[dict[str, Any]] | None = None,
        minimum_runs: int | None = None,
    ) -> dict[str, Any]:
        """Return evidence-gated model advice without changing routing."""

        required_runs = (
            _environment_int("NOVA_CAPABILITY_RECOMMENDATION_MIN_RUNS", 3, 2, 10)
            if minimum_runs is None
            else max(2, min(int(minimum_runs), 10))
        )
        if records is None:
            with self._lock:
                active_records = [dict(value) for value in self._records.values()]
        else:
            active_records = list(records)
        candidates: dict[str, list[dict[str, Any]]] = {}
        pending: set[str] = set()
        for record in active_records:
            if str(record.get("role") or "") == "raw":
                continue
            for capability, score_record in dict(record.get("capabilities") or {}).items():
                if not isinstance(score_record, dict):
                    continue
                runs = max(1, int(score_record.get("runs") or 1))
                score = max(0.0, min(float(score_record.get("score") or 0), 1.0))
                if runs < required_runs:
                    pending.add(str(capability))
                    continue
                candidates.setdefault(str(capability), []).append(
                    {
                        "provider_id": str(record.get("provider_id") or "unknown"),
                        "model_id": str(record.get("model_id") or "unknown"),
                        "role": str(record.get("role") or "managed"),
                        "score": round(score, 3),
                        "runs": runs,
                        "average_latency_ms": float(
                            record.get("average_latency_ms") or 0
                        ),
                    }
                )
        items: list[dict[str, Any]] = []
        no_qualified_model: list[str] = []
        for capability, options in sorted(candidates.items()):
            ranked = sorted(
                options,
                key=lambda item: (
                    -item["score"],
                    item["average_latency_ms"],
                    item["model_id"],
                ),
            )
            best = ranked[0]
            if best["score"] < 0.5:
                no_qualified_model.append(capability)
                continue
            items.append(
                {
                    "task_type": {
                        "instruction_following": "general",
                        "conversation_continuity": "conversation",
                        "reasoning": "reasoning",
                        "coding": "coding",
                        "image_understanding": "vision",
                    }.get(capability, capability),
                    "capability": capability,
                    "provider_id": best["provider_id"],
                    "model_id": best["model_id"],
                    "score": best["score"],
                    "runs": best["runs"],
                    "reason": "highest_repeated_local_capability_score",
                    "alternatives_compared": max(0, len(ranked) - 1),
                }
            )
        return {
            "status": "ready" if items else "collecting_evidence",
            "minimum_runs": required_runs,
            "items": items,
            "pending_capabilities": sorted(pending),
            "no_qualified_model": sorted(no_qualified_model),
            "advisory_only": True,
            "automatic_routing": False,
            "training_used": False,
            "raw_adapter_modes_excluded": True,
        }

    def shadow_recommendation(self, task_type: str) -> dict[str, Any]:
        """Return one evidence-only recommendation without changing a route."""

        requested = str(task_type or "general").strip().lower()
        if requested not in {"general", "conversation", "reasoning", "coding", "vision"}:
            requested = "general"
        recommendations = self.recommendations()
        match = next(
            (
                dict(item)
                for item in recommendations.get("items", [])
                if str(item.get("task_type") or "") == requested
            ),
            None,
        )
        if match is None:
            no_qualified = set(recommendations.get("no_qualified_model") or [])
            capability = {
                "general": "instruction_following",
                "conversation": "conversation_continuity",
                "reasoning": "reasoning",
                "coding": "coding",
                "vision": "image_understanding",
            }[requested]
            status = (
                "no_qualified_model"
                if capability in no_qualified
                else "insufficient_evidence"
            )
            return {
                "status": status,
                "task_type": requested,
                "recommended_provider": None,
                "recommended_model": None,
                "score": None,
                "runs": 0,
                "minimum_runs": recommendations["minimum_runs"],
                "advisory_only": True,
                "automatic_routing": False,
                "route_changed": False,
                "training_used": False,
                "content_logged": False,
                "raw_adapter_modes_excluded": True,
            }
        return {
            "status": "evidence_match",
            "task_type": requested,
            "capability": match.get("capability"),
            "recommended_provider": match.get("provider_id"),
            "recommended_model": match.get("model_id"),
            "score": match.get("score"),
            "runs": match.get("runs"),
            "minimum_runs": recommendations["minimum_runs"],
            "reason": match.get("reason"),
            "advisory_only": True,
            "automatic_routing": False,
            "route_changed": False,
            "training_used": False,
            "content_logged": False,
            "raw_adapter_modes_excluded": True,
        }

    def middle_tier_qualification(
        self,
        provider_id: str,
        model_id: str,
        task_type: str = "general",
        *,
        minimum_score: float = 0.85,
        minimum_runs: int = 3,
    ) -> dict[str, Any]:
        """Return an enforceable decision only after the full v2 pack was run.

        Legacy or absent evidence remains advisory so upgrades do not make an
        otherwise working installation unusable. Once the larger qualification
        pack exists, an underperforming build is kept out of the middle tier.
        """

        key = _normalized_key(provider_id, model_id)
        with self._lock:
            record = dict(self._records.get(key) or {})
        base = {
            "provider_id": str(provider_id or "unknown"),
            "model_id": str(model_id or "unknown"),
            "task_type": str(task_type or "general").strip().lower(),
            "enforced": False,
            "eligible": None,
            "status": "not_evaluated",
            "minimum_score": round(
                max(0.5, min(float(minimum_score), 1.0)),
                3,
            ),
            "minimum_runs": max(2, min(int(minimum_runs), 10)),
            "content_logged": False,
            "route_changed": False,
        }
        if not record:
            return base
        full_pack_evidence = (
            str(record.get("pack_version") or "") == CAPABILITY_PACK_VERSION
            and int(record.get("case_count") or 0) >= 20
            and int(record.get("evaluation_runs") or 0) >= base["minimum_runs"]
        )
        if not full_pack_evidence:
            return {
                **base,
                "status": "legacy_or_insufficient_evidence",
                "overall_score": float(record.get("overall_score") or 0),
                "evaluation_runs": int(record.get("evaluation_runs") or 0),
            }
        capability_name = {
            "coding": "coding",
            "reasoning": "reasoning",
            "conversation": "conversation_continuity",
        }.get(base["task_type"], "instruction_following")
        capabilities = dict(record.get("capabilities") or {})
        target = dict(capabilities.get(capability_name) or {})
        critical_names = (
            "instruction_following",
            "conversation_continuity",
            "reasoning",
            "coding",
            "structured_output",
        )
        critical_scores = [
            float(dict(capabilities.get(name) or {}).get("score") or 0)
            for name in critical_names
        ]
        overall = float(record.get("overall_score") or 0)
        target_score = float(target.get("score") or 0)
        critical_floor = min(critical_scores, default=0.0)
        eligible = (
            overall >= base["minimum_score"]
            and target_score >= 0.8
            and critical_floor >= 0.75
        )
        return {
            **base,
            "enforced": True,
            "eligible": eligible,
            "status": "qualified" if eligible else "not_qualified",
            "overall_score": round(overall, 3),
            "target_capability": capability_name,
            "target_score": round(target_score, 3),
            "critical_capability_floor": round(critical_floor, 3),
            "evaluation_runs": int(record.get("evaluation_runs") or 0),
            "pack_version": str(record.get("pack_version") or ""),
        }


_DEFAULT_STORE: NovaCapabilityEvaluationStore | None = None
_DEFAULT_STORE_LOCK = RLock()


def get_default_capability_evaluation_store(
    root: str | Path | None = None,
) -> NovaCapabilityEvaluationStore:
    global _DEFAULT_STORE
    with _DEFAULT_STORE_LOCK:
        if _DEFAULT_STORE is None:
            base = Path(root) if root is not None else Path(__file__).resolve().parents[1]
            path = os.environ.get("NOVA_CAPABILITY_EVAL_PATH") or (
                base / "data" / "nova_capability_evaluations.json"
            )
            _DEFAULT_STORE = NovaCapabilityEvaluationStore(path)
        return _DEFAULT_STORE


def evaluate_loaded_text_models(
    provider_registry: Any,
    *,
    quality_registry: Any = None,
    store: NovaCapabilityEvaluationStore | None = None,
    maximum_models: int | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Evaluate currently resident managed text models through the provider API."""

    from nova_model_memory import (
        configured_ollama_model_role,
        list_ollama_loaded_models,
        managed_model_residency,
    )

    active_store = store or get_default_capability_evaluation_store()
    maximum = (
        _environment_int("NOVA_CAPABILITY_EVAL_MAX_MODELS", 3, 1, 8)
        if maximum_models is None
        else max(1, min(int(maximum_models), 8))
    )
    timeout = (
        _environment_int("NOVA_CAPABILITY_EVAL_TIMEOUT_SECONDS", 60, 5, 60)
        if timeout_seconds is None
        else max(5, min(int(timeout_seconds), 60))
    )
    cases = builtin_text_cases()
    provider = provider_registry.get_provider("ollama")
    loaded = list_ollama_loaded_models()
    results: list[dict[str, Any]] = []
    attempted = 0
    evaluated = 0
    for item in sorted(loaded, key=lambda value: str(value.get("name") or "")):
        if attempted >= maximum:
            break
        model_id = str(item.get("name") or "").strip()
        role = configured_ollama_model_role(model_id)
        if not model_id:
            continue
        if role == "raw":
            results.append(
                {
                    "provider_id": "ollama",
                    "model_id": model_id,
                    "role": role,
                    "status": "skipped_raw_user_model",
                    "content_logged": False,
                }
            )
            continue
        if role == "vision":
            continue
        if quality_registry is not None and quality_registry.is_quarantined(
            "ollama",
            model_id,
        ):
            results.append(
                {
                    "provider_id": "ollama",
                    "model_id": model_id,
                    "role": role,
                    "status": "skipped_quarantined",
                    "content_logged": False,
                }
            )
            continue
        attempted += 1
        capability_totals: dict[str, dict[str, Any]] = {}
        failure_reasons: list[str] = []
        latencies: list[float] = []
        with managed_model_residency(
            model_id,
            target_family=role,
            estimated_model_bytes=int(item.get("size_bytes") or 0),
        ) as residency:
            if not residency.get("allowed"):
                results.append(
                    {
                        "provider_id": "ollama",
                        "model_id": model_id,
                        "role": role,
                        "status": "resource_blocked",
                        "content_logged": False,
                    }
                )
                continue
            for case in cases:
                started = time.monotonic()
                score = 0.0
                reason = "generation_failed"
                try:
                    response = provider.generate(case.request(model_id, timeout))
                    output = str(getattr(response, "content", "") or "")
                    if str(getattr(response, "finish_reason", "") or "") == "length":
                        reason = "token_limit"
                    else:
                        score, reason = case.scorer(output)
                except Exception as error:
                    reason = (
                        "timeout"
                        if "timed out" in str(error).lower()
                        or "timeout" in str(error).lower()
                        else "generation_failed"
                    )
                latency_ms = (time.monotonic() - started) * 1000
                latencies.append(latency_ms)
                current = capability_totals.setdefault(
                    case.capability,
                    {
                        "score_sum": 0.0,
                        "passed": 0,
                        "total": 0,
                        "evaluated_at": _iso_now(),
                    },
                )
                current["score_sum"] += score
                current["passed"] += int(score >= 1.0)
                current["total"] += 1
                if score < 1.0:
                    failure_reasons.append(_safe_reason(reason))
                # Provider output is intentionally discarded here.
                output = ""
        capabilities = {
            name: {
                "score": values["score_sum"] / max(1, values["total"]),
                "passed": values["passed"],
                "total": values["total"],
                "evaluated_at": values["evaluated_at"],
            }
            for name, values in capability_totals.items()
        }
        recorded = active_store.record(
            {
                "provider_id": "ollama",
                "model_id": model_id,
                "role": role,
                "capabilities": capabilities,
                "average_latency_ms": (
                    sum(latencies) / len(latencies) if latencies else 0.0
                ),
                "failure_reasons": failure_reasons,
            }
        )
        results.append({**recorded, "status": "evaluated"})
        evaluated += 1
    return {
        "ok": True,
        "evaluated_models": evaluated,
        "attempted_models": attempted,
        "results": results,
        "store": active_store.status(),
        "content_logged": False,
        "training_used": False,
        "raw_adapter_modes_excluded": True,
        "evaluation_only": True,
    }


def qualify_text_model(
    provider_registry: Any,
    *,
    model_id: str,
    role: str = "middle",
    quality_registry: Any = None,
    store: NovaCapabilityEvaluationStore | None = None,
    repeated_runs: int = 3,
    timeout_seconds: int = 60,
    minimum_score: float = 0.85,
) -> dict[str, Any]:
    """Run the larger repeated pack against one explicitly selected local model.

    The returned and persisted result is content-free. A passing result is
    advisory evidence that the model is suitable for Nova's replaceable middle
    tier; it never changes the primary model or bypasses Nova Core.
    """

    from nova_model_memory import managed_model_residency

    selected_model = str(model_id or "").strip()
    selected_role = str(role or "middle").strip().lower()
    if not selected_model:
        raise ValueError("model_id is required")
    if selected_role == "raw":
        return {
            "ok": False,
            "status": "raw_model_excluded",
            "provider_id": "ollama",
            "model_id": selected_model,
            "eligible_for_middle": False,
            "content_logged": False,
            "training_used": False,
            "raw_adapter_modes_excluded": True,
            "evaluation_only": True,
        }

    runs = max(2, min(int(repeated_runs), 5))
    timeout = max(5, min(int(timeout_seconds), 60))
    threshold = max(0.5, min(float(minimum_score), 1.0))
    provider = provider_registry.get_provider("ollama")
    installed = {
        str(getattr(item, "model_id", "") or "").strip().lower().removesuffix(":latest")
        for item in provider.list_models()
    }
    normalized_model = selected_model.lower().removesuffix(":latest")
    if normalized_model not in installed:
        return {
            "ok": False,
            "status": "model_unavailable",
            "provider_id": "ollama",
            "model_id": selected_model,
            "eligible_for_middle": False,
            "content_logged": False,
            "training_used": False,
            "raw_adapter_modes_excluded": True,
            "evaluation_only": True,
        }
    if quality_registry is not None and quality_registry.is_quarantined(
        "ollama",
        selected_model,
    ):
        return {
            "ok": False,
            "status": "model_quarantined",
            "provider_id": "ollama",
            "model_id": selected_model,
            "eligible_for_middle": False,
            "content_logged": False,
            "training_used": False,
            "raw_adapter_modes_excluded": True,
            "evaluation_only": True,
        }

    active_store = store or get_default_capability_evaluation_store()
    cases = qualification_text_cases()
    run_summaries: list[dict[str, Any]] = []
    all_latencies: list[float] = []
    total_passed = 0
    total_attempted = 0
    failure_reasons: list[str] = []
    estimated_bytes = 0
    for item in provider.list_models():
        if (
            str(getattr(item, "model_id", "") or "")
            .strip()
            .lower()
            .removesuffix(":latest")
            == normalized_model
        ):
            estimated_bytes = int(
                (getattr(item, "metadata", {}) or {}).get("size") or 0
            )
            break

    with managed_model_residency(
        selected_model,
        target_family=selected_role,
        estimated_model_bytes=estimated_bytes,
    ) as residency:
        if not residency.get("allowed"):
            return {
                "ok": False,
                "status": "resource_blocked",
                "provider_id": "ollama",
                "model_id": selected_model,
                "eligible_for_middle": False,
                "content_logged": False,
                "training_used": False,
                "raw_adapter_modes_excluded": True,
                "evaluation_only": True,
            }
        for run_index in range(1, runs + 1):
            capability_totals: dict[str, dict[str, Any]] = {}
            run_latencies: list[float] = []
            run_failures: list[str] = []
            for case in cases:
                started = time.monotonic()
                score = 0.0
                reason = "generation_failed"
                try:
                    response = provider.generate(case.request(selected_model, timeout))
                    output = str(getattr(response, "content", "") or "")
                    if str(getattr(response, "finish_reason", "") or "") == "length":
                        reason = "token_limit"
                    else:
                        score, reason = case.scorer(output)
                except Exception as error:
                    reason = (
                        "timeout"
                        if "timed out" in str(error).lower()
                        or "timeout" in str(error).lower()
                        else "generation_failed"
                    )
                latency_ms = (time.monotonic() - started) * 1000
                run_latencies.append(latency_ms)
                all_latencies.append(latency_ms)
                total_attempted += 1
                total_passed += int(score >= 1.0)
                current = capability_totals.setdefault(
                    case.capability,
                    {
                        "score_sum": 0.0,
                        "passed": 0,
                        "total": 0,
                        "evaluated_at": _iso_now(),
                    },
                )
                current["score_sum"] += score
                current["passed"] += int(score >= 1.0)
                current["total"] += 1
                if score < 1.0:
                    safe_reason = _safe_reason(reason)
                    run_failures.append(safe_reason)
                    failure_reasons.append(safe_reason)
                # Do not persist or return provider output.
                output = ""
            capabilities = {
                name: {
                    "score": values["score_sum"] / max(1, values["total"]),
                    "passed": values["passed"],
                    "total": values["total"],
                    "evaluated_at": values["evaluated_at"],
                }
                for name, values in capability_totals.items()
            }
            recorded = active_store.record(
                {
                    "provider_id": "ollama",
                    "model_id": selected_model,
                    "role": selected_role,
                    "capabilities": capabilities,
                    "average_latency_ms": (
                        sum(run_latencies) / len(run_latencies)
                        if run_latencies
                        else 0.0
                    ),
                    "failure_reasons": run_failures,
                }
            )
            run_summaries.append(
                {
                    "run": run_index,
                    "score": round(
                        sum(
                            float(item.get("score") or 0)
                            * int(item.get("total") or 0)
                            for item in capabilities.values()
                        )
                        / max(
                            1,
                            sum(
                                int(item.get("total") or 0)
                                for item in capabilities.values()
                            ),
                        ),
                        3,
                    ),
                    "passed_cases": sum(
                        int(item.get("passed") or 0)
                        for item in capabilities.values()
                    ),
                    "case_count": len(cases),
                    "capabilities": {
                        name: round(float(item.get("score") or 0), 3)
                        for name, item in capabilities.items()
                    },
                    "average_latency_ms": round(
                        sum(run_latencies) / len(run_latencies)
                        if run_latencies
                        else 0.0,
                        3,
                    ),
                    "failure_reasons": sorted(set(run_failures)),
                }
            )

    overall_score = total_passed / max(1, total_attempted)
    required_capabilities = {
        "instruction_following",
        "conversation_continuity",
        "reasoning",
        "coding",
        "structured_output",
    }
    capability_scores: dict[str, float] = {}
    for capability in required_capabilities:
        scores = [
            float(run["capabilities"].get(capability, 0))
            for run in run_summaries
        ]
        capability_scores[capability] = (
            sum(scores) / len(scores) if scores else 0.0
        )
    critical_floor = min(capability_scores.values(), default=0.0)
    consistent = all(run["score"] >= threshold for run in run_summaries)
    blocking_failures = {
        "empty_response",
        "generation_failed",
        "invalid_json",
        "timeout",
        "token_limit",
    }.intersection(failure_reasons)
    eligible = (
        overall_score >= threshold
        and critical_floor >= 0.75
        and consistent
        and not blocking_failures
    )
    average_latency = (
        sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
    )
    if quality_registry is not None:
        if eligible:
            quality_registry.record_success(
                "ollama",
                selected_model,
                latency_ms=average_latency,
                quality_score=overall_score,
                source="capability_eval",
                verified=True,
            )
        else:
            # One aggregate failure cannot immediately quarantine a model.
            quality_registry.record_failure(
                "ollama",
                selected_model,
                reason=(
                    "timeout"
                    if "timeout" in failure_reasons
                    else "benchmark_output_mismatch"
                ),
                latency_ms=average_latency,
                source="capability_eval",
            )
    return {
        "ok": True,
        "status": "qualified" if eligible else "not_qualified",
        "provider_id": "ollama",
        "model_id": selected_model,
        "role": selected_role,
        "pack_version": CAPABILITY_PACK_VERSION,
        "repeated_runs": runs,
        "case_count_per_run": len(cases),
        "attempted_cases": total_attempted,
        "passed_cases": total_passed,
        "overall_score": round(overall_score, 3),
        "minimum_score": threshold,
        "critical_capability_floor": round(critical_floor, 3),
        "capabilities": {
            name: round(score, 3)
            for name, score in sorted(capability_scores.items())
        },
        "consistent": consistent,
        "eligible_for_middle": eligible,
        "primary_model_changed": False,
        "route_changed": False,
        "average_latency_ms": round(average_latency, 3),
        "failure_reasons": sorted(set(failure_reasons)),
        "runs": run_summaries,
        "latest_record": recorded,
        "content_logged": False,
        "training_used": False,
        "raw_adapter_modes_excluded": True,
        "evaluation_only": True,
        "limitations": [
            "This bounded local pack is not a general intelligence or IQ test.",
            "Passing qualifies only the tested model build and local runtime.",
            "Nova remains the identity and control layer; the model is replaceable.",
        ],
    }


def _validated_image_data(image_base64: str) -> tuple[str, int]:
    value = str(image_base64 or "").strip()
    if "," in value and value.lower().startswith("data:"):
        value = value.split(",", 1)[1]
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as error:
        raise ValueError("Vision evaluation image is not valid base64.") from error
    if not decoded or len(decoded) > _MAX_VISION_BYTES:
        raise ValueError("Vision evaluation image must be between 1 byte and 5 MB.")
    if not (
        decoded.startswith(b"\xff\xd8\xff")
        or decoded.startswith(b"\x89PNG\r\n\x1a\n")
        or decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP"
    ):
        raise ValueError("Vision evaluation supports JPEG, PNG, or WebP images.")
    return value, len(decoded)


def _validated_keywords(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("Vision evaluation expected_keywords must be a list.")
    keywords = []
    for item in values[:5]:
        value = re.sub(r"[^a-z0-9 _-]+", "", str(item or "").strip().lower())[:32]
        if value and value not in keywords:
            keywords.append(value)
    if not keywords:
        raise ValueError("Vision evaluation requires at least one expected keyword.")
    return keywords


def evaluate_user_approved_vision(
    *,
    model_id: str,
    image_base64: str,
    expected_keywords: list[str],
    store: NovaCapabilityEvaluationStore | None = None,
    quality_registry: Any = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Score one explicitly approved local image without persisting its content."""

    from nova_model_memory import configured_ollama_base_url, managed_model_residency

    active_store = store or get_default_capability_evaluation_store()
    clean_image, image_bytes = _validated_image_data(image_base64)
    keywords = _validated_keywords(expected_keywords)
    selected_model = str(model_id or os.environ.get("NOVA_VISION_MODEL") or "moondream")
    if quality_registry is not None and quality_registry.is_quarantined(
        "ollama",
        selected_model,
    ):
        return {
            "ok": False,
            "status": "model_quarantined",
            "provider_id": "ollama",
            "model_id": selected_model,
            "content_logged": False,
            "image_persisted": False,
            "training_used": False,
        }
    timeout = (
        _environment_int("NOVA_CAPABILITY_EVAL_VISION_TIMEOUT_SECONDS", 60, 5, 120)
        if timeout_seconds is None
        else max(5, min(int(timeout_seconds), 120))
    )
    payload = {
        "model": selected_model,
        "prompt": (
            "Briefly describe the main visible subject in this image in one sentence. "
            "Do not mention this evaluation."
        ),
        "images": [clean_image],
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0,
            "seed": 0,
            "num_ctx": 2048,
            "num_predict": 64,
        },
    }
    started = time.monotonic()
    output = ""
    reason = "provider_error"
    score = 0.0
    with managed_model_residency(
        selected_model,
        target_family="vision",
        estimated_model_bytes=int(
            os.environ.get("NOVA_VISION_MODEL_ESTIMATED_BYTES", "1800000000")
            or 1_800_000_000
        ),
    ) as residency:
        if not residency.get("allowed"):
            return {
                "ok": False,
                "status": "resource_blocked",
                "provider_id": "ollama",
                "model_id": selected_model,
                "content_logged": False,
                "image_persisted": False,
                "training_used": False,
            }
        try:
            request = urllib.request.Request(
                configured_ollama_base_url() + "/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            output = str(response_payload.get("response") or "").strip()
            normalized_output = output.casefold()
            matched = sum(1 for keyword in keywords if keyword in normalized_output)
            score = matched / len(keywords)
            reason = "passed" if score >= 1.0 else (
                "empty_response" if not output else "vision_keyword_mismatch"
            )
        except Exception as error:
            reason = (
                "timeout"
                if "timed out" in str(error).lower()
                or "timeout" in str(error).lower()
                else "provider_error"
            )
    latency_ms = (time.monotonic() - started) * 1000
    recorded = active_store.record(
        {
            "provider_id": "ollama",
            "model_id": selected_model,
            "role": "vision",
            "capabilities": {
                "image_understanding": {
                    "score": score,
                    "passed": int(score >= 1.0),
                    "total": 1,
                    "evaluated_at": _iso_now(),
                }
            },
            "average_latency_ms": latency_ms,
            "failure_reasons": [] if score >= 1.0 else [reason],
        }
    )
    # Drop all content-bearing values before constructing the response.
    output = ""
    clean_image = ""
    payload.clear()
    return {
        "ok": True,
        "status": "evaluated",
        "provider_id": "ollama",
        "model_id": selected_model,
        "image_bytes": image_bytes,
        "score": score,
        "passed": score >= 1.0,
        "reason": reason,
        "record": recorded,
        "content_logged": False,
        "image_persisted": False,
        "output_persisted": False,
        "training_used": False,
        "raw_adapter_modes_excluded": True,
        "evaluation_only": True,
    }


def load_behavior_eval_bank(path: str | Path) -> Any:
    from nova_runtime.eval_bank import load_behavior_eval_bank as _load_behavior_eval_bank

    return _load_behavior_eval_bank(path)


def score_behavior_eval_bank(bank: Any, judge: Any) -> Any:
    from nova_runtime.eval_bank import score_behavior_eval_bank as _score_behavior_eval_bank

    return _score_behavior_eval_bank(bank, judge)
