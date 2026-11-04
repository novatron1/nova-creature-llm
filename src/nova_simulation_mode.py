"""Deterministic dry-run conversation responses for Nova's local simulator."""

from __future__ import annotations

import hashlib
import re
from typing import Any


SIMULATION_VERSION = "1.0"


def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _history_messages(context: dict[str, Any]) -> list[dict[str, str]]:
    raw = context.get("conversation_history")
    if not isinstance(raw, list):
        return []
    messages: list[dict[str, str]] = []
    for item in raw[-20:]:
        if not isinstance(item, dict):
            continue
        role = _normalise(item.get("role")).lower()
        content = _normalise(item.get("content"))
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:4000]})
    return messages


def _name_from_text(value: str) -> str | None:
    match = re.search(
        r"\b(?:my\s+name\s+is|call\s+me)\s+([A-Za-z][A-Za-z .'-]{1,60})",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    name = re.sub(r"[.!?,;:]+$", "", match.group(1)).strip(" .,-")
    if not name or len(name) > 60:
        return None
    return name


def _domain_for(prompt: str) -> str:
    lowered = prompt.lower()
    if re.search(r"\b(?:is\s+it\s+true|true\s+that|really|fact|verify|verified|latest|current|evidence|source)\b", lowered):
        return "truth_check"
    if re.search(r"\b(?:simulation|simulate|dry\s*run|test\s+mode)\b", lowered):
        return "simulation"
    if _name_from_text(prompt) or re.search(r"\b(?:what(?:'s| is)\s+my\s+name|who\s+am\s+i)\b", lowered):
        return "identity"
    if re.search(r"\b(?:joke|funny|silly|make\s+me\s+laugh|sillier)\b", lowered):
        return "humor"
    if re.search(r"\b(?:how\s*(?:-|\s)\s*to|how\s+do\s+i|how\s+can\s+i|steps?\s+to|walk\s+me\s+through)\b", lowered):
        return "how_to"
    if re.search(r"\b(?:advice|advise|what\s+should\s+i|recommend|suggestion|help\s+me\s+decide)\b", lowered):
        return "advice"
    if re.search(r"\bwhy\b", lowered):
        return "why"
    if re.search(r"\bwhat\s+about\b", lowered):
        return "what_about"
    return "general_conversation"


def _base_trace(prompt: str, domain: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "simulation_mode",
        "final_answer_source": "simulation_mode",
        "simulation_mode": True,
        "simulation_version": SIMULATION_VERSION,
        "domain": domain,
        "roles": ["simulation_router", "speech_output_transformer"],
        "skills": ["bounded_dry_run", "conversation_shape_matching"],
        "route_path": ["nova_core", "simulation_mode", "speech_output"],
        "confidence": 0.97,
        "local_llm_synthesis_used": False,
        "memory_write_used": False,
        "memory_read_used": False,
        "actions_executed": False,
        "model_called": False,
        "prompt_content_logged": False,
        "conversation_id": _normalise(context.get("conversation_id")) or "default",
    }


def build_simulation_response(text: str, context: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Return a useful, fully local response without models, tools, or memory writes."""

    context = context if isinstance(context, dict) else {}
    prompt = _normalise(text)
    domain = _domain_for(prompt)
    trace = _base_trace(prompt, domain, context)
    history = _history_messages(context)

    name = _name_from_text(prompt)
    if name:
        response = (
            f"Simulation mode: Hi, {name}. I will use that name only inside this dry-run "
            "conversation; no long-term memory was changed."
        )
        trace["identity_name_captured"] = True
    elif domain == "identity":
        remembered_name = next(
            (_name_from_text(item["content"]) for item in reversed(history) if item["role"] == "user"),
            None,
        )
        response = (
            f"Simulation mode: the name in this test conversation is {remembered_name}."
            if remembered_name
            else "Simulation mode: I do not have a name for you in this dry-run conversation yet."
        )
        trace["identity_name_captured"] = bool(remembered_name)
    elif domain == "simulation":
        response = (
            "Simulation mode is active. This is a dry run: no model, tool, memory, file, "
            "or external action is used. I can exercise general conversation, advice, how-to, "
            "why, what-about, and truth-check replies here."
        )
    elif domain == "truth_check":
        response = (
            "Simulation truth check: yes, this mode is designed to make no model, tool, memory, "
            "file, or external change. It cannot verify unrelated live facts, so treat current "
            "claims as unverified until Nova checks a current source outside the dry run."
        )
    elif domain == "humor":
        response = (
            "Simulation punchline: the judging refrigerator quit the talent show because it "
            "could not handle the cold feedback. Beep-boop, tough crowd."
        )
    elif domain == "how_to":
        response = (
            "Simulation how-to: 1. Define the outcome. 2. Do the smallest safe step. "
            "3. Check the result. 4. Adjust one variable and repeat."
        )
    elif domain == "advice":
        response = (
            "Simulation advice: clarify the goal, choose one next step you can finish today, "
            "and keep a reversible fallback. Momentum beats a perfect first draft."
        )
    elif domain == "why":
        response = (
            "Simulation why-check: starting small reduces the number of unknowns, makes failures "
            "easier to diagnose, and gives you a working result to improve. That is a general "
            "reason, not a verified claim about a specific project."
        )
    elif domain == "what_about":
        response = (
            "Simulation tradeoff: consider the benefit, cost, risk, and reversibility of that idea. "
            "Try it as a small experiment before making it part of the core plan."
        )
    else:
        response = (
            "Simulation reply: I hear you. I can keep the conversation practical, curious, and "
            "inside this dry run. Tell me what you are thinking about next."
        )

    trace["response_length"] = len(response)
    return response, trace


def _funny_enabled(text: str, context: dict[str, Any]) -> bool:
    personality = _normalise(context.get("personality")).lower()
    return bool(
        context.get("funny_personality") is True
        or personality in {"funny", "playful", "witty"}
        or re.search(r"\b(?:be\s+funny|funny\s+personality|make\s+it\s+funny)\b", text, re.I)
    )


def maybe_add_funny_aside(
    response: str,
    text: str,
    context: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Add an occasional short aside without changing serious or truth-oriented answers."""

    context = context if isinstance(context, dict) else {}
    prompt = _normalise(text)
    result = _normalise(response)
    trace: dict[str, Any] = {
        "enabled": False,
        "applied": False,
        "mode": "bounded_occasional_aside",
        "content_logged": False,
    }
    if not _funny_enabled(prompt, context):
        trace["reason"] = "not_enabled"
        return result, trace
    trace["enabled"] = True
    lowered = prompt.lower()
    if re.search(r"\b(?:joke|funny|silly|sillier|make\s+me\s+laugh)\b", lowered):
        trace["reason"] = "explicit_humor_request"
        return result, trace
    if re.search(
        r"\b(?:is\s+it\s+true|true|verify|verified|evidence|source|current|latest|medical|legal|danger|unsafe|emergency|grief)\b",
        lowered,
    ):
        trace["reason"] = "serious_or_truth_check"
        return result, trace
    digest = hashlib.sha256(
        f"{_normalise(context.get('conversation_id'))}|{prompt}".encode("utf-8")
    ).digest()
    if digest[0] % 3:
        trace["reason"] = "occasional_sampling"
        return result, trace
    asides = (
        "Playful Nova aside: I put a tiny cape on that plan.",
        "Playful Nova aside: Even the checklist gets a checklist around here.",
        "Playful Nova aside: My internal clipboard approves this move.",
        "Playful Nova aside: The imaginary studio audience gives that a polite beep.",
    )
    aside = asides[digest[1] % len(asides)]
    trace.update({"applied": True, "reason": "occasional_sampling", "aside": aside})
    return f"{result}\n\n{aside}", trace
