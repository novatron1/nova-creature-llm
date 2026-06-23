# Nova Autonomous App Navigation Design

**Date:** June 23, 2026  
**Status:** Approved concept, awaiting written-spec review  
**Default target:** Local Nova Creature desktop app command handling  

## Purpose

Nova Creature should act like a capable app operator when the user gives a goal. The user should not need to explain every small click, page, button, or verification step. Nova should understand commands such as "go to Agent Library", "open the builder", "check if it works", "look at the logs", "save this", or "fix anything that stops you", map the command to the right app surface, perform the safest available action, verify the result, and report honestly.

The first release is an internal navigation/action brain that turns app-operation language into structured plans and responses. It does not delete major data, deploy publicly, expose secrets, or pretend unavailable UI controls exist. When a command is clear and supported, Nova acts. When an action is destructive or missing required information, Nova asks for that specific permission or reports the blocker.

## User Experience

Nova recognizes app-operation requests before generic memory or fallback answers. It treats short follow-ups like "yes", "ok", "1", "b", "resume", and "check if it works" as contextual commands when recent state makes the target clear.

Supported user commands include:

- navigation: "go home", "open chat", "go to Agent Library", "open the builder", "open preview", "open settings";
- inspection: "check memory", "look at the logs", "show saved projects", "open file manager";
- action: "make an agent", "edit that agent", "save this", "run the test", "fix the app";
- verification: "check if it works", "prove it", "reload/check persistence";
- recovery: "fix anything that stops you", "resume", "continue from where you left off";
- guarded destructive requests: "delete that draft" only after the target is unambiguous and the operation is safe or explicitly confirmed.

Nova responds with a concise operator report:

```text
I understood: make an agent that researches better LLM methods weekly.
Went to: Agent Library.
Did: created Weekly LLM Upgrade Scout, added purpose/topics/schedule, saved.
Checked: reopened the saved agent and verified the weekly schedule.
Result: ready.
```

If blocked:

```text
I understood: open the preview.
Blocker: no active project is selected.
What I checked: saved projects and current app state.
Next safe step: choose a project or ask me to create one.
```

## Navigation Surfaces

The navigation brain knows the canonical app surfaces and common aliases:

- `home`
- `chat`
- `agent_library`
- `app_builder`
- `memory_panel`
- `settings`
- `tools_page`
- `research_panel`
- `test_check_page`
- `saved_projects`
- `preview_area`
- `debug_logs`
- `scheduler`
- `file_manager`

Each surface has:

- user-facing names and aliases;
- supported actions;
- required inputs;
- safety level;
- verification method;
- fallback/blocker message.

This keeps command interpretation separate from UI implementation. A future browser or frontend layer can consume the same structured navigation plan.

## Action Loop

Every supported app-operation command follows the same loop:

1. Understand the command.
2. Resolve what "it", "this", "that", "resume", or a bare option refers to from recent context.
3. Choose the target surface.
4. Choose the action and required controls.
5. Perform the action if safe and supported.
6. Verify the result.
7. If blocked, inspect the cause.
8. Fix the blocker when the fix is safe and in scope.
9. Re-test after any fix.
10. Report what happened with pass/fail evidence.

The loop is represented as structured data, not only prose, so tests can assert which page/action/check Nova selected.

## Architecture

### 1. App navigation module

Create a focused module, `src/nova_app_navigation.py`, responsible for command interpretation and action-loop planning.

Core data objects:

- `NavigationSurface`: canonical surface, aliases, supported actions;
- `NavigationIntent`: understood user goal, target surface, action, confidence, safety level;
- `NavigationStep`: one operator step such as navigate, click, type, save, inspect, test, repair, verify;
- `NavigationPlan`: ordered steps plus blocker/verification metadata;
- `NavigationResult`: final report, status, performed steps, verification result.

The first implementation can simulate local app operations through structured plans where direct UI automation is not yet available. It must still be useful: the response tells the user exactly where Nova would go, what it would do, and which local/server checks prove success.

### 2. Context resolver

The resolver keeps recent operator context in memory for the current server process:

- last surface;
- last active project/agent/draft if known;
- last pending action;
- last verification target;
- last blocker.

This lets "check if it works", "open it", "delete that draft", or "resume" refer to recent work without asking the user to restate everything. Ambiguous destructive commands still require explicit target confirmation.

### 3. Router integration

`nova_hybrid_router.route_and_respond()` gets an early app-operation detector before dictionary/memory fallback. If a command is recognized, it returns the navigation/operator response and a trace with:

- `source: "app_navigation"`;
- `navigation_intent`;
- `target_surface`;
- `action`;
- `safety_level`;
- `steps`;
- `verification`;
- `blocked` when applicable.

The server endpoint can return this trace through the existing `/api/chat` response shape, so the current app can display it without a new protocol.

### 4. Optional server endpoints

If needed, add small read-only/support endpoints later, such as:

- `/api/navigation/surfaces` — list known pages/actions;
- `/api/navigation/status` — show last navigation context;
- `/api/navigation/run` — execute a structured navigation command.

The first implementation should avoid new endpoints unless tests show the chat route is not enough.

## Safety Rules

Nova may perform or plan reversible actions when intent is clear. It must not silently perform high-risk operations.

Safety levels:

- `read_only`: inspect, open, view, preview, show logs, show settings.
- `safe_write`: save a draft, create an agent, run tests, repair generated code inside the active project.
- `confirm_required`: delete drafts, overwrite a stable checkpoint, remove saved projects, clear memory, change credentials, publish/deploy externally.
- `blocked`: action unsupported, target ambiguous, missing data, or unsafe without external permission.

Nova must:

- avoid deleting major data without confirmation;
- avoid exposing secrets;
- avoid claiming a test passed without evidence;
- preserve stable checkpoints before risky edits;
- keep local/private changes local unless the user asks to publish;
- report blockers clearly instead of pretending to click unavailable controls.

## Verification

Tests must prove:

1. Surface recognition:
   - "go to Agent Library" targets `agent_library`;
   - "open the builder" targets `app_builder`;
   - "look at the logs" targets `debug_logs`.
2. Action planning:
   - "make an agent that researches better LLM methods weekly" creates a plan with navigate, create, fill, schedule, save, verify.
   - "run the test" targets the test/check page and includes a verification step.
3. Context resolution:
   - after an app-builder command, "check if it works" uses the active project/test target;
   - "resume" continues the last blocked or pending action.
4. Safety:
   - "delete that draft" is `confirm_required` when the draft is ambiguous;
   - stable checkpoints are not overwritten without confirmation.
5. Router integration:
   - app-navigation commands return `source: "app_navigation"`;
   - generic chat still uses the existing hybrid route path.
6. Honest blockers:
   - unsupported pages/actions produce a blocked result with cause and next safe step.

## Initial Scope

This release adds Nova's command understanding, structured action loop, safety gating, context resolution, chat integration, and tests. It does not need full browser-click automation yet. When browser/app automation tools are available, they can attach to the same `NavigationPlan` interface and execute concrete clicks/types/reloads.

The first version should be small, testable, and useful from chat immediately.

