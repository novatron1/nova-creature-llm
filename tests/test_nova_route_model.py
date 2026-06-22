from pathlib import Path
from dataclasses import asdict
import json
import sys

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_route_model import (
    RouteExample,
    evaluate_route_model,
    load_route_model,
    predict_route,
    route_examples_from_rows,
    save_route_model,
    train_route_model,
)
from nova_training_types import DOMAIN_NAMES, ROLE_NAMES


def examples():
    return [
        RouteExample("debug this Python function", "coding", "left_hemisphere"),
        RouteExample("solve this equation", "math", "left_hemisphere"),
        RouteExample("make an ordered release plan", "planning", "planner_transformer"),
        RouteExample("check whether this claim is true", "critic", "critic_conscience_transformer"),
        RouteExample("imagine a visual pattern", "creative", "right_hemisphere"),
        RouteExample("remember who made you", "memory_recall", "memory_transformer"),
        RouteExample("simulate a failed launch", "dream", "dream_simulation_transformer"),
        RouteExample("explain this clearly", "speech", "speech_output_transformer"),
    ]


def test_route_training_beats_untrained_baseline(tmp_path):
    model, metadata = train_route_model(examples() * 8, seed=7, epochs=80)
    metrics = evaluate_route_model(model, examples())
    assert metrics["primary_role_accuracy"] >= 0.75
    assert metrics["macro_f1"] >= 0.70
    assert metadata["seed"] == 7


def test_shuffled_labels_fail_negative_control():
    rows = examples() * 6
    shuffled = [
        RouteExample(row.text, row.domain, rows[(index + 1) % len(rows)].primary_role)
        for index, row in enumerate(rows)
    ]
    model, _ = train_route_model(shuffled, seed=11, epochs=20)
    metrics = evaluate_route_model(model, examples())
    assert metrics["macro_f1"] < 0.70


def test_validation_provenance_metadata_and_output_guard(tmp_path):
    model, metadata = train_route_model(examples() * 2, seed=3, epochs=1)
    assert model
    assert metadata["validation_source"] == "train_fallback"
    assert metadata["train_count"] == len(examples() * 2)
    assert metadata["validation_count"] == len(examples() * 2)

    holdout = examples()[:3]
    _, holdout_metadata = train_route_model(examples() * 2, validation_examples=holdout, seed=4, epochs=1)
    assert holdout_metadata["validation_source"] == "holdout"
    assert holdout_metadata["train_count"] == len(examples() * 2)
    assert holdout_metadata["validation_count"] == len(holdout)

    with pytest.raises(ValueError, match="validation_examples"):
        train_route_model(examples(), seed=5, epochs=1, output_path=tmp_path / "unsafe.pt")

    _, unsafe_metadata = train_route_model(
        examples(),
        seed=5,
        epochs=1,
        output_path=tmp_path / "allowed.pt",
        allow_train_fallback_for_output=True,
    )
    assert unsafe_metadata["validation_source"] == "train_fallback"


def test_metrics_expose_active_and_all_role_macro_f1_plus_support():
    model, _ = train_route_model(examples() * 4, seed=8, epochs=8)
    metrics = evaluate_route_model(model, examples()[:2])
    assert metrics["macro_f1"] == metrics["macro_f1_active"]
    assert "macro_f1_all_roles" in metrics
    assert set(metrics["per_role_support"]) == set(ROLE_NAMES)
    assert metrics["per_role_support"]["left_hemisphere"] == 2
    assert metrics["macro_f1_all_roles"] <= metrics["macro_f1_active"]


