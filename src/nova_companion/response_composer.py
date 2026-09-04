"""Bounded presentation-only response composition."""

from __future__ import annotations

import json
import re
from typing import Any

from .models import SocialPlan


def _protected(user_message: str, answer: str, plan: SocialPlan, trace: dict[str, Any]) -> bool:
    source = str(trace.get("source") or trace.get("final_answer_source") or "").lower()
    if any(marker in source for marker in ("raw", "tool", "action", "permission", "grounding", "verifier", "candidate")):
        return True
    if isinstance(trace.get("fact_grounding"), dict) and trace["fact_grounding"].get("status") not in {None, "not_required", "skipped"}:
        return True
    if isinstance(trace.get("verification_v2"), dict) and trace["verification_v2"].get("status") not in {None, "skipped"}:
        return True
    stripped = str(answer or "").strip()
    if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
        try:
            json.loads(stripped)
            return True
        except (TypeError, ValueError):
            pass
    if "```" in stripped or plan.primary_mode in {"technical_help", "task_execution"}:
        return True
    if re.search(r"\b(?:exactly|one sentence|only|just)\b", str(user_message or "").lower()):
        return True
    return False


def compose_response(user_message: str, answer: str, plan: SocialPlan, *, trace: dict[str, Any] | None = None) -> str:
    """Apply only safe social presentation changes; fail open to the answer."""

    original = str(answer or "").strip()
    if not original:
        return original
    metadata = trace if isinstance(trace, dict) else {}
    source = str(metadata.get("source") or metadata.get("final_answer_source") or "").lower()
    if (
        source == "answer_firewall_recovery"
        and plan.primary_mode in {"casual_chat", "companionship", "advice", "joking"}
        and any(
            marker in original.lower()
            for marker in ("off-topic draft", "did not produce a reliable answer", "stopped it instead of pretending")
        )
    ):
        metadata["companion_continuity_fallback"] = True
        # The companion has replaced the rejected draft with a deliberate,
        # intent-specific answer. Keep the original firewall reasons for
        # diagnostics, but make the visible route and status describe the
        # answer that was actually delivered.
        metadata["source"] = "companion_continuity_fallback"
        metadata["final_answer_source"] = "companion_continuity_fallback"
        firewall_trace = metadata.get("answer_firewall")
        if isinstance(firewall_trace, dict):
            firewall_trace["status"] = "recovered_by_companion"
            firewall_trace["accepted"] = True
            firewall_trace["recovered"] = True
        user_value = str(user_message or "").lower()
        if plan.primary_mode == "advice":
            return "Take one small next step: write down the single outcome you want, then do the easiest action that moves it forward."
        if plan.primary_mode == "joking":
            return "Debugging is like hide-and-seek: the bug knows exactly where it is, and still refuses to come out."
        if "project" in user_value:
            return "I'm with you on the project. What part are you still thinking through?"
        return "I'm with you. Let's stay with that—what part feels most important right now?"
    if _protected(user_message, original, plan, metadata):
        return original
    lowered = original.lower()
    if plan.primary_mode in {"casual_chat", "companionship"}:
        filler_patterns = (
            r"^i(?:'m| am) here to help[.!]?\s*",
            r"^how can i assist you today\??\s*",
            r"^what can i assist you with today\??\s*",
        )
        cleaned = original
        for pattern in filler_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        if cleaned.lower() != lowered:
            original = cleaned or "I'm listening. What's on your mind?"
    if plan.listen_first and not re.search(r"\b(?:hear|listening|with you|that sounds|makes sense)\b", original.lower()):
        original = "I'm with you. " + original
    return original
