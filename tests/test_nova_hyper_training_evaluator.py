from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_hyper_training_evaluator import (
    decide_promotion,
    evaluate_answers,
    evaluate_routes,
    evaluate_stability,
    run_negative_controls,
)
from nova_training_types import GenerationResult, RoutePrediction


HASH_A = "a" * 64


def metrics(
    joint,
    route,
    answer,
    repetition=0.01,
    protected=True,
    reload_ok=True,
    load_ok=True,
    role_checkpoints_ok=True,
    role_ok=True,
):
    return {
        "joint": joint,
        "routing": {"macro_f1": route, "protected_domain_floor_delta": 0.0},
        "answers": {
            "composite": answer,
            "protected_perfect": protected,
            "malformed_rate": 0.0,
            "repetition_rate": repetition,
        },
        "stability": {
            "reload_ok": reload_ok,
            "load_ok": load_ok,
            "role_checkpoints_ok": role_checkpoints_ok,
            "role_ok": role_ok,
            "confirmation_ok": True,
            "regressions": 0,
            "score": 100.0,
        },
    }


def test_candidate_promotes_only_when_all_gates_pass():
    decision = decide_promotion(
        baseline=metrics(70.0, 70.0, 70.0),
        candidate=metrics(75.0, 76.0, 74.0),
        previous_winner=None,
    )
    assert decision.verdict == "PROMOTED"


def minimal_metrics(joint, route, answer, repetition=0.01, protected=True, reload_ok=True):
    return {
        "joint": joint,
        "routing": {"macro_f1": route, "protected_domain_floor_delta": 0.0},
        "answers": {
            "composite": answer,
            "protected_perfect": protected,
            "malformed_rate": 0.0,
            "repetition_rate": repetition,
        },
        "stability": {"reload_ok": reload_ok, "confirmation_ok": True, "regressions": 0},
    }


def test_minimal_task9_metrics_shape_still_promotes_when_other_gates_pass():
    decision = decide_promotion(
        baseline=minimal_metrics(70.0, 70.0, 70.0),
        candidate=minimal_metrics(75.0, 76.0, 74.0),
        previous_winner=None,
    )
    assert decision.verdict == "PROMOTED"


def test_hash_change_cannot_override_answer_regression():
    decision = decide_promotion(
        baseline=metrics(80.0, 80.0, 80.0),
        candidate=metrics(83.0, 86.0, 79.0),
        previous_winner=None,
    )
    assert decision.verdict == "REJECTED"
    assert any("answer" in reason.lower() for reason in decision.reasons)


def test_repetition_blocks_promotion():
    decision = decide_promotion(
        baseline=metrics(80.0, 80.0, 80.0),
        candidate=metrics(85.0, 86.0, 84.0, repetition=0.03),
        previous_winner=None,
    )
    assert decision.verdict == "REJECTED"


def test_previous_winner_is_the_reference_for_joint_gain():
    decision = decide_promotion(
        baseline=metrics(80.0, 80.0, 80.0),
        candidate=metrics(84.0, 83.0, 83.0),
        previous_winner=metrics(83.0, 81.0, 81.0),
    )
    assert decision.verdict == "REJECTED"
    assert any("joint" in reason.lower() for reason in decision.reasons)


def test_explicit_joint_values_cannot_override_component_score():
    decision = decide_promotion(
        baseline=metrics(10.0, 80.0, 80.0),
        candidate=metrics(99.0, 81.0, 81.0),
        previous_winner=None,
    )
    assert decision.verdict == "REJECTED"
    assert decision.baseline_joint == 82.0
    assert decision.candidate_joint == 82.9
    assert any("joint" in reason.lower() for reason in decision.reasons)


def test_load_gate_blocks_promotion():
    decision = decide_promotion(
        baseline=metrics(70.0, 70.0, 70.0),
        candidate=metrics(75.0, 76.0, 74.0, load_ok=False),
        previous_winner=None,
    )
    assert decision.verdict == "REJECTED"
    assert any("load" in reason.lower() for reason in decision.reasons)


def test_role_checkpoint_gate_blocks_promotion():
    decision = decide_promotion(
        baseline=metrics(70.0, 70.0, 70.0),
        candidate=metrics(75.0, 76.0, 74.0, role_checkpoints_ok=False),
        previous_winner=None,
    )
    assert decision.verdict == "REJECTED"
    assert any("role" in reason.lower() for reason in decision.reasons)


