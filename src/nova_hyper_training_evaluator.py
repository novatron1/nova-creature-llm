from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch

from nova_checkpoint_registry import CheckpointRegistry, sha256
from nova_torch_transformer import load_checkpoint
from nova_training_types import DOMAIN_NAMES, ROLE_NAMES, PromotionDecision, RoutePrediction

PROMOTION_GAIN_FLOOR = 2.0
PROMOTION_ELITE_JOINT = 95.0
PROTECTED_DOMAIN_FLOOR_DELTA = -1.0
REPETITION_RATE_CEILING = 0.02


def evaluate_routes(route_model: Any, cases: Sequence[Any]) -> dict:
    rows = _coerce_nonempty_cases(cases, "cases")
    true_roles: list[str] = []
    predicted_roles: list[str] = []
    true_domains: list[str] = []
    predicted_domains: list[str] = []
    protected_deltas: list[float] = []
    protected_support = 0
    errors: list[str] = []

    for index, case in enumerate(rows):
        text = _case_text(case)
        expected_role = _case_value(case, "primary_role", _case_value(case, "role", "speech_output_transformer"))
        expected_domain = _case_value(case, "domain", "general")
        true_roles.append(str(expected_role))
        true_domains.append(str(expected_domain))

        try:
            prediction = _coerce_route_prediction(_predict_route(route_model, text))
            predicted_roles.append(prediction.primary_role)
            predicted_domains.append(prediction.domain)
        except Exception as exc:
            predicted_roles.append("__route_error__")
            predicted_domains.append("__route_error__")
            errors.append(f"case {index}: {exc}")

        if _case_value(case, "protected", False):
            protected_support += 1
            baseline_score = _optional_float(_case_value(case, "baseline_domain_score", None))
            if baseline_score is not None:
                current_score = 100.0 if predicted_domains[-1] == str(expected_domain) else 0.0
                protected_deltas.append(current_score - baseline_score)

    macro_f1 = _macro_f1(true_roles, predicted_roles)
    domain_accuracy = _accuracy(true_domains, predicted_domains)
    protected_delta = min(protected_deltas) if protected_deltas else 0.0
    return {
        "macro_f1": macro_f1,
        "primary_role_macro_f1": macro_f1,
        "domain_accuracy": domain_accuracy,
        "protected_domain_floor_delta": protected_delta,
        "protected_support": protected_support,
        "support": len(rows),
        "errors": errors,
    }


def evaluate_answers(runtime: Any, cases: Sequence[Any]) -> dict:
    rows = _coerce_nonempty_cases(cases, "cases")
    correct = 0
    malformed = 0
    repetitive = 0
    protected_total = 0
    protected_correct = 0
    traces: list[dict] = []

    for case in rows:
        prompt = str(_case_value(case, "prompt", _case_value(case, "text", "")))
        role = str(_case_value(case, "role", "left_hemisphere"))
        max_new_tokens = int(_case_value(case, "max_new_tokens", 80))
        error = None
        try:
            result = runtime.generate(role, prompt, max_new_tokens=max_new_tokens)
            text = str(getattr(result, "text", "") or "")
            ok = _strict_bool(getattr(result, "ok", False))
            error = getattr(result, "error", None)
            malformed_output = (not ok) or (not text.strip()) or bool(error)
            case_correct = (not malformed_output) and _answer_matches(case, text)
        except Exception as exc:
            text = ""
            ok = False
            error = str(exc)
            malformed_output = True
            case_correct = False
        is_protected = bool(_case_value(case, "protected", False))
        repeated = _is_repetitive_output(text)

        correct += int(case_correct)
        malformed += int(malformed_output)
        repetitive += int(repeated)
        protected_total += int(is_protected)
        protected_correct += int(is_protected and case_correct)
        traces.append(
            {
                "prompt": prompt,
                "role": role,
                "ok": ok,
                "correct": case_correct,
                "malformed": malformed_output,
                "repetitive": repeated,
                "error": error,
            }
        )

    total = len(rows)
    return {
        "composite": 100.0 * correct / total,
        "protected_perfect": protected_total > 0 and protected_correct == protected_total,
        "protected_support": protected_total,
        "malformed_rate": malformed / total,
        "repetition_rate": repetitive / total,
        "support": total,
        "traces": traces,
    }


