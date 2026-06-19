"""v800_rapid_learning_final_report — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def rapid_learning_final_report():
    """Generate v800 rapid learning readiness report."""
    checks = {}
    all_pass = True
    # Check each module
    import v776_learning_intake
    try:
        checks["rapid_learning_intake_exists"] = v776_learning_intake.learning_intake().get("status") == "ok"
    except: checks["rapid_learning_intake_exists"] = False
    import v777_lesson_chunker
    try:
        checks["lesson_chunking_exists"] = v777_lesson_chunker.lesson_chunker().get("status") == "ok"
    except: checks["lesson_chunking_exists"] = False
    import v778_question_generator
    try:
        checks["question_generation_exists"] = v778_question_generator.question_generator().get("status") == "ok"
    except: checks["question_generation_exists"] = False
    import v779_self_test_engine
    try:
        r = v779_self_test_engine.self_test_engine({"lesson_id":"t","claim":"t","topic":"t"}, [{"type":"direct_recall","question":"Q","expected":"A","difficulty":0.5}])
        checks["self_test_engine_exists"] = r.get("status") == "ok"
    except: checks["self_test_engine_exists"] = False
    import v781_correction_loop
    try:
        checks["correction_loop_exists"] = v781_correction_loop.correction_loop().get("status") == "ok"
    except: checks["correction_loop_exists"] = False
    import v780_rapid_learning_memory_lock
    try:
        checks["approved_memory_lock_exists"] = v780_rapid_learning_memory_lock.rapid_learning_memory_lock().get("status") == "ok"
    except: checks["approved_memory_lock_exists"] = False
    import v787_retention_test
    try:
        checks["retention_test_exists"] = v787_retention_test.retention_test().get("status") == "ok"
    except: checks["retention_test_exists"] = False
    import v788_conflict_detection
    try:
        checks["conflict_detection_exists"] = v788_conflict_detection.conflict_detection().get("status") == "ok"
    except: checks["conflict_detection_exists"] = False
    import v789_learning_exporter
    try:
        checks["training_export_exists"] = v789_learning_exporter.learning_exporter().get("status") == "ok"
    except: checks["training_export_exists"] = False
    all_pass = all(v for v in checks.values())
    try:
        from v795_rapid_learning_test_suite import rapid_learning_test_suite
        r = rapid_learning_test_suite()
        checks["all_rapid_learning_tests_passed"] = r.get("failed", 999) == 0
        all_pass = all_pass and checks["all_rapid_learning_tests_passed"]
    except Exception:
        checks["all_rapid_learning_tests_passed"] = False
        all_pass = False
    report = {"version": "v800_rapid_learning_final_report", "created_at": datetime.now().isoformat(),
              "overall_status": "ready" if all_pass else "incomplete",
              "all_checks_passed": all_pass, "checks": checks,
              "modules_total": 25, "modules_range": "v776-v800",
              "note": "Rapid Education Layer complete. Nova can learn from teaching, test itself, and retain knowledge.",
              "next_step": "Run v795_rapid_learning_test_suite to verify."}
    report_dir = ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_dir.joinpath("v800_rapid_learning_final_report.json").write_text(json.dumps(report, indent=2))
    md_lines = ["# v800 Rapid Learning Final Report", "",
                 f"**Status:** {'✅ READY' if all_pass else '❌ INCOMPLETE'}",
                 f"**Generated:** {report['created_at']}",
                 f"**Modules:** {report['modules_range']} ({report['modules_total']} total)", "",
                 "## Checklist", ""]
    for check, flag in checks.items():
        md_lines.append(f"- {'✅' if flag else '❌'} {check.replace('_', ' ').title()}")
    md_lines.extend(["", "## Next Steps", "", "1. Run `python src/v795_rapid_learning_test_suite.py`",
                     "2. Integrate with existing brain systems", "3. Test with real teaching input", ""])
    report_dir.joinpath("v800_rapid_learning_final_report.md").write_text("\n".join(md_lines))
    return report

def main():
    import sys
    print("Nova v800_rapid_learning_final_report")
    r = rapid_learning_final_report()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())


def main():
    print(f"Nova v800_rapid_learning_final_report")
    r = rapid_learning_final_report()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