def test_save_load_round_trip_and_predict_route_are_valid_and_json_safe(tmp_path):
    output_path = tmp_path / "route_model.pt"
    model, metadata = train_route_model(
        examples() * 4,
        validation_examples=examples(),
        seed=13,
        epochs=20,
        output_path=output_path,
    )
    assert output_path.exists()
    assert output_path.with_suffix(".pt.json").exists()

    loaded_model, loaded_metadata = load_route_model(output_path)
    assert loaded_metadata["model_hash"] == metadata["model_hash"]
    assert evaluate_route_model(loaded_model, examples()) == evaluate_route_model(model, examples())

    prediction = predict_route(loaded_model, "debug a failing Python test")
    assert prediction.domain in DOMAIN_NAMES
    assert prediction.primary_role in ROLE_NAMES
    assert 0.0 <= prediction.confidence <= 1.0
    json.dumps(asdict(prediction), allow_nan=False)


def test_save_recomputes_hash_and_sidecar_uses_canonical_json(tmp_path):
    model, metadata = train_route_model(examples() * 2, seed=17, epochs=3)
    fake_metadata = {**metadata, "model_hash": "0" * 64}
    output_path = tmp_path / "route_model.pt"
    saved_metadata = save_route_model(model, output_path, metadata=fake_metadata)
    sidecar_metadata = json.loads(output_path.with_suffix(".pt.json").read_text(encoding="utf-8"))

    assert saved_metadata["model_hash"] != "0" * 64
    assert sidecar_metadata["model_hash"] == saved_metadata["model_hash"]
    json.dumps(sidecar_metadata, allow_nan=False, sort_keys=True)


def test_load_rejects_hash_mismatch_and_malformed_payloads(tmp_path):
    model, metadata = train_route_model(examples() * 2, seed=19, epochs=3)
    good_path = tmp_path / "good.pt"
    save_route_model(model, good_path, metadata=metadata)

    payload = torch.load(good_path, map_location="cpu")
    payload["metadata"]["model_hash"] = "f" * 64
    bad_hash_path = tmp_path / "bad_hash.pt"
    torch.save(payload, bad_hash_path)
    with pytest.raises(ValueError, match="model_hash"):
        load_route_model(bad_hash_path)

    malformed_path = tmp_path / "malformed.pt"
    torch.save(["not", "a", "checkpoint"], malformed_path)
    with pytest.raises(ValueError, match="payload"):
        load_route_model(malformed_path)

    bad_maps_path = tmp_path / "bad_maps.pt"
    payload = torch.load(good_path, map_location="cpu")
    payload["metadata"]["class_maps"]["id_to_role"] = ["left_hemisphere"]
    torch.save(payload, bad_maps_path)
    with pytest.raises(ValueError, match="class_maps"):
        load_route_model(bad_maps_path)


def test_invalid_labels_and_route_row_filtering():
    with pytest.raises(ValueError, match="invalid domain"):
        RouteExample("hello", "not_a_domain", "left_hemisphere")
    with pytest.raises(ValueError, match="invalid primary_role"):
        RouteExample("hello", "general", "not_a_role")

    rows = [
        {"task_type": "route", "text": "debug it", "domain": "coding", "primary_role": "left_hemisphere"},
        {"task_type": "answer", "text": "answer it", "domain": "speech", "primary_role": "speech_output_transformer"},
    ]
    route_only = route_examples_from_rows(rows)
    with_answers = route_examples_from_rows(rows, include_answer_rows=True)
    assert [row.text for row in route_only] == ["debug it"]
    assert [row.text for row in with_answers] == ["debug it", "answer it"]


def test_training_is_deterministic_and_restores_thread_count():
    original_thread_count = torch.get_num_threads()
    model_a, metadata_a = train_route_model(examples() * 3, seed=23, epochs=5)
    model_b, metadata_b = train_route_model(examples() * 3, seed=23, epochs=5)

    assert torch.get_num_threads() == original_thread_count
    assert metadata_a["model_hash"] == metadata_b["model_hash"]
    assert evaluate_route_model(model_a, examples()) == evaluate_route_model(model_b, examples())


def test_non_finite_learning_rate_fails_closed():
    with pytest.raises(ValueError, match="learning_rate"):
        train_route_model(examples(), seed=29, epochs=1, learning_rate=float("nan"))