def test_string_false_load_gate_fails_closed():
    candidate = metrics(75.0, 76.0, 74.0)
    candidate["stability"]["load_ok"] = "false"

    decision = decide_promotion(
        baseline=metrics(70.0, 70.0, 70.0),
        candidate=candidate,
        previous_winner=None,
    )

    assert decision.verdict == "REJECTED"
    assert any("load" in reason.lower() for reason in decision.reasons)


def test_invalid_regression_evidence_rejects_closed():
    for invalid_regressions in ("1", {"count": 1}):
        candidate = metrics(75.0, 76.0, 74.0)
        candidate["stability"]["regressions"] = invalid_regressions

        decision = decide_promotion(
            baseline=metrics(70.0, 70.0, 70.0),
            candidate=candidate,
            previous_winner=None,
        )

        assert decision.verdict == "REJECTED"
        assert any("invalid regression evidence" in reason.lower() for reason in decision.reasons)


class FixedRouteModel:
    def predict(self, text):
        if "plan" in text:
            return RoutePrediction("planning", "planner_transformer", (), 0.9, HASH_A)
        return RoutePrediction("coding", "left_hemisphere", (), 0.9, HASH_A)


def test_evaluate_routes_scores_macro_f1_and_shuffled_labels_drop():
    cases = [
        {"text": "debug code", "domain": "coding", "primary_role": "left_hemisphere"},
        {"text": "make a plan", "domain": "planning", "primary_role": "planner_transformer", "protected": True},
    ]

    metrics_ok = evaluate_routes(FixedRouteModel(), cases)
    metrics_shuffled = evaluate_routes(
        FixedRouteModel(),
        [
            {**cases[0], "primary_role": "planner_transformer"},
            {**cases[1], "primary_role": "left_hemisphere"},
        ],
    )

    assert metrics_ok["macro_f1"] == 100.0
    assert metrics_ok["protected_domain_floor_delta"] == 0.0
    assert metrics_ok["protected_support"] == 1
    assert metrics_shuffled["macro_f1"] == 0.0


class FixedRuntime:
    def __init__(self, text="safe answer", role="left_hemisphere", error=None):
        self.text = text
        self.role = role
        self.error = error

    def generate(self, role, prompt, max_new_tokens=80):
        return GenerationResult(
            self.text,
            self.role,
            "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt",
            HASH_A,
            max(0, len(self.text.split())),
            0.01,
            100.0,
            "length",
            self.error,
        )


class SometimesExplodingRuntime:
    def __init__(self):
        self.calls = 0

    def generate(self, role, prompt, max_new_tokens=80):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("generation exploded")
        return GenerationResult(
            "safe answer",
            role,
            "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt",
            HASH_A,
            2,
            0.01,
            100.0,
            "length",
        )


def test_evaluate_answers_tracks_composite_protected_malformed_and_repetition():
    cases = [
        {"prompt": "identity", "expected": "safe answer", "protected": True},
        {"prompt": "freeform", "expected_contains": "answer"},
    ]

    good = evaluate_answers(FixedRuntime(), cases)
    repetitive = evaluate_answers(FixedRuntime("ha ha ha ha ha ha"), cases)
    malformed = evaluate_answers(FixedRuntime("", error="empty"), cases)

    assert good["composite"] == 100.0
    assert good["protected_perfect"] is True
    assert good["malformed_rate"] == 0.0
    assert repetitive["repetition_rate"] == 1.0
    assert malformed["malformed_rate"] == 1.0


def test_evaluate_answers_traces_include_role_and_protected_flag():
    cases = [
        {
            "prompt": "identity",
            "role": "memory_transformer",
            "expected": "safe answer",
            "protected": True,
        }
    ]

    result = evaluate_answers(FixedRuntime(role="memory_transformer"), cases)

    assert result["traces"][0]["role"] == "memory_transformer"
    assert result["traces"][0]["protected"] is True


def test_evaluate_answers_requires_all_required_terms_for_protected_bank_cases():
    cases = [
        {
            "prompt": "explain the sealed thing",
            "role": "critic_conscience_transformer",
            "required_terms": ["sealed", "evidence"],
            "protected": True,
        }
    ]

    good = evaluate_answers(FixedRuntime("sealed evidence"), cases)
    missing_term = evaluate_answers(FixedRuntime("sealed but vague"), cases)
    no_protected = evaluate_answers(FixedRuntime("anything"), [{"prompt": "freeform"}])

    assert good["protected_support"] == 1
    assert good["protected_perfect"] is True
    assert missing_term["protected_support"] == 1
    assert missing_term["protected_perfect"] is False
    assert no_protected["protected_support"] == 0
    assert no_protected["protected_perfect"] is False


