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
RESUME_COMMANDS = ("resume", "continue", "continue from where you left off")
AGENT_CREATION_PHRASES = ("make an agent", "create an agent", "new agent")
DESTRUCTIVE_CONTEXT_TERMS = ("draft", "project", "log", "memory", "settings")

QUESTION_STARTERS = ("what ", "how ", "why ", "when ", "where ", "who ")
EXPLAIN_REQUEST_STARTERS = ("can you explain", "could you explain", "would you explain")
COMMAND_CONNECTORS = ("to", "the", "at", "my", "a", "an", "up", "into", "on")


def plan_app_navigation(text: str, context: AppNavigationContext | None = None) -> NavigationResult:
    context = context or AppNavigationContext()
    raw = "" if text is None else str(text)
    normalized = _normalize(raw)
    action = _detect_action(normalized)
    target_surface = _detect_surface(normalized)

    if target_surface is None and action == "create_agent":
        target_surface = "agent_library"
    if target_surface is None and action == "verify" and context.verification_target:
        target_surface = context.verification_target
    if target_surface is None and action == "resume" and context.last_surface:
        target_surface = context.last_surface
        action = context.pending_action or "resume"
    if (
        target_surface is None
        and action == "delete"
        and _is_contextual_delete_request(normalized)
    ):
        target_surface = context.last_surface or ("saved_projects" if "draft" in normalized else None)

    if target_surface is None:
        return NavigationResult(False, None)

    safety = _safety_for(action, normalized)
    subject = _subject_for(normalized, action)
    intent = NavigationIntent(raw, target_surface, action, 0.90, safety, subject=subject)
    blocked, blocker, next_safe_step = _blocker_for(intent, context)
    steps = _steps_for(intent, blocked=blocked, blocker=blocker)
    response = _format_response(intent, steps, blocked=blocked, blocker=blocker, next_safe_step=next_safe_step)
    context.last_surface = target_surface
    context.pending_action = action
    context.verification_target = target_surface
    context.last_blocker = blocker if blocked else None
    if action == "create_agent" and subject:
        context.active_agent = subject
    return NavigationResult(
        True,
        intent,
        steps,
        response,
        verification={"method": "structured_navigation_plan", "status": "blocked" if blocked else "planned"},
        blocked=blocked,
        blocker=blocker,
        next_safe_step=next_safe_step,
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
    if normalized in RESUME_COMMANDS:
        return "resume"
    if _has_destructive_verb(normalized):
        return "delete"
    if _is_agent_creation_command(normalized):
        return "create_agent"
    if "check if it works" in normalized:
        return "verify"
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
    if action in {"create", "create_agent", "save"}:
        return SafetyLevel.SAFE_WRITE
    return SafetyLevel.READ_ONLY


def _subject_for(normalized: str, action: str) -> str | None:
    if action == "create_agent":
        return "Weekly LLM Upgrade Scout" if "weekly" in normalized and "llm" in normalized else "Custom Agent"
    if "draft" in normalized:
        return "draft"
    return None


def _blocker_for(intent: NavigationIntent, context: AppNavigationContext) -> tuple[bool, str | None, str | None]:
    normalized = _normalize(intent.raw_text)
    if normalized in RESUME_COMMANDS and context.last_blocker:
        return True, context.last_blocker, _next_safe_step_for_blocker(context.last_blocker, intent)
    if intent.safety_level == SafetyLevel.CONFIRM_REQUIRED:
        return (
            True,
            "destructive action requires explicit target confirmation",
            "Confirm the exact draft or saved item to delete.",
        )
    if intent.action in {"open", "navigate", "resume"} and intent.target_surface == "preview_area" and not context.active_project:
        return True, "no active project is selected", "Choose a project or ask me to create one."
    return False, None, None


def _steps_for(intent: NavigationIntent, *, blocked: bool, blocker: str | None) -> list[NavigationStep]:
    steps = [
        NavigationStep("understand", intent.target_surface, f"Understood command: {intent.raw_text.strip()}"),
    ]
    if intent.action == "create_agent":
        return [
            *steps,
            NavigationStep("navigate", "agent_library", "Open Agent Library."),
            NavigationStep("create", "agent_library", f"Create {intent.subject or 'Custom Agent'}."),
            NavigationStep("fill", "agent_library", "Fill purpose and research topics from the command."),
            NavigationStep("schedule", "scheduler", "Add weekly schedule."),
            NavigationStep("save", "agent_library", "Save the agent draft."),
            NavigationStep("verify", "agent_library", "Reload and verify the saved agent and weekly schedule."),
        ]

    steps.append(
        NavigationStep(
            "navigate",
            intent.target_surface,
            f"Open {intent.target_surface.replace('_', ' ')}.",
        )
    )
    if intent.action == "verify":
        steps.append(NavigationStep("verify", intent.target_surface, "Run the relevant check and inspect the result."))
    elif intent.action == "delete":
        steps.append(NavigationStep("confirm", intent.target_surface, blocker or "Confirm destructive action before continuing."))
    else:
        steps.append(
            NavigationStep(
                "verify",
                intent.target_surface,
                f"Confirm {intent.target_surface.replace('_', ' ')} is available.",
            )
        )
    return steps


def _next_safe_step_for_blocker(blocker: str, intent: NavigationIntent) -> str:
    if intent.target_surface == "preview_area" or "no active project" in blocker.casefold():
        return "Choose a project or clear the blocker, then ask me to resume."
    return "Clear the blocker, then ask me to resume."


def _is_agent_creation_command(normalized: str) -> bool:
    return any(phrase in normalized for phrase in AGENT_CREATION_PHRASES)


def _is_contextual_delete_request(normalized: str) -> bool:
    if _is_question_like_non_command(normalized):
        return False
    return any(_matches_phrase(normalized, term) for term in DESTRUCTIVE_CONTEXT_TERMS)


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