def evaluate_stability(runtime: Any, regression_result: Any) -> dict:
    result = regression_result if isinstance(regression_result, Mapping) else {}
    reload_ok = _bool_or_runtime(result, runtime, "reload_ok", ("check_reload", "reload_ok"))
    load_ok = _bool_or_runtime(result, runtime, "load_ok", ("check_load", "load_ok"), default=True)
    role_checkpoints_ok = _bool_or_runtime(
        result,
        runtime,
        "role_checkpoints_ok",
        ("check_role_checkpoints", "role_checkpoints_ok"),
        default=True,
    )
    roles_ok = _bool_or_runtime(result, runtime, "roles_ok", ("check_roles", "roles_ok"), default=True)
    role_ok = _bool_or_runtime(result, runtime, "role_ok", ("check_role", "role_ok"), default=True)
    confirmation_ok = _bool_or_runtime(
        result,
        runtime,
        "confirmation_ok",
        ("confirm_deterministic", "confirmation_ok"),
    )
    regressions = _regression_count(result.get("regressions", 0))
    regression_evidence_ok = regressions is not None
    regression_count = regressions if regressions is not None else 1

    score = 100.0
    if not reload_ok:
        score -= 45.0
    if not load_ok:
        score -= 25.0
    if not (role_checkpoints_ok and roles_ok and role_ok):
        score -= 25.0
    if not confirmation_ok:
        score -= 45.0
    if not regression_evidence_ok:
        score -= 100.0
    score -= min(10.0 * regression_count, 100.0)
    score = max(0.0, score)
    return {
        "reload_ok": reload_ok,
        "load_ok": load_ok,
        "role_checkpoints_ok": role_checkpoints_ok,
        "roles_ok": roles_ok,
        "role_ok": role_ok,
        "confirmation_ok": confirmation_ok,
        "regressions": regression_count,
        "regression_evidence_ok": regression_evidence_ok,
        "score": score,
    }


def decide_promotion(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    previous_winner: Mapping[str, Any] | None,
) -> PromotionDecision:
    baseline_joint = _joint_metric(baseline)
    candidate_joint = _joint_metric(candidate)
    previous_winner_joint = _joint_metric(previous_winner) if previous_winner is not None else None
    reference_joint = max(
        baseline_joint,
        previous_winner_joint if previous_winner_joint is not None else float("-inf"),
    )

    reasons: list[str] = []
    if not (candidate_joint - reference_joint >= PROMOTION_GAIN_FLOOR or candidate_joint >= PROMOTION_ELITE_JOINT):
        reasons.append(
            f"joint score gain {candidate_joint - reference_joint:.2f} is below {PROMOTION_GAIN_FLOOR:.1f}"
        )

    baseline_route = _nested_float(baseline, ("routing", "macro_f1"), 0.0)
    candidate_route = _nested_float(candidate, ("routing", "macro_f1"), 0.0)
    if candidate_route <= baseline_route:
        reasons.append(f"route macro F1 did not improve ({candidate_route:.2f} <= {baseline_route:.2f})")

    baseline_answer = _nested_float(baseline, ("answers", "composite"), 0.0)
    candidate_answer = _nested_float(candidate, ("answers", "composite"), 0.0)
    if candidate_answer <= baseline_answer:
        reasons.append(f"answer composite did not improve ({candidate_answer:.2f} <= {baseline_answer:.2f})")

    protected_delta = _nested_float(candidate, ("routing", "protected_domain_floor_delta"), float("-inf"))
    if protected_delta < PROTECTED_DOMAIN_FLOOR_DELTA:
        reasons.append(f"protected domain floor fell by {protected_delta:.2f} points")

    if _nested_int(candidate, ("routing", "protected_support"), 1) <= 0:
        reasons.append("route protected support is zero")

    if _nested_int(candidate, ("answers", "protected_support"), 1) <= 0:
        reasons.append("answer protected support is zero")

    if not _nested_bool(candidate, ("answers", "protected_perfect"), False):
        reasons.append("protected answer facts are not perfect")

    baseline_malformed = _nested_float(baseline, ("answers", "malformed_rate"), 1.0)
    candidate_malformed = _nested_float(candidate, ("answers", "malformed_rate"), 1.0)
    if candidate_malformed > baseline_malformed:
        reasons.append(
            f"malformed output rate increased ({candidate_malformed:.4f} > {baseline_malformed:.4f})"
        )

    baseline_repetition = _nested_float(baseline, ("answers", "repetition_rate"), 1.0)
    candidate_repetition = _nested_float(candidate, ("answers", "repetition_rate"), 1.0)
    if candidate_repetition > baseline_repetition:
        reasons.append(
            f"repetition rate increased ({candidate_repetition:.4f} > {baseline_repetition:.4f})"
        )
    if candidate_repetition >= REPETITION_RATE_CEILING:
        reasons.append(f"repetition rate {candidate_repetition:.4f} is not below {REPETITION_RATE_CEILING:.2f}")

    if not _nested_bool(candidate, ("stability", "reload_ok"), False):
        reasons.append("reload gate failed")
    stability = _mapping(candidate.get("stability", {}))
    if not _stability_gate_ok(stability, ("load_ok",)):
        reasons.append("load gate failed")
    if not _stability_gate_ok(stability, ("role_checkpoints_ok", "roles_ok", "role_ok")):
        reasons.append("role checkpoint gate failed")
    if not _nested_bool(candidate, ("stability", "confirmation_ok"), False):
        reasons.append("deterministic confirmation failed")
    regressions = _regression_count(_nested_value(candidate, ("stability", "regressions"), 1))
    if regressions is None:
        reasons.append("invalid regression evidence")
    elif regressions != 0:
        reasons.append(f"regression count is {regressions}, expected zero")

    training = _mapping(candidate.get("training", {}))
    if bool(training.get("promotion_data_leak") or training.get("data_leak_detected")):
        reasons.append("promotion data leak detected")

    routing = _mapping(candidate.get("routing", {}))
    if routing.get("checkpoint_evidence_ok") is False or routing.get("transformer_source_without_checkpoint"):
        reasons.append("router claimed transformer source without checkpoint evidence")

    verdict = "REJECTED" if reasons else "PROMOTED"
    return PromotionDecision(
        verdict,
        tuple(reasons or ("all promotion gates passed",)),
        baseline_joint,
        candidate_joint,
        previous_winner_joint,
    )


