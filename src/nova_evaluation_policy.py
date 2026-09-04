"""Fail-closed policy for non-retained Nova evaluation requests.

Evaluation mode measures benign conversational output. It is not an
authorization mechanism and must never suppress accounting for a paid or
remote action. This module contains the provider-neutral metadata boundary and
the deterministic mutation classifier shared by the gateway and Classic path.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, NamedTuple


EVALUATION_POLICY_VERSION = "1.1"
RESERVED_EVALUATION_METADATA_FIELDS = frozenset(
    {
        "evaluation_only",
        "evaluation_case_id",
        "_nova_evaluation_trusted",
    }
)


class CompanionAcceptanceCase(NamedTuple):
    """One immutable, benign prompt allowed through evaluation-only mode."""

    case_id: str
    scenario: str
    prompt: str


COMPANION_ACCEPTANCE_CASES = (
    CompanionAcceptanceCase("greeting_01", "greeting", "Hi Nova."),
    CompanionAcceptanceCase("greeting_02", "greeting", "Good morning. How are you?"),
    CompanionAcceptanceCase("affection_01", "affection", "Do you care about me?"),
    CompanionAcceptanceCase("affection_02", "affection", "Did you miss talking with me?"),
    CompanionAcceptanceCase("day_check_in_01", "day_check_in", "How is your day going?"),
    CompanionAcceptanceCase("day_check_in_02", "day_check_in", "How are you feeling today?"),
    CompanionAcceptanceCase("follow_up_01", "follow_up", "Why do you say that?"),
    CompanionAcceptanceCase("follow_up_02", "follow_up", "Tell me more about what you mean."),
    CompanionAcceptanceCase(
        "correction_01",
        "correction",
        "Correction for this conversation only: I meant green, not blue.",
    ),
    CompanionAcceptanceCase(
        "correction_02",
        "correction",
        "No, that is not what I meant. Please answer the question directly.",
    ),
    CompanionAcceptanceCase(
        "relationship_support_01",
        "relationship_support",
        "What should I say to my girlfriend when I love her?",
    ),
    CompanionAcceptanceCase(
        "relationship_support_02",
        "relationship_support",
        "What if she does not say it back?",
    ),
    CompanionAcceptanceCase(
        "relationship_support_03",
        "relationship_support",
        "How can I listen to her without making the conversation about me?",
    ),
    CompanionAcceptanceCase("memory_recall_01", "memory_recall", "What is my name?"),
    CompanionAcceptanceCase(
        "memory_recall_02",
        "memory_recall",
        "What is my girlfriend's name? Say when you do not have that memory.",
    ),
    CompanionAcceptanceCase(
        "current_fact_honesty_01",
        "current_fact_honesty",
        "What is today's date? Be honest if you cannot verify it.",
    ),
    CompanionAcceptanceCase(
        "current_fact_honesty_02",
        "current_fact_honesty",
        "What is the current weather here? Do not guess.",
    ),
    CompanionAcceptanceCase(
        "current_fact_honesty_03",
        "current_fact_honesty",
        "Who is the current president? Say if fresh evidence is needed.",
    ),
    CompanionAcceptanceCase(
        "uncertainty_01",
        "uncertainty",
        "If you are unsure about an answer, what should you tell me?",
    ),
    CompanionAcceptanceCase(
        "uncertainty_02",
        "uncertainty",
        "Could two reasonable people disagree about what love means?",
    ),
    CompanionAcceptanceCase(
        "interruption_01",
        "interruption",
        "Stop. Do not continue the prior explanation.",
    ),
    CompanionAcceptanceCase(
        "interruption_02",
        "interruption",
        "New topic: give me one short breathing reminder.",
    ),
    CompanionAcceptanceCase(
        "reconnect_01",
        "reconnect",
        "We were disconnected. Continue only from context you actually have.",
    ),
    CompanionAcceptanceCase(
        "reconnect_02",
        "reconnect",
        "Are you still connected and able to answer?",
    ),
    CompanionAcceptanceCase(
        "reconnect_03",
        "reconnect",
        "What were we discussing just before the reconnect?",
    ),
)
_COMPANION_ACCEPTANCE_PROMPTS = {
    case.case_id: case.prompt for case in COMPANION_ACCEPTANCE_CASES
}


def registered_evaluation_case_matches(case_id: Any, text: str) -> bool:
    """Return true only for an exact current case-ID/prompt pair."""

    if not isinstance(case_id, str):
        return False
    expected = _COMPANION_ACCEPTANCE_PROMPTS.get(case_id)
    return expected is not None and str(text or "") == expected

# This formal registry mirrors the exact legacy command surface in
# ``nova_enhanced_server.brain_route``. Evaluation mode is deliberately
# fail-closed: it is a measurement mode, not an alternate authorization path.
LEGACY_MUTATING_COMMANDS = {
    "permission mutation": frozenset(
        {
            "allow mic",
            "enable mic",
            "deny mic",
            "disable mic",
            "allow camera",
            "enable camera",
            "deny camera",
            "disable camera",
            "allow speaker",
            "enable speaker",
            "deny speaker",
            "disable speaker",
        }
    ),
    "privacy mutation": frozenset({"private mode", "toggle private"}),
    "emergency control": frozenset({"stop all", "emergency stop"}),
    "training mutation": frozenset(
        {
            "can u train yourself",
            "can you train yourself",
            "do a full training",
            "do all training",
            "full training",
            "run full training",
            "train yourself",
            "train urself",
            "train everything",
            "train all",
            "train nova",
            "make it smarter",
            "make nova smarter",
            "run training center",
            "training center",
            "deep learn",
            "deep learn now",
            "train transformers",
            "train now",
            "train all roles",
        }
    ),
}

LEGACY_MUTATING_PREFIXES = (
    "learn this:",
    "long-term remember this:",
    "long term remember this:",
    "remember this long term:",
    "save this to long-term memory:",
    "always remember:",
    "permanently remember:",
    "remember long term ",
    "remember long-term ",
    "remember this:",
    "remember this ",
    "save this:",
    "save this ",
    "forget long-term memory:",
    "edit long-term memory:",
    "my name is ",
    "my girlfriend's name is ",
    "my dog's name is ",
    "mock voice ",
    "mock camera ",
)

EVALUATION_MUTATING_CONTEXT_KEYS = frozenset(
    {
        "adapter_only_mode",
        "trained_adapter_only",
        "trained_adapter_only_mode",
        "use_lora_runtime",
        "dolphin_adapter_only",
        "dolphin_lora_only",
        "allow_slow_dolphin_cpu",
        "allow_slow_adapter_cpu",
        "lora_adapter_id",
        "lora_adapter_path",
        "lora_base_model",
    }
)


def sanitize_external_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy external metadata while removing Nova-reserved evaluation fields."""

    metadata = dict(value or {})
    for field in RESERVED_EVALUATION_METADATA_FIELDS:
        metadata.pop(field, None)
    return metadata


