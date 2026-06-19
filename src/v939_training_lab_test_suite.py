"""v939_training_lab_test_suite — Whole-Brain Training Lab"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

def training_lab_test_suite():
    """Tests for training lab: baseline, serial, parallel, interleaved, cross-brain, retention, regression, memory lock, quarantine, winner."""
    tests=[]; passed=0; failed=0
    for mod,func,name in [
        ("v902_baseline_benchmark_runner", "baseline_benchmark_runner", "baseline_benchmark"),
        ("v904_serial_training_experiment", "serial_training_experiment", "serial_training"),
        ("v905_parallel_training_experiment", "parallel_training_experiment", "parallel_training"),
        ("v906_interleaved_training_experiment", "interleaved_training_experiment", "interleaved_training"),
        ("v907_cross_brain_training_experiment", "cross_brain_training_experiment", "cross_brain_training"),
        ("v908_retention_benchmark_engine", "retention_benchmark_engine", "retention_testing"),
        ("v912_regression_guard", "regression_guard", "regression_guard"),
        ("v913_parallel_training_memory_lock", "parallel_training_memory_lock", "memory_lock"),
        ("v914_failed_training_quarantine", "failed_training_quarantine", "failed_quarantine"),
        ("v929_training_style_winner_selector", "training_style_winner_selector", "winner_selection"),
    ]:
        try:
            exec(f"from {mod} import {func}")
            r = eval(f"{func}()")
            ok = r.get("status") == "ok"
            tests.append({"test": name, "passed": ok})
            passed+=ok; failed+=not ok
        except Exception as e:
            tests.append({"test": name, "passed": False, "detail": str(e)})
            failed+=1
    return {"version": "v939_training_lab_test_suite", "created_at": datetime.now().isoformat(),
            "total_tests": len(tests), "passed": passed, "failed": failed, "status": "ok" if failed==0 else "partial"}

def main():
    print(f"Nova v939_training_lab_test_suite")
    r = training_lab_test_suite()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
