from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_runtime.eval_bank import (  # noqa: E402
    REQUIRED_BEHAVIOR_CATEGORIES,
    BehaviorEvalCase,
    BehaviorEvalBank,
    load_behavior_eval_bank,
    score_behavior_eval_bank,
)
from nova_capability_eval import load_behavior_eval_bank as load_behavior_eval_bank_from_capability  # noqa: E402


def test_behavior_eval_bank_covers_required_categories() -> None:
    bank = load_behavior_eval_bank(ROOT / "tests" / "fixtures" / "nova_creature_behavior_eval_bank.json")
    categories = {case.category for case in bank.cases}

    assert REQUIRED_BEHAVIOR_CATEGORIES <= categories


def test_behavior_eval_bank_loader_round_trips_json(tmp_path: Path) -> None:
    bank = BehaviorEvalBank(
        bank_id="demo",
        version="1.0",
        cases=(
            BehaviorEvalCase(
                case_id="one",
                category="conversation_quality",
                prompt="Prompt",
                expected_behavior="Expected",
                required_evidence=("tone",),
                pass_criteria="Criteria",
            ),
            BehaviorEvalCase(
                case_id="two",
                category="memory_recall",
                prompt="Prompt 2",
                expected_behavior="Expected 2",
                required_evidence=("memory",),
                pass_criteria="Criteria 2",
            ),
            BehaviorEvalCase(
                case_id="three",
                category="planning",
                prompt="Prompt 3",
                expected_behavior="Expected 3",
                required_evidence=("plan",),
                pass_criteria="Criteria 3",
            ),
            BehaviorEvalCase(
                case_id="four",
                category="tool_choice",
                prompt="Prompt 4",
                expected_behavior="Expected 4",
                required_evidence=("tool",),
                pass_criteria="Criteria 4",
            ),
            BehaviorEvalCase(
                case_id="five",
                category="tool_refusal",
                prompt="Prompt 5",
                expected_behavior="Expected 5",
                required_evidence=("refusal",),
                pass_criteria="Criteria 5",
            ),
            BehaviorEvalCase(
                case_id="six",
                category="self_correction",
                prompt="Prompt 6",
                expected_behavior="Expected 6",
                required_evidence=("correction",),
                pass_criteria="Criteria 6",
            ),
            BehaviorEvalCase(
                case_id="seven",
                category="research_accuracy",
                prompt="Prompt 7",
                expected_behavior="Expected 7",
                required_evidence=("evidence",),
                pass_criteria="Criteria 7",
            ),
            BehaviorEvalCase(
                case_id="eight",
                category="multi_step_completion",
                prompt="Prompt 8",
                expected_behavior="Expected 8",
                required_evidence=("step",),
                pass_criteria="Criteria 8",
            ),
        ),
    )

    destination = tmp_path / "behavior_eval_bank.json"
    from nova_runtime.eval_bank import save_behavior_eval_bank

    save_behavior_eval_bank(bank, destination)
    loaded = load_behavior_eval_bank(destination)

    assert loaded == bank


def test_behavior_eval_bank_scoring_summarizes_results() -> None:
    bank = load_behavior_eval_bank(ROOT / "tests" / "fixtures" / "nova_creature_behavior_eval_bank.json")

    def judge(case: BehaviorEvalCase) -> tuple[bool, dict[str, object]]:
        return True, {"evidence": list(case.required_evidence), "semantic_score": 1.0}

    report = score_behavior_eval_bank(bank, judge)

    assert report["total"] == len(bank.cases)
    assert report["passed"] == len(bank.cases)
    assert report["failed"] == 0
    assert report["score"] == 1.0
    assert REQUIRED_BEHAVIOR_CATEGORIES <= set(report["categories"])


def test_capability_eval_exports_behavior_bank_loader() -> None:
    bank = load_behavior_eval_bank_from_capability(ROOT / "tests" / "fixtures" / "nova_creature_behavior_eval_bank.json")

    assert bank.bank_id == "nova_creature_behavior_eval_bank"
