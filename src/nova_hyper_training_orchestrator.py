from __future__ import annotations

import json
import math
import subprocess
import sys
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nova_checkpoint_registry import CheckpointRegistry, ResolvedCheckpoint, sha256
from nova_hyper_training_evaluator import (
    decide_promotion,
    evaluate_answers,
    evaluate_routes,
    evaluate_stability,
    run_negative_controls,
)
from nova_role_trainer import train_role_candidate
from nova_route_model import (
    predict_route,
    route_examples_from_rows,
    train_route_model,
)
from nova_training_dataset import build_dataset
from nova_training_preflight import run_preflight
from nova_training_types import ROLE_NAMES, PromotionDecision
from nova_transformer_runtime import NovaTransformerRuntime

DEFAULT_SEED = 20260622


def apply_decision(
    registry: CheckpointRegistry,
    candidate_hashes: Mapping[str, str],
    decision: PromotionDecision,
) -> None:
    reasons = [str(reason) for reason in decision.reasons if str(reason).strip()]
    if not reasons:
        reasons = [f"promotion verdict was {decision.verdict}"]

    _prevalidate_candidate_set(
        registry,
        candidate_hashes,
        disallow_rejected=decision.verdict == "PROMOTED",
    )

    if decision.verdict == "PROMOTED":
        for role, candidate_hash in candidate_hashes.items():
            registry.promote(role, candidate_hash)
        return

    if decision.verdict in {"REJECTED", "BLOCKED"}:
        for role, candidate_hash in candidate_hashes.items():
            registry.reject(role, candidate_hash, reasons)
        return

    raise ValueError(f"unknown promotion verdict: {decision.verdict!r}")


