"""Immutable runtime contracts for autonomous Nova Creature jobs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RunContract:
    run_id: str
    goal: str
    goal_hash: str
    goal_summary: str
    owner_id: str
    project_id: str
    workspace_root: str
    allowed_roots: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    allowed_resources: tuple[str, ...]
    time_budget_seconds: int
    tool_budget: int
    cost_budget: float
    memory_budget: int
    created_at: str
    contract_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_hash_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("contract_hash", None)
        return payload

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_run_contract(
    *,
    run_id: str,
    goal: str,
    owner_id: str,
    project_id: str,
    workspace_root: str,
    allowed_roots: list[str] | tuple[str, ...],
    allowed_tools: list[str] | tuple[str, ...],
    allowed_resources: list[str] | tuple[str, ...],
    time_budget_seconds: int,
    tool_budget: int,
    cost_budget: float,
    memory_budget: int,
    metadata: dict[str, Any] | None = None,
) -> RunContract:
    created_at = datetime.now(timezone.utc).isoformat()
    goal_text = " ".join(str(goal or "").split())
    payload = {
        "run_id": run_id,
        "goal": goal_text,
        "goal_hash": sha256_json(goal_text),
        "goal_summary": goal_text,
        "owner_id": owner_id,
        "project_id": project_id,
        "workspace_root": workspace_root,
        "allowed_roots": list(allowed_roots),
        "allowed_tools": list(allowed_tools),
        "allowed_resources": list(allowed_resources),
        "time_budget_seconds": int(time_budget_seconds),
        "tool_budget": int(tool_budget),
        "cost_budget": float(cost_budget),
        "memory_budget": int(memory_budget),
        "created_at": created_at,
        "metadata": dict(metadata or {}),
    }
    contract_hash = sha256_json(payload)
    return RunContract(
        run_id=run_id,
        goal=goal_text,
        goal_hash=payload["goal_hash"],
        goal_summary=goal_text,
        owner_id=owner_id,
        project_id=project_id,
        workspace_root=workspace_root,
        allowed_roots=tuple(str(item) for item in allowed_roots),
        allowed_tools=tuple(str(item) for item in allowed_tools),
        allowed_resources=tuple(str(item) for item in allowed_resources),
        time_budget_seconds=int(time_budget_seconds),
        tool_budget=int(tool_budget),
        cost_budget=float(cost_budget),
        memory_budget=int(memory_budget),
        created_at=created_at,
        contract_hash=contract_hash,
        metadata=dict(metadata or {}),
    )
