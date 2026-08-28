from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_runtime.agent_report import StructuredAgentReport, StructuredAgentReportSection  # noqa: E402


def test_agent_report_includes_required_sections() -> None:
    report = StructuredAgentReport(
        goal="update one project file and verify it",
        plan=["read", "edit", "test", "verify"],
        tools_used=["filesystem.read", "filesystem.write", "terminal.run", "playwright.verify"],
        files_changed=["src/example.py"],
        tests_executed=["pytest tests/test_example.py -q"],
        browser_evidence={"screenshot_hash": "abc"},
        failures_and_retries=[],
        final_verification={"passed": True},
        unresolved_blockers=[],
        rollback_information={"available": True},
        sections=[StructuredAgentReportSection(title="plan", content="read -> edit -> test -> verify")],
    )

    public = report.to_dict()

    assert public["goal"] == "update one project file and verify it"
    assert "tests_executed" in public
    assert public["sections"][0]["title"] == "plan"
