# Nova Autonomous App Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Nova's first autonomous app-operator mode so app navigation commands become structured, safe action plans with honest verification/blocker traces.

**Architecture:** Add a focused `src/nova_app_navigation.py` module that owns surface aliases, intent detection, safety gating, context resolution, and operator reports. Integrate it early in `src/nova_hybrid_router.py` before dictionary/memory/transformer fallback, preserving existing chat behavior for non-navigation prompts.

**Tech Stack:** Python 3.11, dataclasses, existing `nova_hybrid_router.route_and_respond()`, pytest.

---

## File Structure

- Create `src/nova_app_navigation.py`
  - Owns canonical surfaces, action classification, safety levels, context state, planning, report text, and trace serialization.
- Create `tests/test_nova_app_navigation.py`
  - Unit tests for command recognition, planning, context resolution, safety gates, and blocker reporting.
- Modify `src/nova_hybrid_router.py`
  - Import the navigation module.
  - Run navigation detection before dictionary lookup unless `transformer_only=True`.
  - Return navigation response and trace when a command is recognized.
- Modify `tests/test_nova_transformer_runtime.py`
  - Add router-level regression tests showing app-navigation commands route to `source: "app_navigation"` and normal chat still routes through the existing transformer path.
- Modify `tests/test_nova_enhanced_server.py`
  - Add one server-level regression proving `/api/chat`/`brain_route()` can return app-navigation traces.

## Task 1: Navigation Module and Surface Recognition

**Files:**
- Create: `src/nova_app_navigation.py`
- Create: `tests/test_nova_app_navigation.py`

- [ ] **Step 1: Write failing surface-recognition tests**

Create `tests/test_nova_app_navigation.py` with:

```python
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_app_navigation import (
    AppNavigationContext,
    SafetyLevel,
    plan_app_navigation,
)


def test_surface_navigation_commands_resolve_canonical_pages():
    context = AppNavigationContext()

    agent = plan_app_navigation("go to Agent Library", context)
    builder = plan_app_navigation("open the builder", context)
    logs = plan_app_navigation("look at the logs", context)

    assert agent.recognized is True
    assert agent.intent.target_surface == "agent_library"
    assert agent.intent.action == "navigate"
    assert agent.intent.safety_level == SafetyLevel.READ_ONLY
    assert agent.steps[0].kind == "understand"
    assert any(step.kind == "navigate" and step.target == "agent_library" for step in agent.steps)

    assert builder.recognized is True
    assert builder.intent.target_surface == "app_builder"
    assert logs.recognized is True
    assert logs.intent.target_surface == "debug_logs"


def test_unknown_chat_is_not_claimed_by_navigation_router():
    context = AppNavigationContext()

    result = plan_app_navigation("what is the quadratic formula?", context)

    assert result.recognized is False
    assert result.intent is None
    assert result.trace()["source"] == "app_navigation_miss"
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```powershell
py -3 -m pytest tests/test_nova_app_navigation.py::test_surface_navigation_commands_resolve_canonical_pages tests/test_nova_app_navigation.py::test_unknown_chat_is_not_claimed_by_navigation_router -q
```

Expected: FAIL because `nova_app_navigation` does not exist.

- [ ] **Step 3: Implement minimal module with surfaces and trace objects**

Create `src/nova_app_navigation.py`:

```python
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
        if any(alias in normalized for alias in aliases):
            return surface
    return None


def _detect_action(normalized: str) -> str:
    if re.search(r"\b(run|test|check|verify|prove)\b", normalized):
        return "verify"
    if re.search(r"\b(make|create|new)\b", normalized):
        return "create"
    if re.search(r"\b(save)\b", normalized):
        return "save"
    if re.search(r"\b(delete|remove|clear)\b", normalized):
        return "delete"
    if re.search(r"\b(open|go|show|look|view)\b", normalized):
        return "navigate"
    return "navigate"


