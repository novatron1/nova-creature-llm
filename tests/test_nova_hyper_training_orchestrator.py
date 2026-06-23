from pathlib import Path
import sys

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


def role_hash(role: str) -> str:
    return sha256_bytes(role.encode("utf-8"))


def sha256_bytes(contents: bytes) -> str:
    import hashlib

    return hashlib.sha256(contents).hexdigest()
