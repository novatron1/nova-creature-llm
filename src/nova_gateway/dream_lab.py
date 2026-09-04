"""Bounded counterfactual route simulation for Nova Core.

Dream Lab is not hidden chain-of-thought and does not execute actions. It
compares a small fixed set of safe response strategies, records only
operational labels, and supplies the selected strategy to Nova's existing
cognitive pipeline as provider-independent context.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
import time
import uuid
from typing import Any

from nova_protocol import NovaRequest


DREAM_LAB_SCHEMA_VERSION = "1.0"
DREAM_LAB_INTERFACE_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raw_adapter_requested(request: NovaRequest) -> bool:
    desktop = request.metadata.get("desktop_context")
    if not isinstance(desktop, dict):
        return False
    return any(
        bool(desktop.get(key))
        for key in (
            "adapter_only_mode",
            "trained_adapter_only",
            "trained_adapter_only_mode",
            "dolphin_adapter_only",
        )
    )


def _task_type(request: NovaRequest) -> str:
    text = request.last_user_text().lower()
    if any(modality in {"image", "video", "audio"} for modality in request.requested_modalities):
        return "multimodal"
    if any(marker in text for marker in ("delete ", "purchase", "buy ", "move robot", "run command", "write file")):
        return "guarded_action"
    if request.tools:
        return "tool_assisted"
    if any(marker in text for marker in ("remember", "recall", "what is my", "who is my", "do you know my")):
        return "memory_grounded"
    if len(text) > 220 or any(
        marker in text
        for marker in (
            "compare",
            "tradeoff",
            "best approach",
            "analyze",
            "debug",
            "design",
            "architecture",
            "future proof",
            "ultra think",
        )
    ):
        return "complex_reasoning"
    return "direct_conversation"


@dataclass(frozen=True)
class DreamAlternative:
    """One privacy-safe simulated route outcome."""

    strategy: str
    predicted_outcome: str
    score: float
    accepted: bool
    remains_local: bool
    risk_level: str
    rejection_reason: str | None = None


@dataclass(frozen=True)
class DreamDecision:
    """The bounded, inspectable result of Dream Lab route simulation."""

    simulation_id: str
    request_id: str
    conversation_id: str
    task_type: str
    selected_strategy: str
    selection_reason: str
    alternatives: list[DreamAlternative] = field(default_factory=list)
    remains_local: bool = True
    advisory_only: bool = True
    executed_actions: bool = False
    private_reasoning_stored: bool = False
    prompt_content_stored: bool = False
    created_at: str = field(default_factory=_now)
    latency_ms: float = 0.0
    schema_version: str = DREAM_LAB_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["alternatives"] = [asdict(item) for item in self.alternatives]
        return data


class NovaDreamLab:
    """Thread-safe bounded store of safe route simulations."""

    def __init__(self, maximum_conversations: int = 128, *, enabled: bool = True):
        self.maximum_conversations = max(8, min(int(maximum_conversations), 1024))
        self.enabled = bool(enabled)
        self._decisions: OrderedDict[tuple[str, str], DreamDecision] = OrderedDict()
        self._lock = RLock()
        self._simulations = 0

    @staticmethod
    def _key(client_id: str, conversation_id: str) -> tuple[str, str]:
        return (str(client_id or "anonymous")[:160], str(conversation_id or "default")[:160])

    def simulate(self, request: NovaRequest, routing: dict[str, Any]) -> dict[str, Any]:
        """Simulate bounded strategies without calling a provider or executing a tool."""
        started = time.monotonic()
        task_type = _task_type(request)
        remains_local = bool(routing.get("remains_local", False))
        memory_allowed = bool(request.metadata.get("memory_read_allowed", False))

        if not self.enabled:
            selected = "disabled"
            reason = "Dream Lab is disabled by configuration."
            alternatives: list[DreamAlternative] = []
        elif _raw_adapter_requested(request):
            selected = "raw_adapter_passthrough"
            reason = "Raw adapter output remains unintercepted; Dream Lab cannot rewrite or replace it."
            alternatives = [
                DreamAlternative(
                    strategy=selected,
                    predicted_outcome="Return the selected raw adapter output unchanged.",
                    score=1.0,
                    accepted=True,
                    remains_local=True,
                    risk_level="bounded",
                )
            ]
        else:
            alternatives = [
                DreamAlternative(
                    strategy="direct_nova_core",
                    predicted_outcome="Use Nova identity, context, memory policy, and the selected local provider.",
                    score=0.78,
                    accepted=True,
                    remains_local=remains_local,
                    risk_level="low",
                ),
                DreamAlternative(
                    strategy="memory_grounded_context",
                    predicted_outcome="Retrieve only permission-allowed Nova memory before generation.",
                    score=0.88 if task_type == "memory_grounded" and memory_allowed else 0.58,
                    accepted=memory_allowed,
                    remains_local=True,
                    risk_level="low",
                    rejection_reason=None if memory_allowed else "memory.read is not available to this client",
                ),
                DreamAlternative(
                    strategy="registered_tool_preflight",
                    predicted_outcome="Validate declared tools and permissions before any tool execution.",
                    score=0.91 if task_type in {"tool_assisted", "guarded_action"} else 0.56,
                    accepted=bool(request.tools),
                    remains_local=True,
                    risk_level="guarded",
                    rejection_reason=None if request.tools else "no client tools were declared",
                ),
                DreamAlternative(
                    strategy="local_counterfactual_review",
                    predicted_outcome="Ask a separate free local model only if the primary answer is uncertain or blocked.",
                    score=0.86 if task_type == "complex_reasoning" else 0.62,
                    accepted=True,
                    remains_local=True,
                    risk_level="low",
                ),
                DreamAlternative(
                    strategy="clarification_before_action",
                    predicted_outcome="Request missing details before a consequential or ambiguous action.",
                    score=0.95 if task_type == "guarded_action" else 0.52,
                    accepted=True,
                    remains_local=True,
                    risk_level="safest",
                ),
                DreamAlternative(
                    strategy="remote_specialist",
                    predicted_outcome="Send the task to a remote specialist.",
                    score=0.0,
                    accepted=False,
                    remains_local=False,
                    risk_level="remote",
                    rejection_reason="Dream Lab never expands Nova's remote-data authority",
                ),
            ]
            accepted = [item for item in alternatives if item.accepted]
            winner = max(accepted, key=lambda item: item.score)
            selected = winner.strategy
            reason = {
                "direct_nova_core": "The task is best handled directly through Nova Core.",
                "memory_grounded_context": "The task depends on permission-scoped Nova memory.",
                "registered_tool_preflight": "Declared tools require schema and permission checks first.",
                "local_counterfactual_review": "The task benefits from a bounded independent local review.",
                "clarification_before_action": "The safest route is to resolve ambiguity before action.",
            }.get(selected, "Nova selected the highest-scoring policy-compliant strategy.")

        decision = DreamDecision(
            simulation_id="dream_" + uuid.uuid4().hex,
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            task_type=task_type,
            selected_strategy=selected,
            selection_reason=reason,
            alternatives=alternatives,
            remains_local=all(item.remains_local for item in alternatives if item.accepted),
            latency_ms=round((time.monotonic() - started) * 1000, 3),
        )
        with self._lock:
            key = self._key(request.client_id, request.conversation_id)
            self._decisions[key] = decision
            self._decisions.move_to_end(key)
            while len(self._decisions) > self.maximum_conversations:
                self._decisions.popitem(last=False)
            self._simulations += 1
        return decision.to_dict()

    def view(self, client_id: str, conversation_id: str | None = None) -> dict[str, Any]:
        client = str(client_id or "anonymous")[:160]
        with self._lock:
            if conversation_id:
                decision = self._decisions.get(self._key(client, conversation_id))
                data: Any = decision.to_dict() if decision else None
                object_type = "nova.dream_decision"
            else:
                data = [
                    decision.to_dict()
                    for (owner, _), decision in reversed(self._decisions.items())
                    if owner == client
                ]
                object_type = "list"
        return {
            "object": object_type,
            "schema_version": DREAM_LAB_SCHEMA_VERSION,
            "privacy": {
                "prompt_content_stored": False,
                "response_content_stored": False,
                "private_reasoning_stored": False,
                "executed_actions": False,
            },
            "data": data,
        }

    def health_check(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "enabled": self.enabled,
                "schema_version": DREAM_LAB_SCHEMA_VERSION,
                "interface_version": DREAM_LAB_INTERFACE_VERSION,
                "simulations": self._simulations,
                "active_conversations": len(self._decisions),
                "bounded_alternatives": 6,
                "provider_calls": 0,
                "executed_actions": False,
                "prompt_content_stored": False,
                "response_content_stored": False,
                "private_reasoning_stored": False,
            }
