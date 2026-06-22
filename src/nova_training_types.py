from __future__ import annotations

import math
import re
from collections.abc import Sequence as ABCSequence
from dataclasses import asdict, dataclass
from typing import Final, Literal, Sequence

RoleName = Literal[
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
]
DomainName = Literal[
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
]
PromotionVerdict = Literal["promote", "hold", "reject"]
FinishReason = Literal["eos", "length", "error"]
RouteSource = Literal["learned_route_model", "transformer"]

ROLE_NAMES: Final[tuple[RoleName, ...]] = (
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
)
DOMAIN_NAMES: Final[tuple[DomainName, ...]] = (
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
FINISH_REASON_NAMES: Final[tuple[FinishReason, ...]] = ("eos", "length", "error")
PROMOTION_VERDICTS: Final[tuple[PromotionVerdict, ...]] = ("promote", "hold", "reject")
ROUTE_SOURCES: Final[tuple[RouteSource, ...]] = ("learned_route_model", "transformer")

_HEX_HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")


@dataclass(frozen=True)
class GenerationResult:
    text: str
    role: RoleName | str
    checkpoint_path: str
    checkpoint_hash: str
    tokens_generated: int
    elapsed_seconds: float
    tokens_per_second: float
    finish_reason: FinishReason | str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return (
            self.error is None
            and bool(self.text.strip())
            and self.role in ROLE_NAMES
            and bool(self.checkpoint_path.strip())
            and bool(_HEX_HASH_RE.fullmatch(self.checkpoint_hash))
            and self.tokens_generated >= 0
            and math.isfinite(self.elapsed_seconds)
            and self.elapsed_seconds >= 0
            and math.isfinite(self.tokens_per_second)
            and self.tokens_per_second >= 0
            and self.finish_reason in FINISH_REASON_NAMES
        )

    @classmethod
    def failed(cls, role: str, error: str) -> "GenerationResult":
        return cls("", role, "", "", 0, 0.0, 0.0, "error", error)

    def to_trace(self) -> dict:
        return {"source": "transformer", **asdict(self), "ok": self.ok}


@dataclass(frozen=True)
class RoutePrediction:
    domain: DomainName | str
    primary_role: RoleName | str
    support_roles: Sequence[str]
    confidence: float
    model_hash: str
    source: RouteSource | str = "learned_route_model"

    def __post_init__(self) -> None:
        if self.domain not in DOMAIN_NAMES:
            raise ValueError(f"invalid domain: {self.domain!r}")
        if self.primary_role not in ROLE_NAMES:
            raise ValueError(f"invalid primary_role: {self.primary_role!r}")
        if self.source not in ROUTE_SOURCES:
            raise ValueError(f"invalid source: {self.source!r}")
        support_roles = _coerce_role_sequence(self.support_roles, "support_roles")
        object.__setattr__(self, "support_roles", support_roles)


@dataclass(frozen=True)
class PromotionDecision:
    verdict: PromotionVerdict | str
    reasons: Sequence[str]
    baseline_joint: float
    candidate_joint: float
    previous_winner_joint: float | None

    def __post_init__(self) -> None:
        if self.verdict not in PROMOTION_VERDICTS:
            raise ValueError(f"invalid verdict: {self.verdict!r}")
        reasons = _coerce_string_sequence(self.reasons, "reasons")
        object.__setattr__(self, "reasons", reasons)


def _coerce_role_sequence(value: Sequence[str], field_name: str) -> tuple[str, ...]:
    items = _coerce_string_sequence(value, field_name)
    for item in items:
        if item not in ROLE_NAMES:
            raise ValueError(f"invalid {field_name} entry: {item!r}")
    return items


def _coerce_string_sequence(value: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, ABCSequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    items = tuple(value)
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} entries must be strings")
    return items
