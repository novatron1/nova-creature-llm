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

        if action_signature.arguments_hash != sha256_json(arguments):
            return PermissionDecision(
                disposition="BLOCK", rule_id="APPROVAL_SIGNATURE_CHANGED",
                message="The arguments do not match the approved action signature.",
                can_continue=False, rollback_available=False,
            )

        if any(not self._is_within_allowed_roots(path) for path in self._extract_paths(arguments)):
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

    def _extract_paths(self, arguments: dict[str, Any]) -> list[str]:
        """Inspect all recognized path fields, including batched/nested operations."""
        paths: list[str] = []
        path_keys = {"path", "file_path", "destination", "target", "source", "root",
                     "paths", "file_paths", "destinations", "targets", "sources", "roots", "cwd"}

        def visit(value: Any, is_path: bool = False) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, key in path_keys)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    visit(child, is_path)
            elif is_path and isinstance(value, str) and value.strip():
                paths.append(value)

        visit(arguments)
        return paths

    def _is_within_allowed_roots(self, candidate: str) -> bool:
        candidate_value = Path(candidate).expanduser()
        if not candidate_value.is_absolute():
            candidate_value = Path(self.contract.workspace_root) / candidate_value
        candidate_path = self._safe_path(str(candidate_value))
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