def test_evaluate_answers_records_generation_exceptions_and_continues():
    cases = [
        {"prompt": "identity", "expected": "safe answer", "protected": True},
        {"prompt": "freeform", "expected": "safe answer"},
    ]

    result = evaluate_answers(SometimesExplodingRuntime(), cases)

    assert result["composite"] == 50.0
    assert result["malformed_rate"] == 0.5
    assert result["protected_perfect"] is False
    assert result["traces"][0]["ok"] is False
    assert result["traces"][0]["malformed"] is True
    assert result["traces"][0]["correct"] is False
    assert "generation exploded" in result["traces"][0]["error"]
    assert result["traces"][1]["ok"] is True
    assert result["traces"][1]["correct"] is True


def test_evaluate_stability_normalizes_reload_confirmation_and_regression_state():
    stable = evaluate_stability(
        FixedRuntime(),
        {"reload_ok": True, "confirmation_ok": True, "regressions": []},
    )
    unstable = evaluate_stability(
        FixedRuntime(),
        {"reload_ok": False, "confirmation_ok": True, "regressions": ["lost arithmetic"]},
    )

    assert stable["score"] == 100.0
    assert stable["regressions"] == 0
    assert unstable["score"] < stable["score"]
    assert unstable["regressions"] == 1


def test_run_negative_controls_rejects_known_bad_candidates(tmp_path):
    report = run_negative_controls(
        tmp_path,
        {
            "routes": [
                {"text": "debug code", "domain": "coding", "primary_role": "left_hemisphere"},
                {"text": "make a plan", "domain": "planning", "primary_role": "planner_transformer"},
            ],
            "baseline": metrics(80.0, 80.0, 80.0),
        },
    )

    assert report["passed"] is True
    assert {
        "shuffled_route_labels",
        "absent_checkpoints",
        "invalid_checkpoint_payloads",
        "repetitive_output",
        "empty_output",
        "random_weights_candidate",
        "promotion_data_leak",
        "transformer_source_without_checkpoint",
    }.issubset(report["controls"])
    assert all(item["rejected"] is True for item in report["controls"].values())
    assert "missing" in report["controls"]["absent_checkpoints"]["error"].lower()
    assert "checkpoint" in report["controls"]["absent_checkpoints"]["error"].lower()
    assert "invalid" in report["controls"]["invalid_checkpoint_payloads"]["error"].lower()
    assert "checkpoint" in report["controls"]["invalid_checkpoint_payloads"]["error"].lower()


def test_shuffled_route_negative_control_corrupts_homogeneous_roles(tmp_path):
    report = run_negative_controls(
        tmp_path,
        {
            "routes": [
                {"text": "debug code", "domain": "coding", "primary_role": "left_hemisphere"},
                {"text": "fix python", "domain": "coding", "primary_role": "left_hemisphere"},
            ],
            "baseline": metrics(80.0, 80.0, 80.0),
        },
    )

    control = report["controls"]["shuffled_route_labels"]
    assert control["rejected"] is True
    assert control["metrics"]["macro_f1"] < control["metrics"]["original_macro_f1"]
    assert control["metrics"]["corrupted"] is True


def test_negative_control_candidate_scores_are_clamped_to_100(tmp_path):
    report = run_negative_controls(
        tmp_path,
        {
            "routes": [
                {"text": "debug code", "domain": "coding", "primary_role": "left_hemisphere"},
                {"text": "make a plan", "domain": "planning", "primary_role": "planner_transformer"},
            ],
            "baseline": metrics(99.0, 99.0, 99.0),
        },
    )

    for control in report["controls"].values():
        decision = control.get("decision")
        if decision:
            assert decision["candidate_joint"] <= 100.0


def test_zero_protected_support_blocks_promotion():
    candidate = metrics(75.0, 76.0, 74.0)
    candidate["routing"]["protected_support"] = 0
    candidate["answers"]["protected_support"] = 0
    candidate["answers"]["protected_perfect"] = True

    decision = decide_promotion(
        baseline=metrics(70.0, 70.0, 70.0),
        candidate=candidate,
        previous_winner=None,
    )

    assert decision.verdict == "REJECTED"
    assert any("protected support" in reason.lower() for reason in decision.reasons)
