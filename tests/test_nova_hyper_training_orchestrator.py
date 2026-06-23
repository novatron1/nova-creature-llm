from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_checkpoint_registry import CheckpointRegistry, sha256
import nova_hyper_training_orchestrator as orchestrator
from nova_hyper_training_orchestrator import apply_decision, run_hyper_training
from nova_training_types import ROLE_NAMES, PromotionDecision


def _write_checkpoint(path: Path, contents: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return sha256(path)


def test_rejected_run_leaves_live_checkpoint_unchanged(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline_hash = _write_checkpoint(baseline, b"baseline")
    candidate_hash = _write_checkpoint(candidate, b"candidate")
    registry.register_baseline("memory_transformer", baseline, baseline_hash)
    registry.register_candidate("memory_transformer", candidate, candidate_hash, {"joint": 70.0})
    decision = PromotionDecision("REJECTED", ("answer regression",), 70.0, 69.0, None)

    apply_decision(registry, {"memory_transformer": candidate_hash}, decision)

    assert registry.resolve_live("memory_transformer").sha256 == baseline_hash


def test_role_candidate_output_path_preserves_checkpoint_evidence_contract(tmp_path):
    path = orchestrator._role_candidate_output_path(
        tmp_path,
        "left_hemisphere",
        "abcdef1234567890fedcba",
        20260623,
    )

    assert path == (
        tmp_path
        / "checkpoints"
        / "brain_slots"
        / "left_hemisphere"
        / "candidates"
        / "abcdef1234567890"
        / "left_hemisphere_20260623.pt"
    )


def test_run_hyper_training_follows_guarded_order_and_writes_reports(tmp_path, monkeypatch):
    events = []

    def fake_preflight(project_root):
        events.append("preflight")
        return {"verdict": "READY", "reasons": [], "hashes": {}}

    def fake_dataset(project_root, seed):
        events.append("dataset")
        return {
            "seed": seed,
            "content_fingerprint": "dataset-fingerprint",
            "split_counts": {"train": 10, "validation": 5, "promotion": 5},
        }

    def fake_baseline(project_root, dataset_manifest, registry):
        events.append("baseline")
        return {"joint": 70.0, "routing": {"macro_f1": 70.0}, "answers": {"composite": 70.0}}

    def fake_route_train(project_root, dataset_manifest, seed, epochs):
        events.append("route_train")
        return {"checkpoint_path": "checkpoints/route_model/candidate.pt", "sha256": "a" * 64}

    def fake_role_train(project_root, role, dataset_manifest, registry, seed, epochs):
        events.append(f"role_train:{role}")
        return {"role": role, "candidate_sha256": role_hash(role), "checkpoint_path": f"{role}.pt"}

    def fake_reload(project_root, route_candidate, role_candidates):
        events.append("reload")
        return {"reload_ok": True, "confirmation_ok": True, "regressions": 0}

    def fake_candidate(project_root, dataset_manifest, route_candidate, role_candidates, reload_check):
        events.append("candidate")
        return {"joint": 69.0, "stability": {"reload_ok": True, "confirmation_ok": True, "regressions": 0}}

    def fake_negative_controls(project_root, dataset_manifest, baseline_metrics):
        events.append("negative_controls")
        return {"passed": True, "controls": {}}

    def fake_decision(baseline_metrics, candidate_metrics, previous_winner_metrics):
        events.append("decision")
        return PromotionDecision("REJECTED", ("answer regression",), 70.0, 69.0, None)

    def fake_apply(registry, candidate_hashes, decision):
        events.append("apply_decision")
        assert set(candidate_hashes) == set(ROLE_NAMES)
        assert decision.verdict == "REJECTED"

    monkeypatch.setattr(orchestrator, "_run_preflight", fake_preflight)
    monkeypatch.setattr(orchestrator, "_build_dataset", fake_dataset)
    monkeypatch.setattr(orchestrator, "_evaluate_baseline", fake_baseline)
    monkeypatch.setattr(orchestrator, "_train_route_candidate", fake_route_train)
    monkeypatch.setattr(orchestrator, "_train_role_candidate_for_orchestrator", fake_role_train)
    monkeypatch.setattr(orchestrator, "_fresh_process_reload_check", fake_reload)
    monkeypatch.setattr(orchestrator, "_evaluate_candidate", fake_candidate)
    monkeypatch.setattr(orchestrator, "_run_negative_controls", fake_negative_controls)
    monkeypatch.setattr(orchestrator, "_decide_promotion", fake_decision)
    monkeypatch.setattr(orchestrator, "apply_decision", fake_apply)

    result = run_hyper_training(tmp_path, seed=123, route_epochs=2, role_epochs=1)

    assert events == [
        "preflight",
        "dataset",
        "baseline",
        "route_train",
        *(f"role_train:{role}" for role in ROLE_NAMES),
        "reload",
        "candidate",
        "negative_controls",
        "decision",
        "apply_decision",
    ]
    assert result["verdict"] == "REJECTED"
    assert result["candidate_joint"] == 69.0
    json_report = Path(result["json_report"])
    markdown_report = Path(result["markdown_report"])
    assert json_report.exists()
    assert markdown_report.exists()
    assert markdown_report.read_text(encoding="utf-8").splitlines()[0] == "# REJECTED"


def test_promotion_rows_include_sealed_promotion_bank_only_for_evaluation(tmp_path):
    promotion_path = tmp_path / "artifacts" / "transformer_training" / "dataset" / "promotion.jsonl"
    promotion_path.parent.mkdir(parents=True)
    promotion_path.write_text(
        '{"prompt":"normal promotion","answer":"ok","domain":"speech","primary_role":"speech_output_transformer","task_type":"answer"}\n',
        encoding="utf-8",
    )
    bank_path = tmp_path / "benchmark_lab" / "test_banks" / "transformer_route_promotion_bank.json"
    bank_path.parent.mkdir(parents=True)
    bank_path.write_text(
        '[{"id":"sealed-1","prompt":"sealed bank prompt","domain":"critic","primary_role":"critic_conscience_transformer","required_terms":["sealed","evidence"],"protected":true}]',
        encoding="utf-8",
    )
    manifest = {"outputs": {"promotion": "artifacts/transformer_training/dataset/promotion.jsonl"}}

    split_rows = orchestrator._split_rows(tmp_path, manifest, "promotion")
    evaluation_rows = orchestrator._promotion_rows(tmp_path, manifest)

    assert {row["prompt"] for row in split_rows} == {"normal promotion"}
    sealed = next(row for row in evaluation_rows if row["prompt"] == "sealed bank prompt")
    assert sealed["protected"] is True
    assert sealed["required_terms"] == ["sealed", "evidence"]
    assert sealed["source"] == "promotion_bank"


def test_blocked_preflight_writes_reports_without_mutating_registry(tmp_path, monkeypatch):
    events = []

    def fake_preflight(project_root):
        events.append("preflight")
        return {"verdict": "BLOCKED", "reasons": ["torch check failed"], "hashes": {}}

    def fail_if_called(*args, **kwargs):
        raise AssertionError("orchestrator continued after BLOCKED preflight")

    monkeypatch.setattr(orchestrator, "_run_preflight", fake_preflight)
    monkeypatch.setattr(orchestrator, "_build_dataset", fail_if_called)
    monkeypatch.setattr(orchestrator, "apply_decision", fail_if_called)

    result = run_hyper_training(tmp_path)

    assert events == ["preflight"]
    assert result["verdict"] == "BLOCKED"
    assert "torch check failed" in result["reasons"]
    assert Path(result["json_report"]).exists()
    markdown_report = Path(result["markdown_report"])
    assert markdown_report.exists()
    assert markdown_report.read_text(encoding="utf-8").splitlines()[0] == "# BLOCKED"


def test_apply_decision_prevalidates_rejection_before_mutating_candidates(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline_hash = _write_checkpoint(baseline, b"baseline")
    candidate_hash = _write_checkpoint(candidate, b"candidate")
    registry.register_baseline("left_hemisphere", baseline, baseline_hash)
    registry.register_candidate("left_hemisphere", candidate, candidate_hash, {"joint": 70.0})
    decision = PromotionDecision("REJECTED", ("missing peer",), 70.0, 69.0, None)

    with pytest.raises(LookupError):
        apply_decision(
            registry,
            {
                "left_hemisphere": candidate_hash,
                "right_hemisphere": "f" * 64,
            },
            decision,
        )

    stored = registry.snapshot()["roles"]["left_hemisphere"]["candidates"][candidate_hash]
    assert stored["status"] == "candidate"


def test_corrupt_registry_returns_blocked_report(tmp_path):
    registry_path = tmp_path / "checkpoints" / "registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{not valid json", encoding="utf-8")

    result = run_hyper_training(tmp_path)

    assert result["verdict"] == "BLOCKED"
    assert "JSONDecodeError" in result["reasons"][0]
    assert Path(result["json_report"]).exists()
    markdown_report = Path(result["markdown_report"])
    assert markdown_report.exists()
    assert markdown_report.read_text(encoding="utf-8").splitlines()[0] == "# BLOCKED"


def test_failed_role_training_rejects_incrementally_registered_candidates(tmp_path, monkeypatch):
    roles = ("left_hemisphere", "right_hemisphere")
    monkeypatch.setattr(orchestrator, "ROLE_NAMES", roles)
    monkeypatch.setattr(orchestrator, "_run_preflight", lambda project_root: {"verdict": "READY", "reasons": []})
    monkeypatch.setattr(orchestrator, "_build_dataset", lambda project_root, seed: {"content_fingerprint": "abc"})
    monkeypatch.setattr(orchestrator, "_evaluate_baseline", lambda project_root, dataset, registry: {"joint": 70.0})
    monkeypatch.setattr(
        orchestrator,
        "_train_route_candidate",
        lambda project_root, dataset, seed, epochs: {"checkpoint_path": str(tmp_path / "route.pt")},
    )

    def fake_role_train(project_root, role, dataset, registry, seed, epochs):
        if role == "right_hemisphere":
            raise RuntimeError("role trainer exploded")
        candidate = tmp_path / f"{role}.pt"
        candidate_hash = _write_checkpoint(candidate, f"candidate:{role}".encode("utf-8"))
        registry.register_candidate(role, candidate, candidate_hash, {"training": {"role": role}})
        return {"role": role, "candidate_sha256": candidate_hash, "checkpoint_path": str(candidate)}

    monkeypatch.setattr(orchestrator, "_train_role_candidate_for_orchestrator", fake_role_train)

    result = run_hyper_training(tmp_path)

    assert result["verdict"] == "BLOCKED"
    snapshot = CheckpointRegistry(tmp_path).snapshot()
    left_candidates = snapshot["roles"]["left_hemisphere"]["candidates"]
    assert list(left_candidates.values())[0]["status"] == "rejected"


def test_promoted_route_failure_restores_previous_live_winners(tmp_path, monkeypatch):
    roles = ("left_hemisphere", "right_hemisphere")
    previous_hashes = _register_previous_winners(tmp_path, roles)
    new_hashes = _register_new_candidates(tmp_path, roles, {"training": {"phase": "candidate"}})
    route_candidate = tmp_path / "route_candidate.pt"
    route_candidate.write_bytes(b"route")

    _patch_promoted_run(monkeypatch, roles, new_hashes, str(route_candidate))
    monkeypatch.setattr(orchestrator, "_promote_route_candidate", lambda project_root, candidate: (_ for _ in ()).throw(RuntimeError("route swap failed")))

    result = run_hyper_training(tmp_path)

    assert result["verdict"] == "BLOCKED"
    registry = CheckpointRegistry(tmp_path)
    for role, previous_hash in previous_hashes.items():
        assert registry.resolve_live(role).sha256 == previous_hash
        stored = registry.snapshot()["roles"][role]["candidates"][new_hashes[role]]
        assert stored["status"] == "candidate"
    assert not (tmp_path / "checkpoints" / "route_model" / "promoted.pt").exists()


def test_promoted_report_failure_happens_before_live_mutation(tmp_path, monkeypatch):
    roles = ("left_hemisphere", "right_hemisphere")
    previous_hashes = _register_previous_winners(tmp_path, roles)
    new_hashes = _register_new_candidates(tmp_path, roles, {"training": {"phase": "candidate"}})
    route_candidate = tmp_path / "route_candidate.pt"
    route_candidate.write_bytes(b"route")

    _patch_promoted_run(monkeypatch, roles, new_hashes, str(route_candidate))
    original_write_reports = orchestrator._write_reports

    def fail_promoted_report(project_root, run_id, verdict, context):
        if verdict == "PROMOTED":
            raise OSError("report disk full")
        return original_write_reports(project_root, run_id, verdict, context)

    monkeypatch.setattr(orchestrator, "_write_reports", fail_promoted_report)

    result = run_hyper_training(tmp_path)

    assert result["verdict"] == "BLOCKED"
    registry = CheckpointRegistry(tmp_path)
    for role, previous_hash in previous_hashes.items():
        assert registry.resolve_live(role).sha256 == previous_hash
        assert registry.snapshot()["roles"][role]["candidates"][new_hashes[role]]["status"] == "candidate"
    assert not (tmp_path / "checkpoints" / "route_model" / "promoted.pt").exists()


def test_promoted_candidates_store_joint_metrics_for_next_run(tmp_path, monkeypatch):
    roles = ("left_hemisphere", "right_hemisphere")
    _register_previous_winners(tmp_path, roles)
    new_hashes = _register_new_candidates(tmp_path, roles, {"training": {"phase": "candidate"}})
    route_candidate = tmp_path / "route_candidate.pt"
    route_candidate.write_bytes(b"route")

    _patch_promoted_run(monkeypatch, roles, new_hashes, str(route_candidate), candidate_joint=88.5)
    monkeypatch.setattr(orchestrator, "_promote_route_candidate", lambda project_root, candidate: None)

    result = run_hyper_training(tmp_path)

    assert result["verdict"] == "PROMOTED"
    registry = CheckpointRegistry(tmp_path)
    for role, candidate_hash in new_hashes.items():
        stored = registry.snapshot()["roles"][role]["candidates"][candidate_hash]
        assert stored["status"] == "promoted"
        assert stored["metrics"]["joint"] == 88.5
    assert orchestrator._previous_winner_metrics(registry) == {"joint": 88.5}


def role_hash(role: str) -> str:
    return sha256_bytes(role.encode("utf-8"))


def sha256_bytes(contents: bytes) -> str:
    import hashlib

    return hashlib.sha256(contents).hexdigest()


def _register_previous_winners(tmp_path: Path, roles: tuple[str, ...]) -> dict[str, str]:
    registry = CheckpointRegistry(tmp_path)
    previous_hashes = {}
    for role in roles:
        baseline = tmp_path / f"{role}_baseline.pt"
        previous = tmp_path / f"{role}_previous.pt"
        baseline_hash = _write_checkpoint(baseline, f"baseline:{role}".encode("utf-8"))
        previous_hash = _write_checkpoint(previous, f"previous:{role}".encode("utf-8"))
        registry.register_baseline(role, baseline, baseline_hash)
        registry.register_candidate(role, previous, previous_hash, {"joint": 81.0})
        registry.promote(role, previous_hash)
        previous_hashes[role] = previous_hash
    return previous_hashes


def _register_new_candidates(tmp_path: Path, roles: tuple[str, ...], metrics: dict) -> dict[str, str]:
    registry = CheckpointRegistry(tmp_path)
    new_hashes = {}
    for role in roles:
        candidate = tmp_path / f"{role}_new.pt"
        candidate_hash = _write_checkpoint(candidate, f"new:{role}".encode("utf-8"))
        registry.register_candidate(role, candidate, candidate_hash, metrics)
        new_hashes[role] = candidate_hash
    return new_hashes


def _patch_promoted_run(
    monkeypatch,
    roles: tuple[str, ...],
    new_hashes: dict[str, str],
    route_path: str,
    *,
    candidate_joint: float = 88.0,
) -> None:
    monkeypatch.setattr(orchestrator, "ROLE_NAMES", roles)
    monkeypatch.setattr(orchestrator, "_run_preflight", lambda project_root: {"verdict": "READY", "reasons": []})
    monkeypatch.setattr(orchestrator, "_build_dataset", lambda project_root, seed: {"content_fingerprint": "abc"})
    monkeypatch.setattr(orchestrator, "_evaluate_baseline", lambda project_root, dataset, registry: {"joint": 80.0})
    monkeypatch.setattr(
        orchestrator,
        "_train_route_candidate",
        lambda project_root, dataset, seed, epochs: {"checkpoint_path": route_path},
    )
    monkeypatch.setattr(
        orchestrator,
        "_train_role_candidate_for_orchestrator",
        lambda project_root, role, dataset, registry, seed, epochs: {
            "role": role,
            "candidate_sha256": new_hashes[role],
            "checkpoint_path": str(project_root / f"{role}_new.pt"),
        },
    )
    monkeypatch.setattr(orchestrator, "_fresh_process_reload_check", lambda project_root, route, candidates: {"reload_ok": True})
    monkeypatch.setattr(orchestrator, "_evaluate_candidate", lambda *args: {"joint": candidate_joint})
    monkeypatch.setattr(orchestrator, "_run_negative_controls", lambda project_root, dataset, baseline: {"passed": True})
    monkeypatch.setattr(
        orchestrator,
        "_decide_promotion",
        lambda baseline, candidate, previous: PromotionDecision("PROMOTED", ("all gates passed",), 80.0, candidate_joint, previous["joint"] if previous else None),
    )
