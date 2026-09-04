"""Deterministic permission gateway for autonomous Nova Creature runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .contracts import RunContract, canonical_json, sha256_json


@dataclass(frozen=True, slots=True)
class ActionSignature:
    tool_id: str
    arguments_hash: str
    resource_hash: str
    contract_hash: str

    @classmethod
    def from_tool_call(
        cls,
        *,
        tool_id: str,
        arguments: dict[str, Any],
        resource_uri: str,
        contract_hash: str,
    ) -> "ActionSignature":
        return cls(
            tool_id=str(tool_id),
            arguments_hash=sha256_json(arguments),
            resource_hash=sha256_json({"resource_uri": resource_uri}),
            contract_hash=str(contract_hash),
        )


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    disposition: str
    rule_id: str
    message: str
    can_continue: bool
    rollback_available: bool
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        return data


class PermissionGateway:
    def __init__(self, *, contract: RunContract) -> None:
        self.contract = contract

    def authorize_tool(
        self,
        *,
        tool_id: str,
        arguments: dict[str, Any],
        action_signature: ActionSignature,
    ) -> PermissionDecision:
        if action_signature.contract_hash != self.contract.contract_hash:
            return PermissionDecision(
                disposition="BLOCK",
                rule_id="APPROVAL_SIGNATURE_CHANGED",
                message="The action signature does not match the frozen contract.",
                can_continue=False,
                rollback_available=False,
            )

        if str(tool_id) not in self.contract.allowed_tools:
            return PermissionDecision(
                disposition="BLOCK",
                rule_id="AUTH_SCOPE_MISMATCH",
                message=f"Tool {tool_id!r} is not allowed by the run contract.",
                can_continue=False,
                rollback_available=False,
            )

        if action_signature.tool_id != str(tool_id):
            return PermissionDecision(
                disposition="BLOCK",
                rule_id="APPROVAL_SIGNATURE_CHANGED",
                message="The requested tool does not match the approved action signature.",
                can_continue=False,
                rollback_available=False,
            )

        path_candidate = self._extract_path(arguments)
        if path_candidate is not None and not self._is_within_allowed_roots(path_candidate):
            return PermissionDecision(
                disposition="BLOCK",
                rule_id="WORKSPACE_ESCAPE",
                message="The requested path resolves outside the allowed workspace roots.",
                can_continue=False,
                rollback_available=False,
            )

        return PermissionDecision(
            disposition="ALLOW",
            rule_id="ALLOW_EXACT_SIGNATURE",
            message="Action matches the frozen contract.",
            can_continue=True,
            rollback_available=False,
        )

    def _extract_path(self, arguments: dict[str, Any]) -> str | None:
        for key in ("path", "file_path", "destination", "target", "source", "root"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    def _is_within_allowed_roots(self, candidate: str) -> bool:
        candidate_path = self._safe_path(candidate)
        if candidate_path is None:
            return False
        allowed_roots = [self._safe_path(root) for root in self.contract.allowed_roots]
        allowed_roots = [root for root in allowed_roots if root is not None]
        if not allowed_roots:
            return False
        for root in allowed_roots:
            if self._same_or_descendant(candidate_path, root):
                return True
        return False

    def _safe_path(self, value: str) -> Path | None:
        try:
            return Path(value).expanduser().resolve(strict=False)
        except Exception:
            return None

    def _same_or_descendant(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return path == root

