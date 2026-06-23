from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class SafetyLevel(StrEnum):
    READ_ONLY = "read_only"
    SAFE_WRITE = "safe_write"
    CONFIRM_REQUIRED = "confirm_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class NavigationIntent:
    raw_text: str
    target_surface: str
    action: str
    confidence: float
    safety_level: SafetyLevel
    subject: str | None = None

    def to_trace(self) -> dict[str, Any]:
        data = asdict(self)
        data["safety_level"] = self.safety_level.value
        return data


@dataclass(frozen=True)
class NavigationStep:
    kind: str
    target: str
    detail: str
    status: str = "planned"

    def to_trace(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class AppNavigationContext:
    last_surface: str | None = None
    active_project: str | None = None
    active_agent: str | None = None
    active_draft: str | None = None
    pending_action: str | None = None
    verification_target: str | None = None
    last_blocker: str | None = None


@dataclass
class NavigationResult:
    recognized: bool
    intent: NavigationIntent | None
    steps: list[NavigationStep] = field(default_factory=list)
    response: str = ""
    verification: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    blocker: str | None = None
    next_safe_step: str | None = None

    def trace(self) -> dict[str, Any]:
        if not self.recognized:
            return {"source": "app_navigation_miss", "recognized": False}
        assert self.intent is not None
        return {
            "source": "app_navigation",
            "recognized": True,
            "navigation_intent": self.intent.to_trace(),
            "target_surface": self.intent.target_surface,
            "action": self.intent.action,
            "safety_level": self.intent.safety_level.value,
            "steps": [step.to_trace() for step in self.steps],
            "verification": dict(self.verification),
            "blocked": self.blocked,
            "blocker": self.blocker,
            "next_safe_step": self.next_safe_step,
        }


SURFACE_ALIASES = {
    "home": ("home", "home screen", "main screen"),
    "chat": ("chat", "chat screen"),
    "agent_library": ("agent library", "agents", "agent page"),
    "app_builder": ("builder", "app builder", "build page"),
    "memory_panel": ("memory", "memory panel"),
    "settings": ("settings", "preferences"),
    "tools_page": ("tools", "tools page"),
    "research_panel": ("research", "research panel"),
    "test_check_page": ("test", "tests", "check page", "test page", "run the test"),
    "saved_projects": ("saved projects", "projects"),
    "preview_area": ("preview", "preview area"),
    "debug_logs": ("logs", "debug logs", "debug area"),
    "scheduler": ("scheduler", "schedule"),
    "file_manager": ("file manager", "files"),
}

OPERATOR_VERBS = (
    "go",
    "open",
    "show",
    "look",
    "view",
    "navigate",
    "check",
    "run",
    "delete",
    "remove",
    "clear",
    "save",
    "make",
    "create",
)

DESTRUCTIVE_VERBS = ("delete", "remove", "clear")

QUESTION_STARTERS = ("what ", "how ", "why ", "when ", "where ", "who ")
EXPLAIN_REQUEST_STARTERS = ("can you explain", "could you explain", "would you explain")
COMMAND_CONNECTORS = ("to", "the", "at", "my", "a", "an", "up", "into", "on")


def plan_app_navigation(text: str, context: AppNavigationContext | None = None) -> NavigationResult:
    context = context or AppNavigationContext()
    raw = "" if text is None else str(text)
    normalized = _normalize(raw)
    target_surface = _detect_surface(normalized)
    if target_surface is None:
        return NavigationResult(False, None)

    action = _detect_action(normalized)
    safety = _safety_for(action, normalized)
    intent = NavigationIntent(raw, target_surface, action, 0.86, safety)
    steps = [
        NavigationStep("understand", target_surface, f"Understood command: {raw.strip()}"),
        NavigationStep("navigate", target_surface, f"Open {target_surface.replace('_', ' ')}."),
        NavigationStep("verify", target_surface, f"Confirm {target_surface.replace('_', ' ')} is available."),
    ]
    response = _format_response(intent, steps, blocked=False, blocker=None, next_safe_step=None)
    context.last_surface = target_surface
    context.pending_action = action
    context.verification_target = target_surface
    context.last_blocker = None
    return NavigationResult(
        True,
        intent,
        steps,
        response,
        verification={"method": "structured_navigation_plan", "status": "planned"},
    )


def _detect_surface(normalized: str) -> str | None:
    for surface, aliases in SURFACE_ALIASES.items():
        if normalized in aliases:
            return surface
    if _is_question_like_non_command(normalized):
        return None
    for surface, aliases in SURFACE_ALIASES.items():
        if any(_matches_command_surface(normalized, alias) for alias in aliases):
            return surface
    return None


def _detect_action(normalized: str) -> str:
    if _has_destructive_verb(normalized):
        return "delete"
    if re.search(r"\b(run|test|check|verify|prove)\b", normalized):
        return "verify"
    if re.search(r"\b(make|create|new)\b", normalized):
        return "create"
    if re.search(r"\b(save)\b", normalized):
        return "save"
    if re.search(r"\b(delete|remove|clear)\b", normalized):
        return "delete"
    if re.search(r"\b(open|go|show|look|view|navigate)\b", normalized):
        return "navigate"
    return "navigate"


def _safety_for(action: str, normalized: str) -> SafetyLevel:
    if (
        action == "delete"
        or _has_destructive_verb(normalized)
        or "overwrite stable" in normalized
        or "clear memory" in normalized
    ):
        return SafetyLevel.CONFIRM_REQUIRED
    if action in {"create", "save"}:
        return SafetyLevel.SAFE_WRITE
    return SafetyLevel.READ_ONLY


def _has_destructive_verb(normalized: str) -> bool:
    return any(_matches_phrase(normalized, verb) for verb in DESTRUCTIVE_VERBS)


def _matches_phrase(normalized: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9_]){re.escape(phrase)}(?![a-z0-9_])", normalized) is not None


def _is_question_like_non_command(normalized: str) -> bool:
    return normalized.startswith(QUESTION_STARTERS) or normalized.startswith(EXPLAIN_REQUEST_STARTERS)


def _matches_command_surface(normalized: str, alias: str) -> bool:
    connector_pattern = "|".join(re.escape(connector) for connector in COMMAND_CONNECTORS)
    alias_pattern = re.escape(alias)
    for verb in OPERATOR_VERBS:
        pattern = (
            rf"(?<![a-z0-9_]){re.escape(verb)}"
            rf"(?:\s+(?:{connector_pattern})){{0,3}}"
            rf"\s+{alias_pattern}(?![a-z0-9_])"
        )
        if re.search(pattern, normalized):
            return True
    return False


def _format_response(
    intent: NavigationIntent,
    steps: list[NavigationStep],
    *,
    blocked: bool,
    blocker: str | None,
    next_safe_step: str | None,
) -> str:
    lines = [
        f"I understood: {intent.raw_text.strip()}",
        f"Planned navigation to: {intent.target_surface.replace('_', ' ').title()}.",
        "Did: planned the safe app operation.",
        f"Checked: {steps[-1].detail}",
    ]
    if blocked:
        lines.append(f"Blocker: {blocker}")
        lines.append(f"Next safe step: {next_safe_step}")
    else:
        lines.append("Result: ready to execute or verify.")
    return "\n".join(lines)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()