def run_negative_controls(project_root: str | Path, cases: Any) -> dict:
    root = Path(project_root)
    case_map = cases if isinstance(cases, Mapping) else {"routes": cases}
    baseline = _mapping(case_map.get("baseline", _default_metrics()))
    controls: dict[str, dict] = {}

    route_cases = list(case_map.get("routes", ()))
    if len(route_cases) >= 2:
        model = _MemorizedRouteModel(route_cases)
        original_route = evaluate_routes(model, route_cases)
        shuffled_cases = _shuffled_route_cases(route_cases)
        shuffled_route = evaluate_routes(model, shuffled_cases)
        shuffled_route["original_macro_f1"] = original_route["macro_f1"]
        shuffled_route["corrupted"] = _route_cases_corrupted(route_cases, shuffled_cases)
        candidate = _candidate_from_parts(baseline, routing=shuffled_route)
        decision = decide_promotion(baseline, candidate, None)
        rejected = decision.verdict == "REJECTED" and shuffled_route["macro_f1"] < original_route["macro_f1"]
        controls["shuffled_route_labels"] = _control_result(rejected, decision, shuffled_route)
    else:
        controls["shuffled_route_labels"] = _control_result(False, None, {"error": "not enough route cases"})

    absent_evidence = _exercise_absent_checkpoint_control(root)
    candidate = _candidate_from_parts(
        baseline,
        stability={
            "reload_ok": absent_evidence["ok"],
            "confirmation_ok": True,
            "regressions": 0,
            "score": 55.0,
        },
    )
    absent_decision = decide_promotion(baseline, candidate, None)
    controls["absent_checkpoints"] = _control_result(
        absent_decision.verdict == "REJECTED",
        absent_decision,
        {"checkpoint_error_observed": not absent_evidence["ok"]},
        error=absent_evidence["error"],
    )

    invalid_evidence = _exercise_invalid_checkpoint_payload_control(root)
    candidate = _candidate_from_parts(
        baseline,
        stability={
            "load_ok": invalid_evidence["ok"],
            "confirmation_ok": True,
            "regressions": 0,
            "score": 75.0,
        },
    )
    invalid_decision = decide_promotion(baseline, candidate, None)
    controls["invalid_checkpoint_payloads"] = _control_result(
        invalid_decision.verdict == "REJECTED",
        invalid_decision,
        {"checkpoint_error_observed": not invalid_evidence["ok"]},
        error=invalid_evidence["error"],
    )

    candidate = _candidate_from_parts(
        baseline,
        answers={"composite": 90.0, "protected_perfect": True, "malformed_rate": 0.0, "repetition_rate": 0.5},
    )
    controls["repetitive_output"] = _control_result(decide_promotion(baseline, candidate, None).verdict == "REJECTED")

    candidate = _candidate_from_parts(
        baseline,
        answers={"composite": 0.0, "protected_perfect": False, "malformed_rate": 1.0, "repetition_rate": 0.0},
    )
    controls["empty_output"] = _control_result(decide_promotion(baseline, candidate, None).verdict == "REJECTED")

    candidate = _candidate_from_parts(
        baseline,
        routing={"macro_f1": 0.0, "protected_domain_floor_delta": 0.0},
        answers={"composite": 50.0, "protected_perfect": True, "malformed_rate": 0.0, "repetition_rate": 0.0},
    )
    controls["random_weights_candidate"] = _control_result(
        decide_promotion(baseline, candidate, None).verdict == "REJECTED"
    )

    candidate = _candidate_from_parts(
        baseline,
        training={"promotion_data_leak": True},
    )
    controls["promotion_data_leak"] = _control_result(decide_promotion(baseline, candidate, None).verdict == "REJECTED")

    candidate = _candidate_from_parts(
        baseline,
        routing={
            "macro_f1": _nested_float(baseline, ("routing", "macro_f1"), 80.0) + 3.0,
            "protected_domain_floor_delta": 0.0,
            "transformer_source_without_checkpoint": True,
        },
    )
    controls["transformer_source_without_checkpoint"] = _control_result(
        decide_promotion(baseline, candidate, None).verdict == "REJECTED"
    )

    return {
        "passed": all(item["rejected"] for item in controls.values()),
        "controls": controls,
    }


