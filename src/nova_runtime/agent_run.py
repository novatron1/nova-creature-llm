"""Canonical agent run state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .contracts import RunContract


class AgentRunState(str, Enum):
    PLANNED = "planned"
    AUTHORIZED = "authorized"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


_ALLOWED_TRANSITIONS: dict[AgentRunState, set[AgentRunState]] = {
    AgentRunState.PLANNED: {AgentRunState.AUTHORIZED, AgentRunState.FAILED},
    AgentRunState.AUTHORIZED: {AgentRunState.EXECUTING, AgentRunState.FAILED},
    AgentRunState.EXECUTING: {AgentRunState.VERIFYING, AgentRunState.FAILED, AgentRunState.ROLLED_BACK},
    AgentRunState.VERIFYING: {AgentRunState.COMPLETED, AgentRunState.FAILED, AgentRunState.ROLLED_BACK},
    AgentRunState.COMPLETED: set(),
    AgentRunState.FAILED: set(),
    AgentRunState.ROLLED_BACK: set(),
}


@dataclass(slots=True)
class AgentRun:
    contract: RunContract
    state: AgentRunState = AgentRunState.PLANNED
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, contract: RunContract) -> "AgentRun":
        run = cls(contract=contract)
        run._record_state(reason="run created")
        return run

    def _record_state(self, *, reason: str) -> None:
        self.history.append(
            {
                "state": self.state.value,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "contract_hash": self.contract.contract_hash,
            }
        )

    def transition(self, new_state: AgentRunState, *, reason: str) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.state]
        if new_state not in allowed:
            raise ValueError(f"Invalid AgentRun transition from {self.state.value!r} to {new_state.value!r}.")
        self.state = new_state
        self._record_state(reason=reason)
