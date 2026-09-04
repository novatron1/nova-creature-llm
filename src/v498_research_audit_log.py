"""v498 — Research Audit Log"""
from __future__ import annotations
from pathlib import Path

from nova_runtime.ledger import EvidenceLedger
from nova_runtime.research_scheduler import ResearchScheduler


STORE_PATH = Path("data") / "research_tasks.jsonl"


def log_research_audit() -> dict:
    ledger = EvidenceLedger(STORE_PATH)
    scheduler = ResearchScheduler(STORE_PATH)
    snapshot = scheduler.snapshot()
    return {
        "version": "v498_research_audit_log",
        "created_at": scheduler._now(),
        "sim_only": False,
        "real_hardware_enabled": False,
        "real_robot_movement_allowed": False,
        "durable_task_records": len(snapshot),
        "ledger_entries": len(ledger.entries()),
        "open_tasks": len(scheduler.recover_pending_tasks()),
        "task_ids": sorted(snapshot.keys()),
        "note": "Research Audit Log now reads durable scheduler and evidence ledger state.",
    }

def main():
    print(f"Nova v498_research_audit_log\n")
    r = log_research_audit()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
