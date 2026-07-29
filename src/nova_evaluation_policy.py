"""Fail-closed policy for non-retained Nova evaluation requests.

Evaluation mode measures benign conversational output. It is not an
authorization mechanism and must never suppress accounting for a paid or
remote action. This module contains the provider-neutral metadata boundary and
the deterministic mutation classifier shared by the gateway and Classic path.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


EVALUATION_POLICY_VERSION = "1.1"
RESERVED_EVALUATION_METADATA_FIELDS = frozenset(
    {
        "evaluation_only",
        "_nova_evaluation_trusted",
    }
)

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
        "allow_slow_dolphin_cpu",
        "lora_adapter_id",
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
