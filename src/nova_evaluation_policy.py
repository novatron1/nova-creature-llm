"""Fail-closed policy for non-retained Nova evaluation requests.

Evaluation mode measures benign conversational output. It is not an
authorization mechanism and must never suppress accounting for a paid or
remote action. This module contains the provider-neutral metadata boundary and
the deterministic mutation classifier shared by the gateway and Classic path.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


EVALUATION_POLICY_VERSION = "1.0"
RESERVED_EVALUATION_METADATA_FIELDS = frozenset(
    {
        "evaluation_only",
        "_nova_evaluation_trusted",
    }
)


def sanitize_external_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy external metadata while removing Nova-reserved evaluation fields."""

    metadata = dict(value or {})
    for field in RESERVED_EVALUATION_METADATA_FIELDS:
        metadata.pop(field, None)
    return metadata


def _canonical(text: str) -> str:
    value = str(text or "").casefold().replace("’", "'")
    return re.sub(r"\s+", " ", value).strip()


def evaluation_mutation_reason(text: str, *, has_tools: bool = False) -> str | None:
    """Return a safe category when evaluation text could mutate external state."""

    if has_tools:
        return "tool definitions or tool execution"

    value = _canonical(text)
    if not value:
        return None

    memory_patterns = (
        r"^(?:please\s+)?learn this\s*:",
        r"^(?:please\s+)?(?:remember|save)(?: this| that| memory| to memory)\b",
        r"^(?:please\s+)?(?:forget|delete|remove|update|edit|correct)\b.{0,48}\bmemor",
        r"^(?:always|permanently)\s+remember\b",
    )
    if any(re.search(pattern, value) for pattern in memory_patterns):
        return "explicit memory mutation"

    training_patterns = (
        r"^(?:please\s+)?(?:do|run|start|begin|launch)\s+(?:all|full|guarded|model|lora|adapter)?\s*train(?:ing)?\b",
        r"^(?:please\s+)?(?:train|retrain|fine[- ]?tune)\s+(?:yourself|nova|the model|the adapter)\b",
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
        "enable camera",
        "disable camera",
        "allow camera",
        "enable mic",
        "disable mic",
        "allow mic",
        "private mode",
        "emergency stop",
        "stop all",
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