def _joint_metric(metrics: Mapping[str, Any] | None) -> float:
    if metrics is None:
        return float("-inf")
    routing_score = _nested_float(metrics, ("routing", "macro_f1"), 0.0)
    answer_score = _nested_float(metrics, ("answers", "composite"), 0.0)
    stability_score = _nested_float(metrics, ("stability", "score"), 0.0)
    return 0.50 * routing_score + 0.40 * answer_score + 0.10 * stability_score


def _candidate_from_parts(
    baseline: Mapping[str, Any],
    *,
    routing: Mapping[str, Any] | None = None,
    answers: Mapping[str, Any] | None = None,
    stability: Mapping[str, Any] | None = None,
    training: Mapping[str, Any] | None = None,
) -> dict:
    baseline_route = _nested_float(baseline, ("routing", "macro_f1"), 80.0)
    baseline_answer = _nested_float(baseline, ("answers", "composite"), 80.0)
    candidate = {
        "routing": {
            "macro_f1": baseline_route + 3.0,
            "protected_domain_floor_delta": 0.0,
        },
        "answers": {
            "composite": baseline_answer + 3.0,
            "protected_perfect": True,
            "protected_support": 1,
            "malformed_rate": _nested_float(baseline, ("answers", "malformed_rate"), 0.0),
            "repetition_rate": min(_nested_float(baseline, ("answers", "repetition_rate"), 0.0), 0.01),
        },
        "stability": {
            "reload_ok": True,
            "load_ok": True,
            "role_checkpoints_ok": True,
            "roles_ok": True,
            "role_ok": True,
            "confirmation_ok": True,
            "regressions": 0,
            "score": 100.0,
        },
    }
    if routing is not None:
        candidate["routing"].update(dict(routing))
    if answers is not None:
        candidate["answers"].update(dict(answers))
    if stability is not None:
        candidate["stability"].update(dict(stability))
    if training is not None:
        candidate["training"] = dict(training)
    candidate["routing"]["macro_f1"] = _clamp_score(candidate["routing"]["macro_f1"])
    candidate["answers"]["composite"] = _clamp_score(candidate["answers"]["composite"])
    candidate["stability"]["score"] = _clamp_score(candidate["stability"].get("score", 100.0))
    candidate["joint"] = (
        0.50 * float(candidate["routing"]["macro_f1"])
        + 0.40 * float(candidate["answers"]["composite"])
        + 0.10 * float(candidate["stability"].get("score", 100.0))
    )
    return candidate


def _default_metrics() -> dict:
    return {
        "joint": 80.0,
        "routing": {"macro_f1": 80.0, "protected_domain_floor_delta": 0.0},
        "answers": {
            "composite": 80.0,
            "protected_perfect": True,
            "malformed_rate": 0.0,
            "repetition_rate": 0.0,
        },
        "stability": {
            "reload_ok": True,
            "load_ok": True,
            "role_checkpoints_ok": True,
            "roles_ok": True,
            "role_ok": True,
            "confirmation_ok": True,
            "regressions": 0,
            "score": 100.0,
        },
    }


