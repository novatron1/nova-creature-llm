from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_route_model import RouteExample, train_route_model, evaluate_route_model


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
