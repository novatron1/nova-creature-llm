from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_runtime.contracts import build_run_contract, sha256_json  # noqa: E402
from nova_runtime.ledger import EvidenceLedger  # noqa: E402
from nova_runtime.permissions import ActionSignature, PermissionGateway  # noqa: E402


def _build_contract() -> object:
    return build_run_contract(
        run_id="run_ledger_001",
        goal="Edit a file and verify it",
        owner_id="local-user",
        project_id="nova-creature",
        workspace_root="C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP",
        allowed_roots=["C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP"],
        allowed_tools=["filesystem.read", "filesystem.write"],
        allowed_resources=["filesystem://workspace"],
        time_budget_seconds=300,
        tool_budget=10,
        cost_budget=0.0,
        memory_budget=4,
    )


def test_permission_gateway_rejects_workspace_escape():
    contract = _build_contract()
    gateway = PermissionGateway(contract=contract)
    action = ActionSignature.from_tool_call(
        tool_id="filesystem.write",
        arguments={"path": "C:/Users/nova/Documents/secrets.txt"},
        resource_uri="filesystem://C:/Users/nova/Documents/secrets.txt",
        contract_hash=contract.contract_hash,
    )

    decision = gateway.authorize_tool(
        tool_id="filesystem.write",
        arguments={"path": "C:/Users/nova/Documents/secrets.txt"},
        action_signature=action,
    )

    assert decision.disposition == "BLOCK"
    assert decision.rule_id == "WORKSPACE_ESCAPE"
    assert decision.can_continue is False


def test_permission_gateway_allows_exact_tool_within_root():
    contract = _build_contract()
    gateway = PermissionGateway(contract=contract)
    action = ActionSignature.from_tool_call(
        tool_id="filesystem.write",
        arguments={"path": "C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP/readme.txt"},
        resource_uri="filesystem://C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP/readme.txt",
        contract_hash=contract.contract_hash,
    )

    decision = gateway.authorize_tool(
        tool_id="filesystem.write",
        arguments={"path": "C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP/readme.txt"},
        action_signature=action,
    )

    assert decision.disposition == "ALLOW"
    assert decision.rule_id == "ALLOW_EXACT_SIGNATURE"


def test_evidence_ledger_is_append_only_and_hash_chained(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    first = ledger.append(event_type="planned", payload={"goal_hash": "g1"})
    second = ledger.append(event_type="authorized", payload={"goal_hash": "g1"})

    assert first.entry_hash != second.entry_hash
    assert second.previous_hash == first.entry_hash
    assert first.sequence == 1
    assert second.sequence == 2

    raw = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    assert "goal_hash" in raw
    assert first.entry_hash in raw
    assert second.entry_hash in raw