def _control_result(
    rejected: bool,
    decision: PromotionDecision | None = None,
    metrics: Mapping[str, Any] | None = None,
    *,
    error: str | None = None,
) -> dict:
    result = {"rejected": bool(rejected)}
    if decision is not None:
        result["decision"] = {
            "verdict": decision.verdict,
            "reasons": list(decision.reasons),
            "baseline_joint": decision.baseline_joint,
            "candidate_joint": decision.candidate_joint,
            "previous_winner_joint": decision.previous_winner_joint,
        }
    if metrics is not None:
        result["metrics"] = dict(metrics)
    if error is not None:
        result["error"] = str(error)
    return result


class _MemorizedRouteModel:
    def __init__(self, cases: Sequence[Any]):
        self._by_text = {
            _case_text(case): (
                str(_case_value(case, "domain", "general")),
                str(_case_value(case, "primary_role", _case_value(case, "role", "speech_output_transformer"))),
            )
            for case in cases
        }

    def predict(self, text: str) -> RoutePrediction:
        domain, role = self._by_text[str(text)]
        if domain not in DOMAIN_NAMES:
            domain = "general"
        if role not in ROLE_NAMES:
            role = "speech_output_transformer"
        return RoutePrediction(domain, role, (), 1.0, "e" * 64)


def _shuffled_route_cases(cases: Sequence[Any]) -> list[dict]:
    roles = [
        str(_case_value(case, "primary_role", _case_value(case, "role", "speech_output_transformer")))
        for case in cases
    ]
    shifted_roles = roles[1:] + roles[:1]
    shuffled = []
    for case, original_role, role in zip(cases, roles, shifted_roles):
        row = dict(case) if isinstance(case, Mapping) else {
            "text": _case_text(case),
            "domain": _case_value(case, "domain", "general"),
        }
        if role == original_role:
            role = _different_valid_role(original_role)
        row["primary_role"] = role
        shuffled.append(row)
    return shuffled


def _different_valid_role(role: str) -> str:
    for candidate_role in ROLE_NAMES:
        if candidate_role != role:
            return candidate_role
    return "speech_output_transformer"


def _route_cases_corrupted(original_cases: Sequence[Any], corrupted_cases: Sequence[Any]) -> bool:
    return any(
        str(_case_value(original, "primary_role", _case_value(original, "role", "speech_output_transformer")))
        != str(_case_value(corrupted, "primary_role", _case_value(corrupted, "role", "speech_output_transformer")))
        for original, corrupted in zip(original_cases, corrupted_cases)
    )


def _exercise_absent_checkpoint_control(project_root: Path) -> dict:
    control_root = _negative_control_root(project_root, "absent")
    role = "left_hemisphere"
    checkpoint_path = control_root / "checkpoints" / "brain_slots" / role / "missing_after_register.pt"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_bytes(b"negative-control-checkpoint-bytes")
    digest = sha256(checkpoint_path)
    registry = CheckpointRegistry(control_root)
    registry.register_baseline(role, checkpoint_path, digest)
    checkpoint_path.unlink()
    try:
        registry.resolve_live(role)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "error": "absent checkpoint unexpectedly resolved"}


def _exercise_invalid_checkpoint_payload_control(project_root: Path) -> dict:
    control_root = _negative_control_root(project_root, "invalid")
    checkpoint_path = control_root / "checkpoints" / "invalid_payload.pt"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"not": "a checkpoint"}, checkpoint_path)
    try:
        load_checkpoint(checkpoint_path)
    except Exception as exc:
        return {"ok": False, "error": f"invalid checkpoint payload: {exc}"}
    return {"ok": True, "error": "invalid checkpoint payload unexpectedly loaded"}


def _negative_control_root(project_root: Path, name: str) -> Path:
    root = project_root / "artifacts" / "negative_controls" / f"{name}_{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _predict_route(route_model: Any, text: str) -> Any:
    if hasattr(route_model, "predict") and callable(route_model.predict):
        return route_model.predict(text)
    if hasattr(route_model, "route") and callable(route_model.route):
        return route_model.route(text)
    if callable(route_model):
        return route_model(text)
    raise TypeError("route_model must expose predict(text), route(text), or be callable")


