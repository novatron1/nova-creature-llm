"""
Agentic wrapper for Nova Creature.

This module adds planning, safe tool use, approval gates, memory, tracing, and
self-checking around the existing Nova pipeline. It does not replace models,
train weights, or alter checkpoint/evaluation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
import json
import os
import re
import uuid


ROOT = Path(__file__).resolve().parents[1]
AGENT_TRACE_DIR = ROOT / "logs" / "agent_traces"


@dataclass
class AgentConfig:
    agent_mode: bool = True
    max_steps: int = 6
    require_approval: bool = True
    allow_shell: bool = False
    allow_file_write: bool = False
    allow_web: bool = False
    trace: bool = True


@dataclass
class AgentStep:
    step_number: int
    thought_summary: str = ""
    action_type: str = "reasoning"
    action_name: str = ""
    action_args: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    status: str = "pending"
    error: str = ""


@dataclass
class AgentTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    risk_level: str = "safe"
    requires_approval: bool = False
    callable: Callable[[dict[str, Any]], dict[str, Any]] | None = None


@dataclass
class AgentTrace:
    trace_id: str
    user_input: str
    mode: str = "agent_mode"
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, event_type: str, **payload) -> None:
        self.events.append(
            {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                **_redact_obj(payload),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "user_input": _redact_text(self.user_input),
            "mode": self.mode,
            "events": self.events,
        }


@dataclass
class AgentState:
    user_input: str
    current_goal: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    steps_taken: list[AgentStep] = field(default_factory=list)
    tool_results: list[Any] = field(default_factory=list)
    final_answer: str = ""
    errors: list[str] = field(default_factory=list)
    requires_approval: bool = False
    approval_request: dict[str, Any] = field(default_factory=dict)
    memory_context: list[dict[str, Any]] = field(default_factory=list)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    config: AgentConfig = field(default_factory=lambda: get_agent_config())
    approval_granted: bool = False
    trace: AgentTrace | None = None


_PENDING_APPROVAL: dict[str, Any] | None = None
_SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9_-]{8,}|api[_-]?key\s*[:=]\s*\S+|token\s*[:=]\s*\S+|password\s*[:=]\s*\S+|secret\s*[:=]\s*\S+)"
)


def _parse_bool(value, default=True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _read_config_file_values() -> dict[str, Any]:
    values = {}
    for path in (ROOT / ".nova_llm_config", ROOT / ".env"):
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
        except Exception:
            pass

    json_path = ROOT / "nova_llm_config.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                values.update(data)
        except Exception:
            pass
    return values


def get_agent_config(overrides: dict[str, Any] | None = None) -> AgentConfig:
    raw = _read_config_file_values()
    raw.update(os.environ)
    if overrides:
        raw.update(overrides)
    return AgentConfig(
        agent_mode=_parse_bool(raw.get("NOVA_AGENT_MODE"), True),
        max_steps=max(1, int(raw.get("NOVA_AGENT_MAX_STEPS", 6) or 6)),
        require_approval=_parse_bool(raw.get("NOVA_AGENT_REQUIRE_APPROVAL"), True),
        allow_shell=_parse_bool(raw.get("NOVA_AGENT_ALLOW_SHELL"), False),
        allow_file_write=_parse_bool(raw.get("NOVA_AGENT_ALLOW_FILE_WRITE"), False),
        allow_web=_parse_bool(raw.get("NOVA_AGENT_ALLOW_WEB"), False),
        trace=_parse_bool(raw.get("NOVA_AGENT_TRACE"), True),
    )


def _redact_text(text) -> str:
    return _SECRET_RE.sub("[REDACTED]", str(text or ""))


def _redact_obj(value):
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {str(k): _redact_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_obj(v) for v in value]
    return value


def initialize_agent_state(user_input: str, config: AgentConfig | None = None) -> AgentState:
    state = AgentState(user_input=str(user_input or ""), config=config or get_agent_config())
    state.current_goal = state.user_input.strip()
    state.trace = AgentTrace(trace_id=state.trace_id, user_input=state.user_input)
    state.trace.record("turn_started", user_input=state.user_input)
    return state


def get_pending_approval() -> dict[str, Any] | None:
    return _PENDING_APPROVAL


def clear_pending_approval() -> None:
    global _PENDING_APPROVAL
    _PENDING_APPROVAL = None


def should_use_agent_mode(user_input: str, config: AgentConfig | None = None) -> bool:
    config = config or get_agent_config()
    if not config.agent_mode:
        return False
    q = str(user_input or "").strip().lower()
    if not q:
        return False
    if q in {"approve", "cancel"} and _PENDING_APPROVAL:
        return True
    casual = {"hi", "hello", "hey", "what is your name", "how are you"}
    if q in casual:
        return False
    triggers = (
        "agent mode",
        "agentic",
        "use agent",
        "agent write",
        "agent read",
        "agent list",
        "agent search",
        "agent run",
        "use tools",
        "tool",
        "read project file",
        "list project files",
        "search project",
        "search code",
        "write project file",
        "run project tests",
        "shell command",
        "inspect project",
        "plan and execute",
    )
    return any(trigger in q for trigger in triggers)


def planner_prompt(user_input: str, memory_context=None) -> str:
    return f"""You are Nova Planner. Break the user goal into a small safe plan.