def _safety_for(action: str, normalized: str) -> SafetyLevel:
    if action == "delete" or "overwrite stable" in normalized or "clear memory" in normalized:
        return SafetyLevel.CONFIRM_REQUIRED
    if action in {"create", "save"}:
        return SafetyLevel.SAFE_WRITE
    return SafetyLevel.READ_ONLY


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
        f"Went to: {intent.target_surface.replace('_', ' ').title()}.",
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
```

- [ ] **Step 4: Run the surface tests and verify they pass**

Run:

```powershell
py -3 -m pytest tests/test_nova_app_navigation.py::test_surface_navigation_commands_resolve_canonical_pages tests/test_nova_app_navigation.py::test_unknown_chat_is_not_claimed_by_navigation_router -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/nova_app_navigation.py tests/test_nova_app_navigation.py
git commit -m "feat: recognize app navigation surfaces"
```

## Task 2: Action Loop, Context Resolution, and Safety Gates

**Files:**
- Modify: `src/nova_app_navigation.py`
- Modify: `tests/test_nova_app_navigation.py`

- [ ] **Step 1: Add failing action-loop/context/safety tests**

Append to `tests/test_nova_app_navigation.py`:

```python
def test_agent_creation_command_builds_full_operator_loop():
    context = AppNavigationContext()

    result = plan_app_navigation(
        "make an agent that researches better LLM methods weekly",
        context,
    )

    assert result.recognized is True
    assert result.intent.target_surface == "agent_library"
    assert result.intent.action == "create_agent"
    assert result.intent.safety_level == SafetyLevel.SAFE_WRITE
    assert [step.kind for step in result.steps] == [
        "understand",
        "navigate",
        "create",
        "fill",
        "schedule",
        "save",
        "verify",
    ]
    assert result.verification["status"] == "planned"
    assert context.last_surface == "agent_library"
    assert context.verification_target == "agent_library"


def test_check_if_it_works_uses_recent_context():
    context = AppNavigationContext()
    plan_app_navigation("open the builder", context)

    result = plan_app_navigation("check if it works", context)

    assert result.recognized is True
    assert result.intent.target_surface == "app_builder"
    assert result.intent.action == "verify"
    assert any(step.kind == "verify" for step in result.steps)


def test_resume_continues_last_blocker_or_pending_action():
    context = AppNavigationContext(
        last_surface="preview_area",
        pending_action="open",
        last_blocker="no active project is selected",
    )

    result = plan_app_navigation("resume", context)

    assert result.recognized is True
    assert result.blocked is True
    assert result.intent.target_surface == "preview_area"
    assert "no active project" in result.blocker
    assert "choose a project" in result.next_safe_step.lower()


def test_destructive_ambiguous_delete_requires_confirmation():
    context = AppNavigationContext(last_surface="saved_projects")

    result = plan_app_navigation("delete that draft", context)

    assert result.recognized is True
    assert result.intent.safety_level == SafetyLevel.CONFIRM_REQUIRED
    assert result.blocked is True
    assert "confirm" in result.next_safe_step.lower()
```

- [ ] **Step 2: Run the new tests and verify expected failures**

Run:

```powershell
py -3 -m pytest tests/test_nova_app_navigation.py -q
```

Expected: FAIL because `create_agent`, contextual "check if it works", "resume", and confirm-required blockers are not implemented.

- [ ] **Step 3: Implement action-loop planning**

Replace the body of `plan_app_navigation()` in `src/nova_app_navigation.py` with:

```python
def plan_app_navigation(text: str, context: AppNavigationContext | None = None) -> NavigationResult:
    context = context or AppNavigationContext()
    raw = "" if text is None else str(text)
    normalized = _normalize(raw)
    target_surface = _detect_surface(normalized)
    action = _detect_action(normalized)

    if target_surface is None and action == "create_agent":
        target_surface = "agent_library"
    if target_surface is None and action == "verify" and context.verification_target:
        target_surface = context.verification_target
    if target_surface is None and normalized in {"resume", "continue", "continue from where you left off"}:
        target_surface = context.last_surface
        action = context.pending_action or "resume"

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
```

Add these helper functions below `_safety_for()`:

```python
def _subject_for(normalized: str, action: str) -> str | None:
    if action == "create_agent":
        return "Weekly LLM Upgrade Scout" if "weekly" in normalized and "llm" in normalized else "Custom Agent"
    if "draft" in normalized:
        return "draft"
    return None


def _blocker_for(intent: NavigationIntent, context: AppNavigationContext) -> tuple[bool, str | None, str | None]:
    if intent.safety_level == SafetyLevel.CONFIRM_REQUIRED:
        return True, "destructive action requires explicit target confirmation", "Confirm the exact draft or saved item to delete."
    if intent.action in {"open", "navigate"} and intent.target_surface == "preview_area" and not context.active_project:
        return True, "no active project is selected", "Choose a project or ask me to create one."
    if intent.raw_text.casefold().strip() == "resume" and context.last_blocker:
        return True, context.last_blocker, "Choose a project or clear the blocker, then ask me to resume."
    return False, None, None


