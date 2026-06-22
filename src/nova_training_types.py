from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

ROLE_NAMES = (
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
)
DOMAIN_NAMES = (
    "coding",
    "math",
    "science",
    "philosophy",
    "psychology",
    "creative",
    "memory_recall",
    "planning",
    "critic",
    "speech",
    "dream",
    "general",
)


@dataclass(frozen=True)
class GenerationResult:
    text: str
    role: str
    checkpoint_path: str
    checkpoint_hash: str
    tokens_generated: int
    elapsed_seconds: float
    tokens_per_second: float
    finish_reason: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip()) and bool(self.checkpoint_hash)

    @classmethod
    def failed(cls, role: str, error: str) -> "GenerationResult":
        return cls("", role, "", "", 0, 0.0, 0.0, "error", error)

    def to_trace(self) -> dict:
        return {"source": "transformer", **asdict(self), "ok": self.ok}


@dataclass(frozen=True)
class RoutePrediction:
    domain: str
    primary_role: str
    support_roles: Sequence[str]
    confidence: float
    model_hash: str
    source: str = "learned_route_model"


@dataclass(frozen=True)
class PromotionDecision:
    verdict: str
    reasons: Sequence[str]
    baseline_joint: float
    candidate_joint: float
    previous_winner_joint: float | None