Return JSON only with goal, needs_tools, plan, risk_level, approval_needed.
Prefer safe read-only actions first. Never request risky tools without approval.

User goal: {user_input}
Relevant memory: {json.dumps(memory_context or [], ensure_ascii=False)}
"""


def nova_planner(user_input: str, memory_context=None) -> dict[str, Any]:
    return create_plan(user_input, memory_context or [])


def nova_executor(state: AgentState, step: AgentStep) -> AgentStep:
    return execute_tool_or_reasoning_step(step, state)


def nova_critic(state: AgentState) -> dict[str, str]:
    return critique_progress(state)


def nova_memory_keeper(state: AgentState) -> str:
    return f"Goal: {state.current_goal}; final: {state.final_answer}"[:500]


def nova_communicator(state: AgentState) -> str:
    return synthesize_final_answer(state)


def _extract_query(user_input: str) -> str:
    text = str(user_input or "")
    quoted = re.search(r"['\"]([^'\"]+)['\"]", text)
    if quoted:
        return quoted.group(1).strip()
    match = re.search(r"\bfor\s+(.+)$", text, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip(".")
    return text.strip()


def _extract_path_and_content(user_input: str) -> tuple[str, str]:
    text = str(user_input or "")
    match = re.search(r"\bwrite\s+(?:project\s+)?file\s+([^\s]+)\s+with\s+(.+)$", text, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    match = re.search(r"\b(?:edit|modify)\s+(?:project\s+)?file\s+([^\s]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip(), ""
    return "agent_output.txt", text


def create_plan(user_input: str, memory_context=None) -> dict[str, Any]:
    q = str(user_input or "").lower()
    goal = str(user_input or "").strip()
    steps = []
    risk = "safe"
    approval_needed = False

    if "write project file" in q or re.search(r"\bwrite\s+file\b", q) or "modify project file" in q:
        path, content = _extract_path_and_content(user_input)
        steps.append(
            {
                "step": 1,
                "description": f"Write requested content to {path}.",
                "tool_needed": "write_project_file",
                "action_args": {"path": path, "content": content},
            }
        )
        risk = "high"
        approval_needed = True
    elif "run project tests" in q:
        command = "py -m pytest -p no:cacheprovider"
        steps.append(
            {
                "step": 1,
                "description": "Run the approved project test suite.",
                "tool_needed": "run_project_tests",
                "action_args": {"command": command},
            }
        )
        risk = "medium"
    elif "shell command" in q:
        command = re.sub(r"(?i)^.*shell command\s*", "", goal).strip() or "echo hi"
        steps.append(
            {
                "step": 1,
                "description": "Run the requested shell command if allowed.",
                "tool_needed": "run_shell_command",
                "action_args": {"command": command},
            }
        )
        risk = "high"
        approval_needed = True
    elif "web" in q or "search online" in q:
        steps.append(
            {
                "step": 1,
                "description": "Search the web if enabled and approved.",
                "tool_needed": "web_search",
                "action_args": {"query": _extract_query(user_input)},
            }
        )
        risk = "medium"
        approval_needed = True
    elif "read project file" in q:
        match = re.search(r"\bread project file\s+([^\s]+)", goal, re.IGNORECASE)
        path = match.group(1) if match else "nova_enhanced_server.py"
        steps.append(
            {
                "step": 1,
                "description": f"Read {path} inside the project.",
                "tool_needed": "read_project_file",
                "action_args": {"path": path},
            }
        )
    elif "list project files" in q or "inspect project" in q:
        steps.append(
            {
                "step": 1,
                "description": "List project files in the Nova project folder.",
                "tool_needed": "list_project_files",
                "action_args": {"path": ".", "max_files": 60},
            }
        )
    elif "search project" in q or "search code" in q or "loop test" in q:
        steps.append(
            {
                "step": 1,
                "description": "Search project text for the requested phrase.",
                "tool_needed": "search_project_text",
                "action_args": {"query": _extract_query(user_input), "path": ".", "max_results": 20},
            }
        )
    else:
        steps.append(
            {
                "step": 1,
                "description": "Answer directly without tools.",
                "tool_needed": None,
                "action_args": {},
            }
        )

    return {
        "goal": goal,
        "needs_tools": any(step.get("tool_needed") for step in steps),
        "plan": steps,
        "risk_level": risk,
        "approval_needed": approval_needed,
    }


def decide_next_action(state: AgentState) -> AgentStep:
    if len(state.steps_taken) >= state.config.max_steps:
        return AgentStep(
            step_number=len(state.steps_taken) + 1,
            thought_summary="Max agent step limit reached.",
            action_type="final_answer",
            status="max_steps",
        )

    plan_steps = list((state.plan or {}).get("plan", []))
    if len(state.steps_taken) >= len(plan_steps):
        return AgentStep(
            step_number=len(state.steps_taken) + 1,
            thought_summary="Plan is complete.",
            action_type="final_answer",
            status="done",
        )

    item = plan_steps[len(state.steps_taken)]
    tool_name = item.get("tool_needed")
    return AgentStep(
        step_number=int(item.get("step", len(state.steps_taken) + 1)),
        thought_summary=str(item.get("description", "")),
        action_type="tool" if tool_name else "reasoning",
        action_name=str(tool_name or "direct_reasoning"),
        action_args=dict(item.get("action_args", {})),
    )


def validate_tool_call(tool_name: str, args: dict[str, Any] | None, state: AgentState | None = None) -> dict:
    from nova_tools import validate_tool_call as _validate

    return _validate(tool_name, args or {}, state)


def action_requires_approval(step: AgentStep, state: AgentState) -> dict:
    if step.action_type != "tool":
        return {"allowed": True, "approval_required": False, "reason": "No tool call."}
    return validate_tool_call(step.action_name, step.action_args, state)


def build_approval_request(step: AgentStep, validation: dict) -> dict[str, Any]:
    return {
        "action_name": step.action_name,
        "action_args": _redact_obj(step.action_args),
        "reason": validation.get("reason", "Approval required."),
        "risk": validation.get("risk_level", "risky"),
    }


def approval_needed_response(state: AgentState) -> str:
    request = state.approval_request
    args = request.get("action_args", {})
    file_line = f"\nFile: {args.get('path')}" if args.get("path") else ""
    command_line = f"\nCommand: {args.get('command')}" if args.get("command") else ""
    return (
        "Yeah, I can do that, but this step changes project state. Approve this action?\n\n"
        f"Action: {request.get('action_name')}{file_line}{command_line}\n"
        f"Reason: {request.get('reason')}\n"
        f"Risk: {request.get('risk')}\n\n"
        "Reply APPROVE to continue or CANCEL to stop."
    )


def execute_tool_or_reasoning_step(step: AgentStep, state: AgentState) -> AgentStep:
    if step.action_type == "reasoning":
        step.status = "done"
        step.result = {"ok": True, "message": "No external tool needed."}
        return step

    from nova_tools import get_tool_registry

    registry = get_tool_registry()
    tool = registry.get(step.action_name)
    if not tool or not tool.callable:
        step.status = "error"
        step.error = f"Tool not available: {step.action_name}"
        state.errors.append(step.error)
        return step
    try:
        step.result = tool.callable(step.action_args)
        step.status = "done"
    except Exception as exc:
        step.status = "error"
        step.error = str(exc)
        state.errors.append(step.error)
    return step


def critique_progress(state: AgentState) -> dict[str, str]:
    if state.requires_approval and state.errors:
        return {"status": "fail_safe", "reason": "Unsafe action was blocked.", "next_hint": "Ask user for a safer path."}
    if state.requires_approval:
        return {"status": "ask_approval", "reason": "Approval is needed.", "next_hint": "Wait for APPROVE or CANCEL."}
    if state.final_answer:
        return {"status": "done", "reason": "Final answer is ready.", "next_hint": ""}
    if state.errors:
        return {"status": "replan", "reason": state.errors[-1], "next_hint": "Try a safer read-only step."}
    if state.steps_taken and all(step.status == "done" for step in state.steps_taken):
        return {"status": "done", "reason": "Plan steps completed.", "next_hint": "Synthesize final answer."}
    return {"status": "continue", "reason": "More work remains.", "next_hint": ""}


def recover_or_replan(state: AgentState) -> None:
    if state.trace:
        state.trace.record("replan", errors=state.errors[-3:])


def synthesize_final_answer(state: AgentState) -> str:
    if state.final_answer:
        return state.final_answer
    if state.requires_approval:
        return approval_needed_response(state)
    if state.errors:
        return "I stopped safely because " + state.errors[-1]
    if not state.steps_taken:
        return "I made a small plan, but there wasn’t a tool step to run."

    step = state.steps_taken[-1]
    result = step.result if isinstance(step.result, dict) else {}
    if step.action_name == "search_project_text":
        matches = result.get("matches", [])
        if matches:
            first = matches[0]
            return f"I searched the project and found {len(matches)} match(es). First hit: {first.get('path')}:{first.get('line')}."
        return "I searched the project but didn’t find a matching line."
    if step.action_name == "list_project_files":
        files = result.get("files", [])
        names = ", ".join(item.get("path", "") for item in files[:5])
        return f"I listed {len(files)} project file(s). First ones: {names}."
    if step.action_name == "read_project_file":
        return f"I read {result.get('path')}; it has {len(result.get('content', ''))} characters in the returned slice."
    if step.action_name == "write_project_file":
        return f"Approved — I ran write_project_file and wrote {result.get('path')}."
    if step.action_name == "run_project_tests":
        return f"I ran the approved tests. Return code: {result.get('returncode')}."
    return f"I completed {step.action_name}."


def _save_trace(state: AgentState) -> None:
    if not state.config.trace or not state.trace:
        return
    payload = state.trace.to_dict()
    payload.update(
        {
            "timestamp": datetime.now().isoformat(),
            "trace_id": state.trace_id,
            "user_input": _redact_text(state.user_input),
            "mode": "agent_mode",
            "plan": _redact_obj(state.plan),
            "tool_calls": [_redact_obj(asdict(step)) for step in state.steps_taken],
            "approval_requests": _redact_obj(state.approval_request),
            "critic_statuses": [event for event in state.trace.events if event.get("event_type") == "critic"],
            "final_answer": _redact_text(state.final_answer),
            "errors": _redact_obj(state.errors),
        }
    )
    AGENT_TRACE_DIR.mkdir(parents=True, exist_ok=True)
    (AGENT_TRACE_DIR / f"{state.trace_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _public_trace(state: AgentState) -> dict[str, Any]:
    return {
        "trace_id": state.trace_id,
        "mode": "agent_mode",
        "agent_mode": True,
        "plan": _redact_obj(state.plan),
        "steps_taken_count": len(state.steps_taken),
        "tool_results": _redact_obj(state.tool_results),
        "requires_approval": state.requires_approval,
        "approval_request": _redact_obj(state.approval_request),
        "errors": _redact_obj(state.errors),
        "final_answer": _redact_text(state.final_answer),
        "max_steps": state.config.max_steps,
    }


def _execute_approved_action(user_input: str) -> tuple[str, dict]:
    global _PENDING_APPROVAL
    pending = _PENDING_APPROVAL
    if not pending:
        state = initialize_agent_state(user_input)
        state.final_answer = "There is no pending action to approve."
        return state.final_answer, _public_trace(state)

    state = initialize_agent_state(user_input)
    state.approval_granted = True
    step_data = pending["step"]
    step = AgentStep(**step_data)
    state.trace_id = pending.get("trace_id") or state.trace_id
    state.current_goal = pending.get("goal", "")
    state.plan = pending.get("plan", {})
    state.trace = AgentTrace(trace_id=state.trace_id, user_input=user_input)
    state.trace.record("approval_received", action_name=step.action_name, action_args=step.action_args)

    validation = validate_tool_call(step.action_name, step.action_args, state)
    if not validation.get("allowed"):
        state.errors.append(validation.get("reason", "Approved action was still blocked."))
        state.final_answer = synthesize_final_answer(state)
    else:
        executed = execute_tool_or_reasoning_step(step, state)
        state.steps_taken.append(executed)
        state.tool_results.append(executed.result)
        state.final_answer = synthesize_final_answer(state)

    _PENDING_APPROVAL = None
    try:
        from nova_agent_memory import save_agent_memory

        save_agent_memory(state)
    except Exception:
        pass
    _save_trace(state)
    trace = _public_trace(state)
    trace["approved_action"] = {"action_name": step.action_name, "action_args": _redact_obj(step.action_args)}
    return state.final_answer, trace


def _cancel_approval(user_input: str) -> tuple[str, dict]:
    global _PENDING_APPROVAL
    state = initialize_agent_state(user_input)
    _PENDING_APPROVAL = None
    state.final_answer = "Canceled. I discarded the pending action and did not change anything."
    trace = _public_trace(state)
    trace["approval_canceled"] = True
    return state.final_answer, trace


def run_agentic_turn(user_input: str) -> tuple[str, dict]:
    global _PENDING_APPROVAL
    q = str(user_input or "").strip().lower()
    if q == "approve":
        return _execute_approved_action(user_input)
    if q == "cancel":
        return _cancel_approval(user_input)

    state = initialize_agent_state(user_input)
    try:
        from nova_agent_memory import load_relevant_memory, save_agent_memory

        state.memory_context = load_relevant_memory(user_input)
    except Exception:
        state.memory_context = []

    state.plan = create_plan(user_input, state.memory_context)
    if state.trace:
        state.trace.record("plan_created", plan=state.plan)

    for _ in range(state.config.max_steps):
        step = decide_next_action(state)
        if step.action_type == "final_answer":
            if step.status == "max_steps":
                state.errors.append("Max agent step limit reached.")
            break

        validation = action_requires_approval(step, state)
        if validation.get("approval_required"):
            state.requires_approval = True
            state.approval_request = build_approval_request(step, validation)
            _PENDING_APPROVAL = {
                "trace_id": state.trace_id,
                "goal": state.current_goal,
                "plan": state.plan,
                "step": asdict(step),
                "approval_request": state.approval_request,
            }
            state.final_answer = approval_needed_response(state)
            if state.trace:
                state.trace.record("approval_required", approval_request=state.approval_request)
            _save_trace(state)
            return state.final_answer, _public_trace(state)

        if not validation.get("allowed"):
            step.status = "blocked"
            step.error = validation.get("reason", "Tool call blocked.")
            state.errors.append(step.error)
            state.steps_taken.append(step)
            if state.trace:
                state.trace.record("tool_blocked", action_name=step.action_name, reason=step.error)
            break

        step = execute_tool_or_reasoning_step(step, state)
        state.steps_taken.append(step)
        state.tool_results.append(step.result)
        if state.trace:
            state.trace.record("tool_result", action_name=step.action_name, status=step.status, result=step.result, error=step.error)

        critique = critique_progress(state)
        if state.trace:
            state.trace.record("critic", **critique)
        if critique["status"] in {"done", "fail_safe"}:
            break
        if critique["status"] == "replan":
            recover_or_replan(state)
            break

    state.final_answer = synthesize_final_answer(state)
    try:
        from nova_agent_memory import save_agent_memory

        save_agent_memory(state)
    except Exception:
        pass
    _save_trace(state)
    return state.final_answer, _public_trace(state)
