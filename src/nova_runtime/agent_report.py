"""Structured agent report for audited autonomous Nova runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class StructuredAgentReportSection:
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StructuredAgentReport:
    goal: str
    plan: list[str]
    tools_used: list[str]
    files_changed: list[str]
    tests_executed: list[str]
    browser_evidence: dict[str, Any]
    failures_and_retries: list[dict[str, Any]]
    final_verification: dict[str, Any]
    unresolved_blockers: list[str]
    rollback_information: dict[str, Any]
    sections: list[StructuredAgentReportSection] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sections"] = [section.to_dict() for section in self.sections]
        return data


@dataclass(frozen=True, slots=True)
class OrchestratedRunResult:
    run: Any
    report: StructuredAgentReport
    workspace_root: str
    report_path: str
    proof_artifacts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": getattr(self.run, "state", self.run),
            "report": self.report.to_dict(),
            "workspace_root": self.workspace_root,
            "report_path": self.report_path,
            "proof_artifacts": dict(self.proof_artifacts),
        }


__all__ = [
    "OrchestratedRunResult",
    "StructuredAgentReport",
    "StructuredAgentReportSection",
]
