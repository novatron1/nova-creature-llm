"""Deterministic per-turn analysis for Nova's cognitive orchestration.

The analyzer is intentionally small and provider-independent.  It decides how
much orchestration a request needs; it does not answer the request and it never
stores prompt content by itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from nova_conversation_intelligence import ConversationDecision


TURN_ANALYZER_VERSION = "1.0"
REASONING_MODES = frozenset({"fast", "deep", "agent", "verify"})


@dataclass(frozen=True)
class TurnState:
    user_text: str
    intent: str
    dialogue_act: str
    topic: str
    complexity: str
    certainty_required: bool
    current_information_required: bool
    memory_required: bool
    project_context_required: bool
    rag_required: bool
    tools_required: bool
    reasoning_mode: str
    risk_level: str
    requested_depth: str
    open_loops: tuple[str, ...] = field(default_factory=tuple)
    context_budget: int = 8192
    max_tool_steps: int = 4
    analyzer_version: str = TURN_ANALYZER_VERSION

    def __post_init__(self) -> None:
        if self.reasoning_mode not in REASONING_MODES:
            raise ValueError(f"Unsupported reasoning mode: {self.reasoning_mode!r}")
        if self.context_budget < 1024:
            raise ValueError("context_budget must be at least 1024 tokens")
        if not 0 <= self.max_tool_steps <= 12:
            raise ValueError("max_tool_steps must be between 0 and 12")

    def to_dict(self, *, include_user_text: bool = True) -> dict[str, Any]:
        value = asdict(self)
        value["open_loops"] = list(self.open_loops)
        if not include_user_text:
            value.pop("user_text", None)
            value["user_text_length"] = len(self.user_text)
        return value

    def safe_trace(self) -> dict[str, Any]:
        """Return operational routing metadata without prompt content."""

        return self.to_dict(include_user_text=False)


_CURRENT_MARKERS = (
    "current", "currently", "today", "tonight", "latest", "live", "right now",
    "this week", "this month", "newest", "recent", "price", "weather", "score",
    "news", "president", "ceo", "law", "regulation", "version",
)
_MEMORY_MARKERS = (
    "remember", "forget", "what is my", "what's my", "what did i tell",
    "my name", "my girlfriend", "my preference", "saved memory",
)
_PROJECT_MARKERS = (
    "repository", "repo", "codebase", "project", "file", "folder", "module",
    "function", "class", "endpoint", "test suite", "configuration",
)
_AGENT_MARKERS = (
    "open the", "search the web", "look online", "browse", "read the file",
    "search the code", "search the project", "search project", "read project",
    "run the", "run tests", "run project", "execute", "install", "send", "publish",
    "delete", "rename", "move the file", "database", "calendar", "email",
    "deploy", "upload", "download", "create the file", "edit the file",
)
_DEEP_MARKERS = (
    "analyze", "architecture", "compare", "debug", "design", "explain why",
    "prove", "reason", "tradeoff", "multi-step", "step by step", "root cause",
    "future-proof", "algorithm", "calculate", "math", "plan", "calculus",
    "differentiate", "derivative", "integral", "probability", "latency",
    "troubleshoot", "diagnose", "evidence-based", "incident", "think deep",
    "go deep", "in depth", "origin of life", "abiogenesis", "philosophy",
)
_VERIFY_MARKERS = (
    "verify", "double-check", "fact-check", "accurate", "exact", "prove",
    "cite", "source", "evidence", "audit", "validate",
)
_HIGH_STAKES = (
    "medical", "medicine", "diagnosis", "symptom", "legal", "lawyer", "lawsuit",
    "financial", "investment", "tax", "insurance", "credit", "mortgage",
    "emergency", "robot movement", "motor command", "dosage",
)
_DESTRUCTIVE = (
    "delete", "remove", "wipe", "format", "purchase", "buy", "send email",
    "publish", "deploy", "transfer money", "move robot", "run shell",
)


def _contains(value: str, markers: Iterable[str]) -> bool:
    return any(marker in value for marker in markers)


def _contains_action_marker(value: str, markers: Iterable[str]) -> bool:
    """Match action markers as phrases, not substrings inside unrelated words."""

    return any(
        re.search(
            r"(?<![a-z0-9])" + re.escape(str(marker).strip()) + r"(?![a-z0-9])",
            value,
        )
        for marker in markers
        if str(marker).strip()
    )


def _topic(value: str) -> str:
    groups = (
        ("memory", _MEMORY_MARKERS),
        ("project_code", _PROJECT_MARKERS),
        ("current_information", _CURRENT_MARKERS),
        ("health", ("health", "medical", "symptom", "medicine")),
        ("law", ("legal", "law", "court", "contract")),
        ("finance", ("financial", "investment", "stock", "tax", "budget")),
        ("robotics", ("robot", "lidar", "sensor", "motor", "navigation")),
        ("conversation", ("feel", "love", "think", "talk", "relationship")),
    )
    for name, markers in groups:
        if _contains(value, markers):
            return name
    words = re.findall(r"[a-z0-9]+", value)
    return "_".join(words[:4]) if words else "general"


def _intent(value: str) -> str:
    if value in {"hi", "hello", "hey", "yo", "what up", "whats up", "what's up"}:
        return "greeting"
    if _contains(value, ("remember ", "save this", "save that", "correct my memory")):
        return "memory_write"
    if _contains(value, ("forget ", "delete that memory", "remove that memory")):
        return "memory_delete"
    if _contains_action_marker(value, _AGENT_MARKERS):
        return "tool_task"
    if _contains(value, ("rewrite", "rephrase", "make this sound", "summarize")):
        return "transformation"
    if "?" in value or re.match(r"^(what|why|how|who|when|where|can|should|is|are|do)\b", value):
        return "question"
    return "conversation"


def _dialogue_act(intent: str, value: str) -> str:
    return {
        "greeting": "acknowledge",
        "memory_write": "act_then_confirm",
        "memory_delete": "act_then_confirm",
        "tool_task": "plan_and_act",
        "transformation": "transform",
        "question": "answer",
    }.get(intent, "respond")


def _requested_depth(value: str) -> str:
    if _contains(value, ("ultra", "thorough", "in depth", "deep", "everything", "complete")):
        return "thorough"
    if _contains(value, ("brief", "quick", "short", "one sentence", "simple")):
        return "brief"
    if len(value.split()) > 80 or _contains(value, _DEEP_MARKERS):
        return "detailed"
    return "normal"


def analyze_turn(
    user_text: str,
    *,
    open_loops: Iterable[str] | None = None,
    context_budget: int = 8192,
    max_tool_steps: int = 4,
    conversation_decision: "ConversationDecision | None" = None,
) -> TurnState:
    """Classify one request without invoking a language model."""

    raw = str(user_text or "").strip()
    value = re.sub(r"\s+", " ", raw.lower())
    decision = conversation_decision
    decision_family = str(getattr(decision, "intent_family", "") or "")
    if decision_family in {"relationship", "emotional", "social"}:
        intent = "social_checkin"
    elif decision_family == "follow_up":
        intent = "contextual_followup"
    elif decision_family == "memory":
        decision_subtype = str(getattr(decision, "intent_subtype", "") or "")
        intent = {
            "remember": "memory_write",
            "update": "memory_write",
            "forget": "memory_delete",
            "recall": "memory_recall",
        }.get(decision_subtype, "memory_recall")
    elif decision_family in {"project_tool", "vision_robot", "permission_action"}:
        intent = "tool_task"
    else:
        intent = _intent(value)
    current = bool(
        getattr(decision, "current_information_required", False)
        if decision is not None
        else _contains(value, _CURRENT_MARKERS)
    )
    memory = bool(
        decision_family == "memory"
        or getattr(decision, "memory_recommended", False)
        or _contains(value, _MEMORY_MARKERS)
        or intent.startswith("memory_")
    )
    project = bool(decision_family == "project_tool" or _contains(value, _PROJECT_MARKERS))
    tools = bool(
        decision_family in {"project_tool", "vision_robot", "permission_action"}
        or intent == "tool_task"
    )
    high_stakes = bool(
        decision_family == "permission_action" or _contains(value, _HIGH_STAKES)
    )
    explicit_verify = bool(
        getattr(decision, "reasoning_mode", "") == "verify"
        or _contains(value, _VERIFY_MARKERS)
    )
    deep = bool(
        getattr(decision, "reasoning_mode", "") == "deep"
        or _contains(value, _DEEP_MARKERS)
        or len(value.split()) > 45
    )
    destructive = bool(
        decision_family == "permission_action"
        or _contains_action_marker(value, _DESTRUCTIVE)
    )
    rag = bool(
        _contains(value, ("article", "document", "knowledge base", "sources", "citation", "field guide"))
        or (current and not tools)
    )

    decision_mode = str(getattr(decision, "reasoning_mode", "") or "")
    if decision_mode in {"agent", "verify"}:
        mode = decision_mode
    elif tools:
        mode = "agent"
    elif high_stakes or explicit_verify or current:
        mode = "verify"
    elif decision_mode == "deep" or (
        deep
        and decision_family
        not in {"relationship", "emotional", "social"}
    ):
        mode = "deep"
    else:
        mode = decision_mode if decision_mode in REASONING_MODES else "fast"

    if destructive or high_stakes:
        risk = "high"
    elif tools or current or explicit_verify:
        risk = "medium"
    else:
        risk = "low"

    word_count = len(value.split())
    if word_count > 120 or (deep and tools):
        complexity = "high"
    elif word_count > 30 or deep or tools:
        complexity = "medium"
    else:
        complexity = "low"

    bounded_steps = 0 if mode in {"fast", "deep", "verify"} and not tools else max_tool_steps
    return TurnState(
        user_text=raw,
        intent=intent,
        dialogue_act=(
            str(getattr(decision, "dialogue_act", "") or _dialogue_act(intent, value))
        ),
        topic=decision_family or _topic(value),
        complexity=complexity,
        certainty_required=bool(high_stakes or explicit_verify or current),
        current_information_required=current,
        memory_required=memory,
        project_context_required=project,
        rag_required=rag,
        tools_required=tools,
        reasoning_mode=mode,
        risk_level=risk,
        requested_depth=_requested_depth(value),
        open_loops=tuple(str(item)[:240] for item in (open_loops or ()) if str(item).strip())[:8],
        context_budget=max(1024, min(int(context_budget), 131072)),
        max_tool_steps=max(0, min(int(bounded_steps), 12)),
    )