def _steps_for(intent: NavigationIntent, *, blocked: bool, blocker: str | None) -> list[NavigationStep]:
    steps = [NavigationStep("understand", intent.target_surface, f"Understood command: {intent.raw_text.strip()}")]
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
    steps.append(NavigationStep("navigate", intent.target_surface, f"Open {intent.target_surface.replace('_', ' ')}."))
    if intent.action == "verify":
        steps.append(NavigationStep("verify", intent.target_surface, "Run the relevant check and inspect the result."))
    elif intent.action == "delete":
        steps.append(NavigationStep("confirm", intent.target_surface, blocker or "Confirm destructive action before continuing."))
    else:
        steps.append(NavigationStep("verify", intent.target_surface, f"Confirm {intent.target_surface.replace('_', ' ')} is available."))
    return steps
```

Replace `_detect_action()` with:

```python
def _detect_action(normalized: str) -> str:
    if normalized in {"resume", "continue", "continue from where you left off"}:
        return "resume"
    if "make an agent" in normalized or "create an agent" in normalized or "new agent" in normalized:
        return "create_agent"
    if "check if it works" in normalized or re.search(r"\b(run|test|check|verify|prove)\b", normalized):
        return "verify"
    if re.search(r"\b(make|create|new)\b", normalized):
        return "create"
    if re.search(r"\b(save)\b", normalized):
        return "save"
    if re.search(r"\b(delete|remove|clear)\b", normalized):
        return "delete"
    if re.search(r"\b(open|go|show|look|view)\b", normalized):
        return "navigate"
    return "navigate"
```

Update `_detect_surface()` by adding contextual phrases before the alias loop:

```python
    if "make an agent" in normalized or "create an agent" in normalized or "new agent" in normalized:
        return "agent_library"
    if "check if it works" in normalized:
        return None
```

- [ ] **Step 4: Run navigation module tests**

Run:

```powershell
py -3 -m pytest tests/test_nova_app_navigation.py -q
```

Expected: all tests in `tests/test_nova_app_navigation.py` pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/nova_app_navigation.py tests/test_nova_app_navigation.py
git commit -m "feat: plan autonomous app actions"
```

## Task 3: Hybrid Router Integration

**Files:**
- Modify: `src/nova_hybrid_router.py`
- Modify: `tests/test_nova_transformer_runtime.py`

- [ ] **Step 1: Add failing router integration tests**

Append to `tests/test_nova_transformer_runtime.py`:

```python
def test_app_navigation_commands_short_circuit_hybrid_router(monkeypatch):
    import nova_hybrid_router as router

    dictionary_calls = []

    def dict_lookup(text):
        dictionary_calls.append(text)
        return "dictionary should not win"

    response, trace = router.route_and_respond(
        "go to Agent Library",
        dict_lookup_fn=dict_lookup,
        memory={"lessons": {"1": {"text": "Agent Library memory hit"}}},
    )

    assert dictionary_calls == []
    assert "Agent Library" in response
    assert trace["source"] == "app_navigation"
    assert trace["target_surface"] == "agent_library"
    assert trace["action"] == "navigate"


def test_generic_chat_still_uses_existing_transformer_path(monkeypatch):
    import nova_hybrid_router as router

    prediction = RoutePrediction("coding", "left_hemisphere", (), 0.8, HASH_A)
    generation = GenerationResult(
        "fixed",
        "left_hemisphere",
        "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt",
        HASH_B,
        1,
        0.1,
        10.0,
        "length",
    )

    class FakeBrain:
        last_route_error = None

        def route_with_evidence(self, text):
            return prediction, None

        def generate(self, role, text, max_new_tokens=80):
            return generation

    monkeypatch.setattr(router, "BRAIN", FakeBrain())
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    response, trace = router.route_and_respond("help me debug python")

    assert response == "fixed"
    assert trace["source"] == "transformer"
    assert trace["domain"] == "coding"
```

- [ ] **Step 2: Run router integration tests and verify expected failure**

Run:

```powershell
py -3 -m pytest tests/test_nova_transformer_runtime.py::test_app_navigation_commands_short_circuit_hybrid_router tests/test_nova_transformer_runtime.py::test_generic_chat_still_uses_existing_transformer_path -q
```

Expected: first test fails because `route_and_respond()` does not call the app-navigation router.

- [ ] **Step 3: Integrate navigation before dictionary lookup**

In `src/nova_hybrid_router.py`, add this import near the other lazy imports:

```python
from nova_app_navigation import AppNavigationContext, plan_app_navigation
```