def _coerce_route_prediction(value: Any) -> RoutePrediction:
    if isinstance(value, RoutePrediction):
        return value
    if isinstance(value, Mapping):
        return RoutePrediction(
            value.get("domain", "general"),
            value.get("primary_role", "speech_output_transformer"),
            tuple(value.get("support_roles", ())),
            float(value.get("confidence", 0.0)),
            value.get("model_hash", "0" * 64),
            source=value.get("source", "learned_route_model"),
        )
    raise TypeError("route model returned an invalid prediction")


def _answer_matches(case: Any, text: str) -> bool:
    required_terms = _case_value(case, "required_terms", None)
    terms = _string_sequence(required_terms)
    if terms:
        lowered = text.lower()
        return all(term.lower() in lowered for term in terms)
    expected = _case_value(case, "expected", None)
    if expected is not None:
        return text.strip() == str(expected).strip()
    expected_contains = _case_value(case, "expected_contains", None)
    if expected_contains is not None:
        return str(expected_contains).lower() in text.lower()
    return bool(text.strip())


def _is_repetitive_output(text: str) -> bool:
    words = [word for word in text.lower().split() if word]
    if len(words) >= 4 and len(set(words)) <= 2:
        return True
    compact = "".join(text.lower().split())
    return len(compact) >= 8 and len(set(compact)) <= 2


def _bool_or_runtime(
    result: Mapping[str, Any],
    runtime: Any,
    key: str,
    runtime_names: Sequence[str],
    *,
    default: bool = False,
) -> bool:
    if key in result:
        return _strict_bool(result[key])
    for name in runtime_names:
        value = getattr(runtime, name, None)
        if callable(value):
            return _strict_bool(value())
        if isinstance(value, bool):
            return value
    return default


def _stability_gate_ok(stability: Mapping[str, Any], keys: Sequence[str]) -> bool:
    values = [stability[key] for key in keys if key in stability]
    if not values:
        return True
    return all(_strict_bool(value) for value in values)


def _nested_int(metrics: Mapping[str, Any], path: Sequence[str], default: int) -> int:
    value = _nested_value(metrics, path, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return default


def _regression_count(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return max(int(value), 0)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    return None


def _coerce_nonempty_cases(cases: Sequence[Any], field_name: str) -> list[Any]:
    rows = list(cases)
    if not rows:
        raise ValueError(f"{field_name} must not be empty")
    return rows


def _case_text(case: Any) -> str:
    value = _case_value(case, "text", _case_value(case, "prompt", None))
    if value is None or not str(value).strip():
        raise ValueError("case must include non-empty text or prompt")
    return str(value)


def _case_value(case: Any, key: str, default: Any = None) -> Any:
    if isinstance(case, Mapping):
        return case.get(key, default)
    return getattr(case, key, default)


def _string_sequence(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nested_value(metrics: Mapping[str, Any], path: Sequence[str], default: Any) -> Any:
    current: Any = metrics
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def _nested_float(metrics: Mapping[str, Any], path: Sequence[str], default: float) -> float:
    value = _optional_float(_nested_value(metrics, path, None))
    return default if value is None else value


def _nested_bool(metrics: Mapping[str, Any], path: Sequence[str], default: bool) -> bool:
    value = _nested_value(metrics, path, default)
    return _strict_bool(value)


def _strict_bool(value: Any) -> bool:
    return value if isinstance(value, bool) else False


def _clamp_score(value: Any) -> float:
    number = _optional_float(value)
    if number is None:
        return 0.0
    return max(0.0, min(100.0, number))


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _accuracy(truth: Sequence[str], predictions: Sequence[str]) -> float:
    if not truth:
        return 0.0
    return 100.0 * sum(1 for expected, actual in zip(truth, predictions) if expected == actual) / len(truth)


def _macro_f1(truth: Sequence[str], predictions: Sequence[str]) -> float:
    labels = set(truth) | set(predictions)
    if not labels:
        return 0.0
    scores = []
    for label in labels:
        tp = sum(1 for expected, actual in zip(truth, predictions) if expected == label and actual == label)
        fp = sum(1 for expected, actual in zip(truth, predictions) if expected != label and actual == label)
        fn = sum(1 for expected, actual in zip(truth, predictions) if expected == label and actual != label)
        denominator = (2 * tp) + fp + fn
        scores.append(0.0 if denominator == 0 else (2 * tp) / denominator)
    return 100.0 * sum(scores) / len(scores)