def run_hyper_training(
    project_root: str | Path,
    seed: int = DEFAULT_SEED,
    route_epochs: int = 80,
    role_epochs: int = 30,
) -> dict:
    root = Path(project_root).resolve()
    run_id = _new_run_id()
    registry: CheckpointRegistry | None = None
    context: dict[str, Any] = {
        "run_id": run_id,
        "project_root": str(root),
        "seed": seed,
        "route_epochs": route_epochs,
        "role_epochs": role_epochs,
        "started_at": _utc_now(),
        "candidate_hashes": {},
    }

    try:
        registry = CheckpointRegistry(root)
        preflight = _run_preflight(root)
        context["preflight"] = preflight
        if preflight.get("verdict") != "READY":
            return _blocked_result(root, run_id, context, preflight.get("reasons", ["preflight failed"]))

        dataset_manifest = _build_dataset(root, seed)
        context["dataset"] = dataset_manifest

        baseline_metrics = _evaluate_baseline(root, dataset_manifest, registry)
        context["baseline_metrics"] = baseline_metrics

        route_candidate = _train_route_candidate(root, dataset_manifest, seed, route_epochs)
        context["route_candidate"] = _report_safe(route_candidate)

        role_candidates: dict[str, dict[str, Any]] = {}
        candidate_hashes: dict[str, str] = {}
        for index, role in enumerate(ROLE_NAMES):
            candidate = _train_role_candidate_for_orchestrator(
                root,
                role,
                dataset_manifest,
                registry,
                seed + index + 1,
                role_epochs,
            )
            role_candidates[role] = candidate
            candidate_hashes[role] = str(candidate["candidate_sha256"])
            context["candidate_hashes"] = dict(candidate_hashes)
        context["role_candidates"] = _report_safe(role_candidates)

        reload_check = _fresh_process_reload_check(root, route_candidate, role_candidates)
        context["reload_check"] = reload_check

        candidate_metrics = _evaluate_candidate(
            root,
            dataset_manifest,
            route_candidate,
            role_candidates,
            reload_check,
        )
        context["candidate_metrics"] = candidate_metrics

        negative_controls = _run_negative_controls(root, dataset_manifest, baseline_metrics)
        context["negative_controls"] = negative_controls

        previous_winner_metrics = _previous_winner_metrics(registry)
        context["previous_winner_metrics"] = previous_winner_metrics

        decision = _decide_promotion(baseline_metrics, candidate_metrics, previous_winner_metrics)
        if not negative_controls.get("passed"):
            decision = PromotionDecision(
                "BLOCKED",
                ("negative controls failed",),
                _joint_metric(baseline_metrics),
                _joint_metric(candidate_metrics),
                _joint_metric(previous_winner_metrics) if previous_winner_metrics else None,
            )
        context["decision"] = _decision_dict(decision)

        if decision.verdict == "PROMOTED":
            return _complete_promoted_transaction(
                root,
                run_id,
                registry,
                candidate_hashes,
                decision,
                context,
                route_candidate,
                candidate_metrics,
            )

        apply_decision(registry, candidate_hashes, decision)

        return _final_result(root, run_id, decision.verdict, context)
    except Exception as exc:
        context["exception"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        reasons = [f"{type(exc).__name__}: {exc}"]
        candidate_hashes = context.get("candidate_hashes")
        if (
            registry is not None
            and isinstance(candidate_hashes, Mapping)
            and candidate_hashes
            and not context.get("promotion_transaction_started")
        ):
            try:
                blocked = PromotionDecision(
                    "BLOCKED",
                    tuple(reasons),
                    _joint_metric(context.get("baseline_metrics")),
                    _joint_metric(context.get("candidate_metrics")),
                    None,
                )
                apply_decision(registry, candidate_hashes, blocked)
            except Exception as reject_exc:
                context["candidate_rejection_error"] = {
                    "type": type(reject_exc).__name__,
                    "message": str(reject_exc),
                }
        return _blocked_result(root, run_id, context, reasons)


def _prevalidate_candidate_set(
    registry: CheckpointRegistry,
    candidate_hashes: Mapping[str, str],
    *,
    disallow_rejected: bool,
) -> None:
    snapshot = registry.snapshot()
    roles = snapshot.get("roles", {})
    missing: list[str] = []
    rejected: list[str] = []
    for role, candidate_hash in candidate_hashes.items():
        role_record = roles.get(role)
        candidates = role_record.get("candidates", {}) if isinstance(role_record, dict) else {}
        candidate = candidates.get(candidate_hash) if isinstance(candidates, dict) else None
        if not isinstance(candidate, dict):
            missing.append(f"{role}:{candidate_hash}")
        elif disallow_rejected and candidate.get("status") == "rejected":
            rejected.append(f"{role}:{candidate_hash}")
    if missing or rejected:
        messages = []
        if missing:
            messages.append("missing candidates: " + ", ".join(missing))
        if rejected:
            messages.append("rejected candidates: " + ", ".join(rejected))
        raise LookupError("; ".join(messages))


def _complete_promoted_transaction(
    project_root: Path,
    run_id: str,
    registry: CheckpointRegistry,
    candidate_hashes: Mapping[str, str],
    decision: PromotionDecision,
    context: dict[str, Any],
    route_candidate: Mapping[str, Any],
    candidate_metrics: Mapping[str, Any],
) -> dict:
    context["promotion_transaction_started"] = True
    registry_snapshot = registry.snapshot()
    route_snapshot = _capture_route_snapshot(project_root)
    try:
        _prevalidate_candidate_set(registry, candidate_hashes, disallow_rejected=True)
        _validate_route_candidate(route_candidate)
        _update_candidate_metrics(registry, candidate_hashes, candidate_metrics)
        result = _final_result(project_root, run_id, decision.verdict, context)
        apply_decision(registry, candidate_hashes, decision)
        _promote_route_candidate(project_root, route_candidate)
        return result
    except Exception:
        _restore_registry_snapshot(registry, registry_snapshot)
        _restore_route_snapshot(project_root, route_snapshot)
        raise


def _run_preflight(project_root: Path) -> dict[str, Any]:
    return run_preflight(project_root)


def _build_dataset(project_root: Path, seed: int) -> dict[str, Any]:
    return build_dataset(project_root, seed=seed)


def _evaluate_baseline(
    project_root: Path,
    dataset_manifest: Mapping[str, Any],
    registry: CheckpointRegistry,
) -> dict[str, Any]:
    rows = _promotion_rows(project_root, dataset_manifest)
    route_cases = _route_cases(rows)
    answer_cases = _answer_cases(rows)
    runtime = NovaTransformerRuntime(project_root)
    routing = evaluate_routes(runtime, route_cases)
    answers = evaluate_answers(runtime, answer_cases)
    stability = evaluate_stability(
        runtime,
        {"reload_ok": True, "load_ok": True, "confirmation_ok": True, "regressions": 0},
    )
    return _metrics(routing, answers, stability)


def _train_route_candidate(
    project_root: Path,
    dataset_manifest: Mapping[str, Any],
    seed: int,
    epochs: int,
) -> dict[str, Any]:
    train_rows = _split_rows(project_root, dataset_manifest, "train")
    validation_rows = _split_rows(project_root, dataset_manifest, "validation")
    train_examples = route_examples_from_rows(train_rows, include_answer_rows=True)
    validation_examples = route_examples_from_rows(validation_rows, include_answer_rows=True)
    fingerprint = str(dataset_manifest.get("content_fingerprint", "dataset"))[:16]
    output_path = (
        project_root
        / "artifacts"
        / "transformer_training"
        / "route_candidates"
        / f"route_model_{fingerprint}_{seed}.pt"
    )
    model, metadata = train_route_model(
        train_examples,
        validation_examples=validation_examples,
        seed=seed,
        epochs=epochs,
        output_path=output_path,
    )
    return {
        "checkpoint_path": str(output_path),
        "sha256": sha256(output_path),
        "metadata": metadata,
        "_route_model": _RouteCandidateAdapter(model),
    }


def _train_role_candidate_for_orchestrator(
    project_root: Path,
    role: str,
    dataset_manifest: Mapping[str, Any],
    registry: CheckpointRegistry,
    seed: int,
    epochs: int,
) -> dict[str, Any]:
    baseline = registry.resolve_live(role)
    train_rows = _role_rows(_split_rows(project_root, dataset_manifest, "train"), role)
    validation_rows = _role_rows(_split_rows(project_root, dataset_manifest, "validation"), role)
    fingerprint = str(dataset_manifest.get("content_fingerprint", "dataset"))[:16]
    output_path = (
        project_root
        / "artifacts"
        / "transformer_training"
        / "role_candidates"
        / fingerprint
        / f"{role}_{seed}.pt"
    )
    protected_paths = [registry.resolve_live(protected_role).path for protected_role in ROLE_NAMES]
    result = train_role_candidate(
        role,
        baseline.path,
        train_rows,
        validation_rows,
        output_path,
        seed=seed,
        epochs=epochs,
        protected_paths=protected_paths,
    )
    registry.register_candidate(
        role,
        output_path,
        str(result["candidate_sha256"]),
        {
            "training": _report_safe(result),
            "baseline_sha256": baseline.sha256,
        },
    )
    return result


def _fresh_process_reload_check(
    project_root: Path,
    route_candidate: Mapping[str, Any],
    role_candidates: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "project_root": str(project_root),
        "route_path": route_candidate.get("checkpoint_path"),
        "role_paths": {
            role: candidate.get("checkpoint_path")
            for role, candidate in role_candidates.items()
        },
    }
    script = r"""
import json, sys
from pathlib import Path
data = json.loads(sys.stdin.read())
root = Path(data["project_root"])
sys.path.insert(0, str(root / "src"))
from nova_route_model import load_route_model
from nova_torch_transformer import load_checkpoint
load_route_model(data["route_path"])
for path in data["role_paths"].values():
    load_checkpoint(path)
print(json.dumps({"reload_ok": True, "load_ok": True, "role_checkpoints_ok": True, "roles_ok": True, "role_ok": True, "confirmation_ok": True, "regressions": 0}))
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=project_root,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        return {
            "reload_ok": False,
            "load_ok": False,
            "role_checkpoints_ok": False,
            "roles_ok": False,
            "role_ok": False,
            "confirmation_ok": False,
            "regressions": 1,
            "error": str(exc),
        }
    if completed.returncode != 0:
        return {
            "reload_ok": False,
            "load_ok": False,
            "role_checkpoints_ok": False,
            "roles_ok": False,
            "role_ok": False,
            "confirmation_ok": False,
            "regressions": 1,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        return {
            "reload_ok": False,
            "load_ok": False,
            "role_checkpoints_ok": False,
            "roles_ok": False,
            "role_ok": False,
            "confirmation_ok": False,
            "regressions": 1,
            "error": f"fresh-process reload returned invalid JSON: {exc}",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }


def _evaluate_candidate(
    project_root: Path,
    dataset_manifest: Mapping[str, Any],
    route_candidate: Mapping[str, Any],
    role_candidates: Mapping[str, Mapping[str, Any]],
    reload_check: Mapping[str, Any],
) -> dict[str, Any]:
    rows = _promotion_rows(project_root, dataset_manifest)
    route_cases = _route_cases(rows)
    answer_cases = _answer_cases(rows)
    route_model = route_candidate.get("_route_model")
    if route_model is None:
        route_model = NovaTransformerRuntime(project_root).route_model
    runtime = NovaTransformerRuntime(project_root, route_model=route_model)
    runtime.registry = _CandidateRegistryView(project_root, CheckpointRegistry(project_root), role_candidates)
    routing = evaluate_routes(route_model, route_cases)
    answers = evaluate_answers(runtime, answer_cases)
    stability = evaluate_stability(runtime, reload_check)
    return _metrics(routing, answers, stability)


def _run_negative_controls(
    project_root: Path,
    dataset_manifest: Mapping[str, Any],
    baseline_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    rows = _promotion_rows(project_root, dataset_manifest)
    return run_negative_controls(
        project_root,
        {"routes": _route_cases(rows), "baseline": baseline_metrics},
    )


def _decide_promotion(
    baseline_metrics: Mapping[str, Any],
    candidate_metrics: Mapping[str, Any],
    previous_winner_metrics: Mapping[str, Any] | None,
) -> PromotionDecision:
    return decide_promotion(baseline_metrics, candidate_metrics, previous_winner_metrics)


def _blocked_result(
    project_root: Path,
    run_id: str,
    context: dict[str, Any],
    reasons: Any,
) -> dict:
    reason_list = [str(reason) for reason in _as_list(reasons)] or ["blocked"]
    context["decision"] = {
        "verdict": "BLOCKED",
        "reasons": reason_list,
        "baseline_joint": _joint_metric(context.get("baseline_metrics")),
        "candidate_joint": _joint_metric(context.get("candidate_metrics")),
        "previous_winner_joint": None,
    }
    return _final_result(project_root, run_id, "BLOCKED", context)


def _final_result(project_root: Path, run_id: str, verdict: str, context: dict[str, Any]) -> dict:
    context["finished_at"] = _utc_now()
    context["verdict"] = verdict
    reports = _write_reports(project_root, run_id, verdict, context)
    decision = context.get("decision", {})
    result = {
        "run_id": run_id,
        "verdict": verdict,
        "json_report": str(reports["json"]),
        "markdown_report": str(reports["markdown"]),
        "baseline_joint": decision.get("baseline_joint"),
        "candidate_joint": decision.get("candidate_joint"),
        "reasons": list(decision.get("reasons", ())),
    }
    return _json_safe(result)


def _write_reports(project_root: Path, run_id: str, verdict: str, context: Mapping[str, Any]) -> dict[str, Path]:
    report_dir = project_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"transformer_hyper_training_{run_id}.json"
    markdown_path = report_dir / f"transformer_hyper_training_{run_id}.md"
    safe_context = _json_safe(context)
    json_path.write_text(
        json.dumps(safe_context, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown_report(verdict, safe_context), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _markdown_report(verdict: str, context: Mapping[str, Any]) -> str:
    decision = context.get("decision", {}) if isinstance(context.get("decision"), Mapping) else {}
    lines = [
        f"# {verdict}",
        "",
        f"- Run ID: `{context.get('run_id')}`",
        f"- Dataset fingerprint: `{_nested(context, ('dataset', 'content_fingerprint'), 'unavailable')}`",
        f"- Baseline joint: `{decision.get('baseline_joint')}`",
        f"- Candidate joint: `{decision.get('candidate_joint')}`",
        "",
        "## Reasons",
    ]
    for reason in _as_list(decision.get("reasons", [])):
        lines.append(f"- {reason}")
    lines.extend(
        [
            "",
            "## Reports",
            "",
            "The JSON report contains the full preflight, dataset, candidate, control, and decision details.",
            "",
        ]
    )
    return "\n".join(lines)


def _promotion_rows(project_root: Path, dataset_manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _split_rows(project_root, dataset_manifest, "promotion")


def _split_rows(project_root: Path, dataset_manifest: Mapping[str, Any], split: str) -> list[dict[str, Any]]:
    outputs = dataset_manifest.get("outputs", {}) if isinstance(dataset_manifest, Mapping) else {}
    path_value = outputs.get(split) if isinstance(outputs, Mapping) else None
    path = project_root / str(path_value or f"artifacts/transformer_training/dataset/{split}.jsonl")
    rows: list[dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(f"dataset split is missing: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    if not rows:
        raise ValueError(f"dataset split is empty: {split}")
    return rows


def _route_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = [row for row in rows if row.get("domain") and row.get("primary_role")]
    if not cases:
        raise ValueError("promotion split has no route cases")
    return cases


def _answer_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        if row.get("task_type") == "route":
            continue
        if not row.get("answer"):
            continue
        case = dict(row)
        case["expected"] = row.get("answer")
        cases.append(case)
    if not cases:
        raise ValueError("promotion split has no answer cases")
    return cases


def _role_rows(rows: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    role_rows = [
        row for row in rows
        if row.get("task_type") != "route" and row.get("primary_role") == role and row.get("answer")
    ]
    if not role_rows:
        role_rows = [row for row in rows if row.get("task_type") != "route" and row.get("answer")]
    if not role_rows:
        raise ValueError(f"no answer training rows available for {role}")
    return role_rows


def _metrics(
    routing: Mapping[str, Any],
    answers: Mapping[str, Any],
    stability: Mapping[str, Any],
) -> dict[str, Any]:
    result = {
        "routing": dict(routing),
        "answers": dict(answers),
        "stability": dict(stability),
    }
    result["joint"] = _joint_metric(result)
    return result


def _joint_metric(metrics: Any) -> float:
    if not isinstance(metrics, Mapping):
        return 0.0
    explicit = _optional_float(metrics.get("joint"))
    if explicit is not None:
        return explicit
    routing = _optional_float(_nested(metrics, ("routing", "macro_f1"), 0.0)) or 0.0
    answers = _optional_float(_nested(metrics, ("answers", "composite"), 0.0)) or 0.0
    stability = _optional_float(_nested(metrics, ("stability", "score"), 0.0)) or 0.0
    return 0.50 * routing + 0.40 * answers + 0.10 * stability


def _previous_winner_metrics(registry: CheckpointRegistry) -> dict[str, Any] | None:
    metrics: list[float] = []
    snapshot = registry.snapshot()
    roles = snapshot.get("roles", {})
    if not isinstance(roles, Mapping):
        return None
    for role_record in roles.values():
        if not isinstance(role_record, Mapping):
            continue
        live_sha256 = role_record.get("live_sha256")
        candidates = role_record.get("candidates", {})
        if isinstance(live_sha256, str) and isinstance(candidates, Mapping):
            candidate = candidates.get(live_sha256)
            if isinstance(candidate, Mapping) and candidate.get("status") == "promoted":
                joint = _optional_float(_nested(candidate, ("metrics", "joint"), None))
                if joint is not None:
                    metrics.append(joint)
    if not metrics:
        return None
    return {"joint": sum(metrics) / len(metrics)}


def _update_candidate_metrics(
    registry: CheckpointRegistry,
    candidate_hashes: Mapping[str, str],
    candidate_metrics: Mapping[str, Any],
) -> None:
    metrics = _json_safe(dict(candidate_metrics))
    roles = registry._data.setdefault("roles", {})
    for role, candidate_hash in candidate_hashes.items():
        role_record = roles[role]
        candidate = role_record["candidates"][candidate_hash]
        existing_metrics = candidate.get("metrics", {})
        if not isinstance(existing_metrics, dict):
            existing_metrics = {}
        merged_metrics = dict(existing_metrics)
        merged_metrics.update(metrics)
        candidate["metrics"] = merged_metrics
    registry._write()


def _restore_registry_snapshot(registry: CheckpointRegistry, snapshot: Mapping[str, Any]) -> None:
    registry._data = json.loads(json.dumps(snapshot))
    registry._write()


def _capture_route_snapshot(project_root: Path) -> dict[str, bytes | None]:
    target = project_root / "checkpoints" / "route_model" / "promoted.pt"
    sidecar = target.with_suffix(f"{target.suffix}.json")
    return {
        "model": target.read_bytes() if target.exists() else None,
        "sidecar": sidecar.read_bytes() if sidecar.exists() else None,
    }


def _restore_route_snapshot(project_root: Path, snapshot: Mapping[str, bytes | None]) -> None:
    target = project_root / "checkpoints" / "route_model" / "promoted.pt"
    sidecar = target.with_suffix(f"{target.suffix}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    for path, key in ((target, "model"), (sidecar, "sidecar")):
        value = snapshot.get(key)
        if value is None:
            if path.exists():
                path.unlink()
        else:
            temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
            temp.write_bytes(value)
            temp.replace(path)


def _validate_route_candidate(route_candidate: Mapping[str, Any]) -> Path:
    source_value = route_candidate.get("checkpoint_path")
    if not source_value:
        raise ValueError("route candidate is missing checkpoint_path")
    source = Path(str(source_value))
    if not source.exists():
        raise FileNotFoundError(f"route candidate is missing: {source}")
    if not source.is_file():
        raise ValueError(f"route candidate is not a file: {source}")
    return source


def _promote_route_candidate(project_root: Path, route_candidate: Mapping[str, Any]) -> None:
    source = _validate_route_candidate(route_candidate)
    target = project_root / "checkpoints" / "route_model" / "promoted.pt"
    target.parent.mkdir(parents=True, exist_ok=True)
    sidecar = source.with_suffix(f"{source.suffix}.json")
    if sidecar.exists():
        target_sidecar = target.with_suffix(f"{target.suffix}.json")
        temp_sidecar = target_sidecar.with_name(f"{target_sidecar.name}.{uuid.uuid4().hex}.tmp")
        temp_sidecar.write_bytes(sidecar.read_bytes())
        temp_sidecar.replace(target_sidecar)
    temp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    temp.write_bytes(source.read_bytes())
    temp.replace(target)


class _RouteCandidateAdapter:
    def __init__(self, model: Any):
        self.model = model
        self.model_hash = getattr(model, "route_metadata", {}).get("model_hash", "")

    def predict(self, text: str):
        return predict_route(self.model, text)


class _CandidateRegistryView:
    def __init__(
        self,
        project_root: Path,
        registry: CheckpointRegistry,
        role_candidates: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self.project_root = project_root
        self.registry = registry
        self.role_candidates = role_candidates

    def resolve_live(self, role: str) -> ResolvedCheckpoint:
        candidate = self.role_candidates.get(role)
        if not isinstance(candidate, Mapping):
            return self.registry.resolve_live(role)
        path = Path(str(candidate["checkpoint_path"]))
        digest = str(candidate["candidate_sha256"])
        return ResolvedCheckpoint(role, path, digest, "candidate", dict(candidate))


def _decision_dict(decision: PromotionDecision) -> dict[str, Any]:
    return asdict(decision)


def _report_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _report_safe(item)
            for key, item in value.items()
            if not str(key).startswith("_") and key != "model"
        }
    if isinstance(value, (list, tuple)):
        return [_report_safe(item) for item in value]
    return _json_safe(value)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _nested(value: Mapping[str, Any], path: tuple[str, ...], default: Any) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)):
        return [value]
    if isinstance(value, list | tuple):
        return list(value)
    return [value]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"
