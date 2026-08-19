"""Persistent, bounded social behavior for managed Nova conversations."""

from .models import (
    CompanionContext,
    CompanionState,
    MoodState,
    RelationshipMemory,
    SocialIntent,
    SocialPlan,
)
from .store import CompanionStore

COMPANION_LAYER_VERSION = "1.0"

__all__ = [
    "COMPANION_LAYER_VERSION",
    "CompanionContext",
    "CompanionState",
    "CompanionStore",
    "MoodState",
    "RelationshipMemory",
    "SocialIntent",
    "SocialPlan",
]