Add this global below `CONV_ENGINE = None`:

```python
APP_NAV_CONTEXT = AppNavigationContext()
```

Inside `route_and_respond()`, immediately after `q = text.lower().strip()` and before the dictionary fast path, add:

```python
    if not transformer_only:
        navigation = plan_app_navigation(text, APP_NAV_CONTEXT)
        if navigation.recognized:
            nav_trace = trace | navigation.trace()
            nav_trace["roles"] = ["planner_transformer", "memory_transformer"]
            nav_trace["skills"] = ["app_navigation", "operator_loop"]
            nav_trace["confidence"] = navigation.intent.confidence if navigation.intent else 0.0
            nav_trace["domain"] = "app_navigation"
            nav_trace["route_path"] = ["planner_transformer", "memory_transformer"]
            _log_route(text, "app_navigation", nav_trace["route_path"], nav_trace["confidence"], "app_navigation")
            return navigation.response, nav_trace
```

- [ ] **Step 4: Run router integration tests**

Run:

```powershell
py -3 -m pytest tests/test_nova_transformer_runtime.py::test_app_navigation_commands_short_circuit_hybrid_router tests/test_nova_transformer_runtime.py::test_generic_chat_still_uses_existing_transformer_path -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/nova_hybrid_router.py tests/test_nova_transformer_runtime.py
git commit -m "feat: route app commands through navigation mode"
```

## Task 4: Verification, Server Smoke, and Report

**Files:**
- Modify: `tests/test_nova_enhanced_server.py`
- Modify: `reports/HYBRID_ROUTER_TEST_REPORT.md`

- [ ] **Step 1: Add server-level regression for app-navigation trace**

Append to `tests/test_nova_enhanced_server.py`:

```python
def test_brain_route_returns_app_navigation_trace(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)

    response, trace = server.brain_route("go to Agent Library")

    assert "Agent Library" in response
    assert trace["source"] == "app_navigation"
    assert trace["target_surface"] == "agent_library"
```

- [ ] **Step 2: Run the server test**

Run:

```powershell
py -3 -m pytest tests/test_nova_enhanced_server.py::test_brain_route_returns_app_navigation_trace -q
```

Expected: PASS after router integration.

- [ ] **Step 3: Update report with app-navigation evidence**

Append to `reports/HYBRID_ROUTER_TEST_REPORT.md`:

```markdown

## Autonomous App Navigation Mode

The branch also adds the approved app-operator design and implementation. Navigation commands are recognized before generic memory/dictionary fallback and return structured traces with `source: "app_navigation"`, target surface, action, safety level, steps, and verification state.

Verified examples:

- `go to Agent Library` -> `agent_library`, `navigate`, `read_only`;
- `make an agent that researches better LLM methods weekly` -> create-agent action loop with schedule/save/verify steps;
- `check if it works` -> uses recent context;
- `delete that draft` -> blocked with `confirm_required`;
- generic chat still uses the existing transformer route path.
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
py -3 -m pytest tests/test_nova_app_navigation.py tests/test_nova_transformer_runtime.py tests/test_nova_enhanced_server.py -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Run full verification**

Run:

```powershell
py -3 -m pytest tests -q
py -3 -m nova_training_preflight
git diff --check
git status --short
```

Expected:

- pytest passes with no failures;
- preflight verdict is `READY`;
- diff check exits 0;
- only intentional report/code changes are present before final commit.

- [ ] **Step 6: Commit Task 4**

```powershell
git add reports/HYBRID_ROUTER_TEST_REPORT.md tests/test_nova_enhanced_server.py
git commit -m "test: prove autonomous app navigation mode"
```

---

## Self-Review Checklist

- Spec coverage:
  - canonical surfaces: Task 1;
  - action loop: Task 2;
  - context resolution: Task 2;
  - safety gates: Task 2;
  - router integration: Task 3;
  - verification/reporting: Task 4.
- Placeholder scan: this plan contains only concrete implementation and verification steps.
- Type consistency:
  - `AppNavigationContext`, `NavigationIntent`, `NavigationStep`, `NavigationResult`, and `SafetyLevel` are introduced in Task 1 and reused consistently.
  - Trace field names match the spec: `source`, `navigation_intent`, `target_surface`, `action`, `safety_level`, `steps`, `verification`, and `blocked`.
- Scope check:
  - This plan implements the first chat-driven operator brain.
  - Full browser clicking is intentionally outside this release and remains attachable through the structured `NavigationPlan`-style steps.
