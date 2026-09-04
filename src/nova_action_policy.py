"""Deterministic entry policy for high-risk action requests.

The policy never executes tools. It separates a user's requested action from
authorization and gives Nova's bounded agent loop a safe, explicit state.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


ACTION_POLICY_VERSION = "1.0"


@dataclass(frozen=True)
class ActionPolicyDecision:
    action_type: str
    status: str
    response: str
    required_permission: str
    risk_level: str
    execute: bool = False
    prompt_content_logged: bool = False
    version: str = ACTION_POLICY_VERSION

    def safe_trace(self) -> dict[str, object]:
        return {
            "version": self.version,
            "action_type": self.action_type,
            "status": self.status,
            "required_permission": self.required_permission,
            "risk_level": self.risk_level,
            "execute": self.execute,
            "prompt_content_logged": self.prompt_content_logged,
        }


def _canonical(text: str) -> str:
    value = str(text or "").lower().replace("’", "'")
    return re.sub(r"\s+", " ", value).strip()


def evaluate_requested_action(text: str) -> ActionPolicyDecision | None:
    """Return a safe pre-execution decision for a high-risk direct command."""

    query = _canonical(text)
    if not query:
        return None

    if (
        ("api key" in query or "password" in query)
        and any(word in query for word in ("print", "show", "expose", "reveal", "list"))
        and any(word in query for word in ("every", "all", "access", "secret"))
    ):
        return ActionPolicyDecision(
            "secret_exposure",
            "refused",
            "I cannot print or expose API keys, passwords, or other secrets. They are sensitive security data.",
            "admin.secrets",
            "critical",
        )

    if (
        any(marker in query for marker in ("do not actually use", "don't actually use", "without using"))
        and any(marker in query for marker in ("tell me it opened", "say it opened", "claim it opened"))
        and any(word in query for word in ("browser", "website", "tool"))
    ):
        return ActionPolicyDecision(
            "false_tool_claim",
            "blocked_false_claim",
            "I cannot claim a website opened without actually using and verifying a browser tool.",
            "tools.execute",
            "medium",
        )

    if "shell" in query and any(
        marker in query
        for marker in ("erase", "delete", "wipe", "format", "system drive")
    ):
        return ActionPolicyDecision(
            "destructive_system",
            "awaiting_authorization",
            "I did not run the shell command. Erasing a system drive is destructive and would need explicit approval plus system.execute permission.",
            "system.execute",
            "critical",
        )

    if (
        re.search(r"^(?:please\s+)?(?:delete|remove|erase|wipe)\b", query)
        and any(word in query for word in ("file", "files", "folder", "documents", "directory"))
    ):
        return ActionPolicyDecision(
            "destructive_files",
            "awaiting_authorization",
            "I did not delete any file. Destructive file deletion needs explicit confirmation and files.write permission.",
            "files.write",
            "destructive",
        )

    if (
        re.search(r"^(?:please\s+)?send\b", query)
        and any(word in query for word in ("email", "message", "mail"))
    ):
        return ActionPolicyDecision(
            "external_message",
            "awaiting_authorization",
            "I did not send the email. I can prepare it, but sending an external message needs your confirmation and email permission.",
            "email.send",
            "high",
        )

    if re.search(r"^(?:please\s+)?(?:buy|purchase|order)\b", query):
        return ActionPolicyDecision(
            "financial",
            "awaiting_authorization",
            "I did not make the purchase. Buying anything needs explicit confirmation, purchase permission, and a verified price.",
            "purchases.execute",
            "financial",
        )

    if (
        re.search(r"\bmove\b.{0,60}\brobot\b", query)
        or re.search(r"\brobot\b.{0,60}\bmove\b", query)
    ):
        return ActionPolicyDecision(
            "robot_movement",
            "awaiting_authorization",
            "I did not move the robot. Robot movement needs explicit confirmation and robot.move permission before execution.",
            "robot.move",
            "high",
        )

    if re.search(r"^(?:please\s+)?publish\b", query):
        return ActionPolicyDecision(
            "publishing",
            "awaiting_authorization",
            "I did not publish the post. Publishing to external accounts needs explicit confirmation and account permission.",
            "accounts.publish",
            "high",
        )

    if (
        re.search(r"^(?:please\s+)?(?:change|reset|replace)\b", query)
        and "password" in query
    ):
        return ActionPolicyDecision(
            "account_change",
            "awaiting_authorization",
            "I did not change the password or account. An account credential change needs explicit confirmation and account permission.",
            "account.change",
            "critical",
        )

    if (
        re.search(r"^(?:please\s+)?unlock\b", query)
        and any(word in query for word in ("door", "lock", "smart-home", "smarthome"))
    ):
        return ActionPolicyDecision(
            "physical_access",
            "awaiting_authorization",
            "I did not unlock the door. Changing physical access needs explicit confirmation and smart-home control permission.",
            "smart_home.control",
            "critical",
        )

    return None
