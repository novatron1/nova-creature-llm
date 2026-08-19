"""Bounded single-agent execution state machine for registered Nova tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import time
from typing import Any, Callable, Iterable

from nova_tool_registry import NovaToolRegistry, get_default_tool_registry


AGENT_LOOP_VERSION = "1.0"
AGENT_STATES = (
    "PLAN",
    "SELECT_ACTION",
    "VALIDATE",
    "EXECUTE",
    "OBSERVE",
    "UPDATE_PLAN",
    "VERIFY",
    "RESPOND",
)


@dataclass
class AgentAction:
    tool_name: str
    arguments: dict[str, Any] | str
    purpose: str = ""
    action_id: str = ""
    status: str = "proposed"
    authorized: bool = False
    attempted: bool = False
    observed: bool = False
    verified: bool = False
    result: Any = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.action_id:
            signature = json.dumps(
                {"tool": self.tool_name, "arguments": self.arguments},
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            self.action_id = "action_" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]

    def safe_trace(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "tool_name": self.tool_name,
            "purpose": self.purpose,
            "status": self.status,
            "authorized": self.authorized,
            "attempted": self.attempted,
            "observed": self.observed,
            "verified": self.verified,
            "error_type": self.error,
            "arguments_logged": False,
            "result_content_logged": False,
        }


@dataclass
class AgentLoopResult:
    goal: str
    status: str
    response: str
    actions: list[AgentAction]
    states_visited: list[str]
    started_at: str
    duration_ms: float
    tool_steps: int
    cancelled: bool = False
    timed_out: bool = False
    awaiting_authorization: bool = False
    version: str = AGENT_LOOP_VERSION

    def safe_trace(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": self.status,
            "states_visited": list(self.states_visited),
            "duration_ms": round(self.duration_ms, 2),
            "tool_steps": self.tool_steps,
            "cancelled": self.cancelled,
            "timed_out": self.timed_out,
            "awaiting_authorization": self.awaiting_authorization,
            "actions": [item.safe_trace() for item in self.actions],
            "goal_content_logged": False,
        }


class NovaAgentLoop:
    """Execute a finite plan without recursion or invented tools."""

    def __init__(
        self,
        registry: NovaToolRegistry | None = None,
        *,
        max_tool_steps: int = 4,
        max_retries_per_step: int = 1,
        total_timeout_seconds: int = 120,
    ) -> None:
        self.registry = registry or get_default_tool_registry()
        self.max_tool_steps = max(1, min(int(max_tool_steps), 20))
        self.max_retries_per_step = max(0, min(int(max_retries_per_step), 2))
        self.total_timeout_seconds = max(1, int(total_timeout_seconds))

    @staticmethod
    def _needs_confirmation(tool: Any) -> bool:
        return bool(
            tool.confirmation_policy in {"always", "dangerous"}
            or tool.risk_level in {"high", "critical", "destructive", "financial"}
            or tool.read_write_classification
            in {"write", "destructive", "financial", "account_change", "publish", "external_message"}
        )

    @staticmethod
    def _signature(action: AgentAction, parsed: dict[str, Any]) -> str:
        payload = json.dumps(
            {"tool": action.tool_name, "arguments": parsed},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _response(actions: list[AgentAction], status: str) -> str:
        if status == "awaiting_authorization":
            pending = next((item for item in actions if item.status == "awaiting_authorization"), None)
            if pending:
                return (
                    f"I prepared the {pending.tool_name} action but did not run it. "
                    "It needs your explicit approval because it can change external or local state."
                )
        if status == "cancelled":
            return "I stopped the agent run before executing any further actions."
        if status == "timed_out":
            return "The bounded agent run reached its time limit and stopped safely."
        failed = [item for item in actions if item.status == "failed"]
        if failed:
            return (
                f"I could not verify {len(failed)} planned action"
                f"{'s' if len(failed) != 1 else ''}. No failed action is being reported as complete."
            )
        completed = [item for item in actions if item.verified]
        if not completed:
            return "The plan contained no executable registered actions."
        summaries = []
        for item in completed[:4]:
            if isinstance(item.result, dict):
                if "path" in item.result:
                    summaries.append(f"{item.tool_name}: observed {item.result['path']}")
                elif "result" in item.result:
                    summaries.append(f"{item.tool_name}: {item.result['result']}")
                elif "matches" in item.result:
                    summaries.append(f"{item.tool_name}: {len(item.result['matches'])} matches")
                elif "files" in item.result:
                    summaries.append(f"{item.tool_name}: {len(item.result['files'])} files")
                else:
                    summaries.append(f"{item.tool_name}: verified")
            else:
                summaries.append(f"{item.tool_name}: verified")
        return "Completed and verified: " + "; ".join(summaries) + "."

    def run(
        self,
        goal: str,
        actions: Iterable[AgentAction | dict[str, Any]],
        *,
        scopes: set[str] | frozenset[str],
        approved_action_ids: set[str] | frozenset[str] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        regenerate_arguments: Callable[[str], str | dict[str, Any]] | None = None,
    ) -> AgentLoopResult:
        started_clock = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        states = ["PLAN"]
        normalized: list[AgentAction] = []
        for item in actions:
            normalized.append(
                item
                if isinstance(item, AgentAction)
                else AgentAction(
                    tool_name=str(item.get("tool_name") or item.get("tool_needed") or ""),
                    arguments=item.get("arguments", item.get("action_args", {})),
                    purpose=str(item.get("purpose") or item.get("description") or ""),
                    action_id=str(item.get("action_id") or ""),
                )
            )
        approved = set(approved_action_ids or ())
        seen: set[str] = set()
        tool_steps = 0
        status = "completed"

        for action in normalized:
            if tool_steps >= self.max_tool_steps:
                action.status = "step_limit_reached"
                status = "step_limit_reached"
                break
            if is_cancelled and is_cancelled():
                action.status = "cancelled"
                status = "cancelled"
                break
            if time.monotonic() - started_clock >= self.total_timeout_seconds:
                action.status = "timed_out"
                status = "timed_out"
                break
            states.append("SELECT_ACTION")
            try:
                tool = self.registry.get(action.tool_name)
            except Exception as error:
                action.status = "failed"
                action.error = type(error).__name__
                status = "failed"
                states.extend(["VALIDATE", "UPDATE_PLAN"])
                continue

            states.append("VALIDATE")
            try:
                parsed = self.registry.parse_arguments(
                    action.tool_name,
                    action.arguments,
                    regenerate=regenerate_arguments,
                )
            except Exception as error:
                action.status = "failed"
                action.error = type(error).__name__
                status = "failed"
                states.append("UPDATE_PLAN")
                continue

            signature = self._signature(action, parsed)
            if signature in seen:
                action.status = "duplicate_prevented"
                states.append("UPDATE_PLAN")
                continue
            seen.add(signature)

            needs_confirmation = self._needs_confirmation(tool)
            action.authorized = not needs_confirmation or action.action_id in approved
            if not action.authorized:
                action.status = "awaiting_authorization"
                status = "awaiting_authorization"
                break

            states.append("EXECUTE")
            action.status = "authorized"
            action.attempted = True
            tool_steps += 1
            try:
                action.result = self.registry.execute_typed(
                    action.tool_name,
                    parsed,
                    scopes,
                    confirmed=action.authorized,
                    regenerate=regenerate_arguments,
                )
                action.status = "observed"
                action.observed = True
                states.append("OBSERVE")
                # Input/output schema validation in the registry is the
                # deterministic verification boundary for a tool result.
                action.verified = True
                action.status = "verified_result"
                states.extend(["UPDATE_PLAN", "VERIFY"])
            except Exception as error:
                action.status = "failed"
                action.error = type(error).__name__
                status = "failed"
                states.extend(["OBSERVE", "UPDATE_PLAN", "VERIFY"])

        states.append("RESPOND")
        cancelled = status == "cancelled"
        timed_out = status == "timed_out"
        awaiting = status == "awaiting_authorization"
        return AgentLoopResult(
            goal=str(goal),
            status=status,
            response=self._response(normalized, status),
            actions=normalized,
            states_visited=states,
            started_at=started_at,
            duration_ms=(time.monotonic() - started_clock) * 1000,
            tool_steps=tool_steps,
            cancelled=cancelled,
            timed_out=timed_out,
            awaiting_authorization=awaiting,
        )


def run_existing_read_only_plan(
    user_input: str,
    *,
    scopes: set[str] | frozenset[str] | None = None,
) -> AgentLoopResult | None:
    """Adapt existing deterministic plans when every action is read-only.

    High-risk and approval-continuation flows remain on Nova's existing agent
    wrapper so backward-compatible approval behavior is preserved.
    """

    from nova_agentic_core import create_plan

    plan = create_plan(user_input, [])
    raw_actions = list(plan.get("plan") or plan.get("steps") or [])
    if not raw_actions:
        return None
    registry = get_default_tool_registry()
    for item in raw_actions:
        name = str(item.get("tool_name") or item.get("tool_needed") or "")
        try:
            tool = registry.get(name)
        except Exception:
            return None
        if NovaAgentLoop._needs_confirmation(tool):
            return None
    return NovaAgentLoop(registry).run(
        user_input,
        raw_actions,
        scopes=scopes
        or frozenset({"files.read", "tools.execute", "tools.list", "memory.read"}),
    )


__all__ = [
    "AGENT_LOOP_VERSION",
    "AGENT_STATES",
    "AgentAction",
    "AgentLoopResult",
    "NovaAgentLoop",
    "run_existing_read_only_plan",
]
