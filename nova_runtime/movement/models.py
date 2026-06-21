from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ExecutionTier = Literal["avatar", "simulation", "shadow", "physical"]


@dataclass(frozen=True)
class MovementIntent:
    action: str
    source: Literal["owner", "task", "self", "safety"] = "owner"
    execution_tier: ExecutionTier = "avatar"
    target: str | None = None
    speed: float = 0.5
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JointTarget:
    joint: str
    position: float
    velocity: float
    effort: float = 0.0


@dataclass(frozen=True)
class MovementPlan:
    intent: MovementIntent
    duration_ms: int
    targets: tuple[JointTarget, ...]
    expression: str
    recovery_action: str = "neutral"


@dataclass(frozen=True)
class MovementResult:
    accepted: bool
    status: str
    reason: str
    body_state: dict[str, Any]
    evidence: dict[str, Any]
