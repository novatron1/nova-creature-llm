#!/usr/bin/env python3
"""Print Deep Intelligence Report (v621-v650)"""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import importlib, json

MODULES = [
    ("v621_logic_proof_gym", "run_logic_proof", 621, "Logic Proof Gym"),
    ("v622_math_reasoning_ladder", "run_math_ladder", 622, "Math Reasoning Ladder"),
    ("v623_causal_reasoning_brain", "reason_causal", 623, "Causal Reasoning Brain"),
    ("v624_counterfactual_simulator", "simulate_counterfactual", 624, "Counterfactual Simulator"),
    ("v625_strategy_war_room", "run_strategy_war_room", 625, "Strategy War Room"),
    ("v626_long_plan_consistency_test", "test_long_plan_consistency", 626, "Long-Plan Consistency Test"),
    ("v627_multi_step_problem_solver", "solve_multi_step", 627, "Multi-Step Problem Solver"),
    ("v628_memory__plus_reasoning_combo_test", "test_memory_reasoning_combo", 628, "Memory + Reasoning Combo Test"),
    ("v629_creativity_under_constraint", "create_under_constraint", 629, "Creativity Under Constraint"),
    ("v630_compression_brain", "compress_knowledge", 630, "Compression Brain"),
    ("v631_analogy_generator", "generate_analogy", 631, "Analogy Generator"),
    ("v632_pattern_discovery_brain", "discover_pattern", 632, "Pattern Discovery Brain"),
    ("v633_hidden_assumption_detector", "detect_hidden_assumption", 633, "Hidden Assumption Detector"),
    ("v634_explanation_quality_trainer", "train_explanation_quality", 634, "Explanation Quality Trainer"),
    ("v635_emotional_intelligence_mode", "run_emotional_intelligence", 635, "Emotional Intelligence Mode"),
    ("v636_negotiation_simulator", "simulate_negotiation", 636, "Negotiation Simulator"),
    ("v637_teaching_mode", "teach_concept", 637, "Teaching Mode"),
    ("v638_socratic_question_brain", "ask_socratic_question", 638, "Socratic Question Brain"),
    ("v639_world_model_builder", "build_world_model", 639, "World Model Builder"),
    ("v640_prediction_tracker", "track_prediction", 640, "Prediction Tracker"),
    ("v641_model_mistake_classifier", "classify_model_mistake", 641, "Model Mistake Classifier"),
    ("v642_hard_benchmark_tournament", "run_hard_benchmark_tournament", 642, "Hard Benchmark Tournament"),
    ("v643_intelligence_gain_meter", "measure_intelligence_gain", 643, "Intelligence Gain Meter"),
    ("v644_self_correction_reflex", "run_self_correction_reflex", 644, "Self-Correction Reflex"),
    ("v645_deep_focus_mode", "activate_deep_focus", 645, "Deep Focus Mode"),
    ("v646_fast_recall_mode", "activate_fast_recall", 646, "Fast Recall Mode"),
    ("v647_precision_answer_mode", "activate_precision_mode", 647, "Precision Answer Mode"),
    ("v648_big_picture_mode", "activate_big_picture_mode", 648, "Big Picture Mode"),
    ("v649_intelligence_regression_trap", "test_intelligence_regression", 649, "Intelligence Regression Trap"),
    ("v650_deep_intelligence_report", "generate_deep_intelligence_report", 650, "Deep Intelligence Report"),
]

def main():
    print("=" * 60)
    print("Nova Deep Intelligence Report (v621-v650)")
    print("=" * 60)
    results = {}
    for slug, funcname, num, display in MODULES:
        try:
            mod = importlib.import_module(slug)
            fn = getattr(mod, funcname)
            r = fn()
            results[slug] = r
            icon = "\U0001f7e2" if r.get("safe") else "\U0001f534"
            print(f"  {icon} v{num:03d} - {display}")
        except Exception as e:
            print(f"  \u26a0 v{num:03d} - {display}: {e}")

    from v650_deep_intelligence_report import generate_deep_intelligence_report
    rpt = generate_deep_intelligence_report()
    print(f"\n{'=' * 60}")
    print(f"Report fields: {len(rpt)}")
    print(f"Safe: {rpt.get('safe', 'N/A')}")
    print(f"Version: {rpt.get('version', 'N/A')}")
    (ROOT / "reports" / "v621_to_v650_deep_intelligence_status.json").write_text(
        json.dumps(rpt if isinstance(rpt, dict) else results, indent=2)
    )
    print("Report saved to reports/v621_to_v650_deep_intelligence_status.json")
if __name__ == "__main__":
    raise SystemExit(main())
