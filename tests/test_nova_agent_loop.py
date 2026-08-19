from __future__ import annotations

from nova_agent_loop import AgentAction, NovaAgentLoop
from nova_gateway.tools import NovaRegisteredTool
from nova_tool_registry import NovaToolRegistry


def _registry(calls: list[dict]) -> NovaToolRegistry:
    registry = NovaToolRegistry()
    registry.register(
        NovaRegisteredTool(
            name="read_value",
            version="1",
            description="Read a deterministic value.",
            input_schema={
                "type": "object",
                "required": ["key"],
                "properties": {"key": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["result"],
                "properties": {"result": {"type": "string"}},
            },
            required_permissions=["tools.execute"],
            handler=lambda args: calls.append(args) or {"result": args["key"]},
        )
    )
    registry.register(
        NovaRegisteredTool(
            name="change_value",
            version="1",
            description="Change a value.",
            input_schema={"type": "object"},
            required_permissions=["tools.execute"],
            handler=lambda args: calls.append(args) or {"ok": True},
            read_write_classification="write",
            risk_level="high",
            confirmation_policy="always",
        )
    )
    return registry


def test_bounded_loop_executes_and_verifies_read_only_action() -> None:
    calls: list[dict] = []
    result = NovaAgentLoop(_registry(calls), max_tool_steps=4).run(
        "read it",
        [AgentAction("read_value", {"key": "alpha"})],
        scopes={"tools.execute"},
    )

    assert result.status == "completed"
    assert result.tool_steps == 1
    assert result.actions[0].attempted
    assert result.actions[0].observed
    assert result.actions[0].verified
    assert result.actions[0].status == "verified_result"
    assert calls == [{"key": "alpha"}]
    assert result.states_visited[-1] == "RESPOND"


def test_duplicate_action_is_not_executed_twice() -> None:
    calls: list[dict] = []
    result = NovaAgentLoop(_registry(calls)).run(
        "read twice",
        [
            AgentAction("read_value", {"key": "same"}),
            AgentAction("read_value", {"key": "same"}),
        ],
        scopes={"tools.execute"},
    )

    assert len(calls) == 1
    assert result.actions[1].status == "duplicate_prevented"
    assert result.tool_steps == 1


def test_high_risk_action_requires_explicit_action_authorization() -> None:
    calls: list[dict] = []
    action = AgentAction("change_value", {})
    loop = NovaAgentLoop(_registry(calls))

    prepared = loop.run("change it", [action], scopes={"tools.execute"})
    assert prepared.status == "awaiting_authorization"
    assert not prepared.actions[0].attempted
    assert calls == []

    approved_action = AgentAction("change_value", {})
    completed = loop.run(
        "change it",
        [approved_action],
        scopes={"tools.execute"},
        approved_action_ids={approved_action.action_id},
    )
    assert completed.actions[0].verified
    assert len(calls) == 1


def test_step_limit_and_cancellation_stop_safely() -> None:
    calls: list[dict] = []
    registry = _registry(calls)
    limited = NovaAgentLoop(registry, max_tool_steps=1).run(
        "two reads",
        [
            AgentAction("read_value", {"key": "one"}),
            AgentAction("read_value", {"key": "two"}),
        ],
        scopes={"tools.execute"},
    )
    assert limited.status == "step_limit_reached"
    assert len(calls) == 1
    assert limited.actions[1].attempted is False

    cancelled = NovaAgentLoop(registry).run(
        "cancel",
        [AgentAction("read_value", {"key": "three"})],
        scopes={"tools.execute"},
        is_cancelled=lambda: True,
    )
    assert cancelled.cancelled
    assert cancelled.tool_steps == 0


def test_unknown_tool_is_failed_not_reported_complete() -> None:
    result = NovaAgentLoop(_registry([])).run(
        "invent",
        [AgentAction("invented_tool", {})],
        scopes={"tools.execute"},
    )
    assert result.status == "failed"
    assert result.actions[0].status == "failed"
    assert not result.actions[0].verified
    assert "could not verify" in result.response.lower()
