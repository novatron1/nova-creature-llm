from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_runtime.agent_run import AgentRun, AgentRunState
from nova_runtime.contracts import build_run_contract, canonical_json, sha256_json


def test_run_contract_is_immutable_and_hash_stable():
    contract = build_run_contract(
        run_id="run_001",
        goal="Edit the project and verify the result",
        owner_id="local-user",
        project_id="nova-creature",
        workspace_root="C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP",
        allowed_roots=["C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP"],
        allowed_tools=["filesystem.read", "filesystem.write", "terminal.run"],
        allowed_resources=["filesystem://workspace", "terminal://local"],
        time_budget_seconds=900,
        tool_budget=20,
        cost_budget=0.0,
        memory_budget=8,
    )

    assert contract.contract_hash == sha256_json(contract.to_hash_payload())
    assert contract.goal_summary == "Edit the project and verify the result"
    with pytest.raises((AttributeError, TypeError)):
        contract.goal = "changed"


def test_canonical_json_orders_keys_and_hashes_stably():
    payload = {"b": 2, "a": 1, "nested": {"z": 9, "x": 7}}
    assert canonical_json(payload) == '{"a":1,"b":2,"nested":{"x":7,"z":9}}'
    assert sha256_json(payload) == sha256_json({"nested": {"x": 7, "z": 9}, "a": 1, "b": 2})


def test_agent_run_state_machine_allows_only_valid_transitions():
    contract = build_run_contract(
        run_id="run_001",
        goal="Edit the project and verify the result",
        owner_id="local-user",
        project_id="nova-creature",
        workspace_root="C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP",
        allowed_roots=["C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP"],
        allowed_tools=["filesystem.read", "filesystem.write", "terminal.run"],
        allowed_resources=["filesystem://workspace", "terminal://local"],
        time_budget_seconds=900,
        tool_budget=20,
        cost_budget=0.0,
        memory_budget=8,
    )
    run = AgentRun.create(contract=contract)

    assert run.state == AgentRunState.PLANNED
    run.transition(AgentRunState.AUTHORIZED, reason="approved")
    run.transition(AgentRunState.EXECUTING, reason="starting")
    run.transition(AgentRunState.VERIFYING, reason="tests complete")
    run.transition(AgentRunState.COMPLETED, reason="verified")
    assert run.state == AgentRunState.COMPLETED
    assert run.history[-1]["state"] == AgentRunState.COMPLETED.value


def test_agent_run_rejects_invalid_transition_sequence():
    contract = build_run_contract(
        run_id="run_002",
        goal="Edit the project and verify the result",
        owner_id="local-user",
        project_id="nova-creature",
        workspace_root="C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP",
        allowed_roots=["C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP"],
        allowed_tools=["filesystem.read", "filesystem.write", "terminal.run"],
        allowed_resources=["filesystem://workspace", "terminal://local"],
        time_budget_seconds=900,
        tool_budget=20,
        cost_budget=0.0,
        memory_budget=8,
    )
    run = AgentRun.create(contract=contract)

    with pytest.raises(ValueError, match="Invalid AgentRun transition"):
        run.transition(AgentRunState.COMPLETED, reason="skipped execution")