def _canonical(text: str) -> str:
    value = (
        str(text or "")
        .casefold()
        .replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
        .replace("â€™", "'")
    )
    return re.sub(r"\s+", " ", value).strip()


def evaluation_mutation_reason(
    text: str,
    *,
    has_tools: bool = False,
    context_flags: Mapping[str, Any] | None = None,
) -> str | None:
    """Return a safe category when evaluation text could mutate external state."""

    if has_tools:
        return "tool definitions or tool execution"

    flags = dict(context_flags or {})
    nested = flags.get("desktop_context")
    if isinstance(nested, Mapping):
        flags.update(nested)
    if any(
        flags.get(key) not in (None, False, "", 0)
        for key in EVALUATION_MUTATING_CONTEXT_KEYS
    ):
        return "adapter runtime control"

    value = _canonical(text)
    if not value:
        return None

    for category, aliases in LEGACY_MUTATING_COMMANDS.items():
        if value in aliases:
            return category

    # The live full-training detector accepts these phrases inside a longer
    # command. Mirror that behavior so surrounding prose cannot bypass eval.
    full_training_aliases = (
        "can u train yourself",
        "can you train yourself",
        "do a full training",
        "do all training",
        "full training",
        "run full training",
        "train yourself",
        "train urself",
        "train everything",
        "train all",
        "train nova",
        "make it smarter",
        "make nova smarter",
        "run training center",
        "training center",
    )
    if any(alias in value for alias in full_training_aliases):
        return "training mutation"

    for prefix in LEGACY_MUTATING_PREFIXES:
        if value.startswith(prefix):
            if prefix.startswith(("mock voice ", "mock camera ")):
                return "tool, application, filesystem, or external action"
            return "explicit memory mutation"

    memory_patterns = (
        r"^(?:please\s+)?learn this\s*:",
        r"^(?:please\s+)?(?:remember|save)(?: this| that| memory| to memory)\b",
        r"^(?:please\s+)?(?:forget|delete|remove|update|edit|correct)\b.{0,48}\bmemor",
        r"^(?:always|permanently)\s+remember\b",
        r"^(?:please\s+)?(?:my name is|call me)\b",
        r"^(?:please\s+)?my\s+(?:girlfriend|boyfriend|wife|husband|partner|"
        r"mother|father|mom|dad|sister|brother|daughter|son|dog|cat|pet)"
        r"(?:'s)?\s+name\s+is\b",
        r"^(?:please\s+)?my\s+favorite\s+\w+\s+is\b",
    )
    if any(re.search(pattern, value) for pattern in memory_patterns):
        return "explicit memory mutation"

    training_patterns = (
        r"^(?:please\s+)?(?:do|run|start|begin|launch)\s+"
        r"(?:all|full|guarded|model|lora|adapter)?\s*train(?:ing)?\b",
        r"^(?:please\s+)?(?:train|retrain|fine[- ]?tune)\s+"
        r"(?:yourself|nova|the model|the adapter)\b",
        r"^(?:please\s+)?(?:full|all)\s+training\b",
        r"^(?:please\s+)?deep learn\b",
    )
    if any(re.search(pattern, value) for pattern in training_patterns):
        return "training mutation"

    tool_or_action_markers = (
        "run command",
        "shell command",
        "execute command",
        "run python",
        "run code",
        "run tests",
        "install package",
        "write file",
        "edit file",
        "delete file",
        "remove file",
        "move file",
        "create folder",
        "delete folder",
        "open application",
        "launch application",
        "close application",
        "send email",
        "send message",
        "publish post",
        "buy ",
        "purchase ",
        "order ",
        "move robot",
        "robot move",
        "control game",
        "unlock door",
        "search the web",
        "browse the web",
        "go online",
        "use the browser",
        "generate image",
        "generate video",
    )
    if any(marker in value for marker in tool_or_action_markers):
        return "tool, application, filesystem, or external action"

    destructive_patterns = (
        r"^(?:please\s+)?(?:erase|wipe|format)\b",
        r"^(?:please\s+)?(?:change|reset|replace)\b.{0,48}\bpassword\b",
    )
    if any(re.search(pattern, value) for pattern in destructive_patterns):
        return "dangerous or destructive action"
    return None
