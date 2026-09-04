"""Durable research task scheduler with restart-safe budgets."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import uuid

from .contracts import sha256_json
from .ledger import EvidenceLedger


@dataclass(frozen=True, slots=True)
class ResearchTaskRecord:
    task_id: str
    run_id: str
    objective: str
    status: str
    attempt_count: int
    tool_budget: int
    time_budget_seconds: int
    cost_budget: float
    created_at: str
    updated_at: str
    next_retry_at: str | None
    last_heartbeat_at: str | None
    priority_score: float = 0.0
    safety_score: float = 1.0
    tool_usage_count: int = 0
    cost_used: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def remaining_tool_budget(self) -> int:
        return max(0, int(self.tool_budget) - int(self.tool_usage_count))

    def remaining_cost_budget(self) -> float:
        return max(0.0, float(self.cost_budget) - float(self.cost_used))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResearchResumeState:
    task_id: str
    run_id: str
    objective: str
    status: str
    attempt_count: int
    priority_score: float
    safety_score: float
    next_retry_at: str | None
    last_heartbeat_at: str | None
    tool_budget_remaining: int
    cost_budget_remaining: float
    time_budget_seconds: int
    resume_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BudgetExceededError(RuntimeError):
    pass


class ResearchScheduler:
    def __init__(
        self,
        store_path: str | Path,
        *,
        priority_ranker: Callable[[str], Any] | None = None,
        safety_gate: Callable[[str], Any] | None = None,
    ) -> None:
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger = EvidenceLedger(self.store_path)
        self.priority_ranker = priority_ranker
        self.safety_gate = safety_gate

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _snapshot(self) -> dict[str, ResearchTaskRecord]:
        tasks: dict[str, dict[str, Any]] = {}
        for entry in self.ledger.entries():
            payload = dict(entry.payload or {})
            task_id = str(payload.get("task_id") or "")
            if not task_id:
                continue
            status = str(payload.get("status") or tasks.get(task_id, {}).get("status") or "pending")
            previous = dict(tasks.get(task_id) or {})
            if entry.event_type == "task_created":
                previous = {
                    "task_id": task_id,
                    "run_id": str(payload.get("run_id") or ""),
                    "objective": str(payload.get("objective") or ""),
                    "status": status,
                    "attempt_count": int(payload.get("attempt_count") or 0),
                    "tool_budget": int(payload.get("tool_budget") or 0),
                    "time_budget_seconds": int(payload.get("time_budget_seconds") or 0),
                    "cost_budget": float(payload.get("cost_budget") or 0.0),
                    "created_at": str(payload.get("created_at") or entry.timestamp),
                    "updated_at": str(payload.get("updated_at") or entry.timestamp),
                    "next_retry_at": payload.get("next_retry_at"),
                    "last_heartbeat_at": payload.get("last_heartbeat_at"),
                    "priority_score": float(payload.get("priority_score") or 0.0),
                    "safety_score": float(payload.get("safety_score") or 1.0),
                    "tool_usage_count": int(payload.get("tool_usage_count") or 0),
                    "cost_used": float(payload.get("cost_used") or 0.0),
                    "metadata": dict(payload.get("metadata") or {}),
                }
            else:
                previous.update(
                    {
                        key: value
                        for key, value in payload.items()
                        if key not in {"task_id", "task_event", "event_type"}
                    }
                )
                previous["status"] = str(payload.get("status") or previous.get("status") or status)
                previous["updated_at"] = str(payload.get("updated_at") or entry.timestamp)
            tasks[task_id] = previous
        return {
            task_id: ResearchTaskRecord(
                task_id=str(data["task_id"]),
                run_id=str(data.get("run_id") or ""),
                objective=str(data.get("objective") or ""),
                status=str(data.get("status") or "pending"),
                attempt_count=int(data.get("attempt_count") or 0),
                tool_budget=int(data.get("tool_budget") or 0),
                time_budget_seconds=int(data.get("time_budget_seconds") or 0),
                cost_budget=float(data.get("cost_budget") or 0.0),
                created_at=str(data.get("created_at") or self._now()),
                updated_at=str(data.get("updated_at") or self._now()),
                next_retry_at=(str(data.get("next_retry_at")) if data.get("next_retry_at") else None),
                last_heartbeat_at=(str(data.get("last_heartbeat_at")) if data.get("last_heartbeat_at") else None),
                priority_score=float(data.get("priority_score") or 0.0),
                safety_score=float(data.get("safety_score") or 1.0),
                tool_usage_count=int(data.get("tool_usage_count") or 0),
                cost_used=float(data.get("cost_used") or 0.0),
                metadata=dict(data.get("metadata") or {}),
            )
            for task_id, data in tasks.items()
        }

    def snapshot(self) -> dict[str, ResearchTaskRecord]:
        return self._snapshot()

    def create_task(
        self,
        *,
        objective: str,
        tool_budget: int,
        time_budget_seconds: int,
        cost_budget: float,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ResearchTaskRecord:
        task_id = "research_" + uuid.uuid4().hex[:12]
        now = self._now()
        priority = self._rank(objective)
        safety = self._gate(objective)
        record = ResearchTaskRecord(
            task_id=task_id,
            run_id=str(run_id or task_id),
            objective=str(objective),
            status="pending",
            attempt_count=0,
            tool_budget=max(1, int(tool_budget)),
            time_budget_seconds=max(1, int(time_budget_seconds)),
            cost_budget=max(0.0, float(cost_budget)),
            created_at=now,
            updated_at=now,
            next_retry_at=None,
            last_heartbeat_at=None,
            priority_score=priority,
            safety_score=safety,
            metadata=dict(metadata or {}),
        )
        self.ledger.append(
            event_type="task_created",
            payload=record.to_dict(),
            metadata={"objective_hash": sha256_json(objective)},
        )
        return record

    def mark_running(self, task_id: str) -> ResearchTaskRecord:
        record = self._require(task_id)
        updated = replace(
            record,
            status="running",
            attempt_count=record.attempt_count + 1,
            updated_at=self._now(),
            last_heartbeat_at=self._now(),
        )
        self._append_transition(updated, event_type="task_running")
        return updated

    def heartbeat(self, task_id: str) -> ResearchTaskRecord:
        record = self._require(task_id)
        updated = replace(record, last_heartbeat_at=self._now(), updated_at=self._now())
        self._append_transition(updated, event_type="task_heartbeat")
        return updated

    def record_tool_use(self, task_id: str, *, tool_name: str, cost: float = 0.0) -> ResearchTaskRecord:
        record = self._require(task_id)
        if record.tool_usage_count + 1 > record.tool_budget:
            self._append_transition(
                replace(
                    record,
                    status="blocked_budget",
                    updated_at=self._now(),
                ),
                event_type="task_budget_blocked",
                extra={"tool_name": tool_name, "reason": "tool_budget"},
            )
            raise BudgetExceededError(f"Task {task_id!r} exceeded its tool budget.")
        if record.cost_used + float(cost) > record.cost_budget:
            self._append_transition(
                replace(
                    record,
                    status="blocked_budget",
                    updated_at=self._now(),
                ),
                event_type="task_budget_blocked",
                extra={"tool_name": tool_name, "reason": "cost_budget"},
            )
            raise BudgetExceededError(f"Task {task_id!r} exceeded its cost budget.")
        updated = replace(
            record,
            tool_usage_count=record.tool_usage_count + 1,
            cost_used=record.cost_used + float(cost),
            updated_at=self._now(),
        )
        self._append_transition(updated, event_type="task_tool_use", extra={"tool_name": tool_name, "cost": float(cost)})
        return updated

    def complete_task(self, task_id: str, *, summary: str = "") -> ResearchTaskRecord:
        record = self._require(task_id)
        updated = replace(record, status="completed", updated_at=self._now())
        self._append_transition(updated, event_type="task_completed", extra={"summary": summary})
        return updated

    def fail_task(self, task_id: str, *, error: str, next_retry_at: str | None = None) -> ResearchTaskRecord:
        record = self._require(task_id)
        updated = replace(record, status="failed", updated_at=self._now(), next_retry_at=next_retry_at)
        self._append_transition(updated, event_type="task_failed", extra={"error": error, "next_retry_at": next_retry_at})
        return updated

    def recover_pending_tasks(self) -> list[ResearchResumeState]:
        records = self._snapshot()
        resumed = []
        for record in records.values():
            if record.status in {"pending", "running", "failed", "paused"}:
                resumed.append(
                    ResearchResumeState(
                        task_id=record.task_id,
                        run_id=record.run_id,
                        objective=record.objective,
                        status=record.status,
                        attempt_count=record.attempt_count,
                        priority_score=record.priority_score,
                        safety_score=record.safety_score,
                        next_retry_at=record.next_retry_at,
                        last_heartbeat_at=record.last_heartbeat_at,
                        tool_budget_remaining=record.remaining_tool_budget(),
                        cost_budget_remaining=record.remaining_cost_budget(),
                        time_budget_seconds=record.time_budget_seconds,
                        resume_reason="restart_recovery",
                    )
                )
        resumed.sort(key=lambda item: (-item.priority_score, item.task_id))
        return resumed

    def dispatch_next(self) -> ResearchResumeState | None:
        candidates = self.recover_pending_tasks()
        if not candidates:
            return None
        candidate = candidates[0]
        if candidate.safety_score < 0.5:
            return replace(candidate, resume_reason="safety_gate_blocked")
        return candidate

    def _rank(self, objective: str) -> float:
        if callable(self.priority_ranker):
            result = self.priority_ranker(objective)
            if isinstance(result, dict):
                for key in ("priority_score", "score", "priority"):
                    value = result.get(key)
                    if isinstance(value, (int, float)):
                        return float(value)
        return 0.5

    def _gate(self, objective: str) -> float:
        if callable(self.safety_gate):
            result = self.safety_gate(objective)
            if isinstance(result, dict):
                for key in ("safety_score", "score", "safety"):
                    value = result.get(key)
                    if isinstance(value, (int, float)):
                        return float(value)
                if "allowed" in result:
                    return 1.0 if bool(result["allowed"]) else 0.0
        return 1.0

    def _require(self, task_id: str) -> ResearchTaskRecord:
        task = self._snapshot().get(task_id)
        if task is None:
            raise KeyError(f"Unknown research task {task_id!r}.")
        return task

    def _append_transition(self, record: ResearchTaskRecord, *, event_type: str, extra: dict[str, Any] | None = None) -> None:
        payload = record.to_dict()
        payload.update(dict(extra or {}))
        self.ledger.append(
            event_type=event_type,
            payload=payload,
            metadata={"task_status": record.status},
        )


__all__ = [
    "BudgetExceededError",
    "ResearchResumeState",
    "ResearchScheduler",
    "ResearchTaskRecord",
]
