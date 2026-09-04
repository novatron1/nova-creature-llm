"""
Nova Entity Memory
==================

Small deterministic entity-memory layer for facts about people/things connected
to the user. This intentionally stays simple: parse a short natural-language
fact, store it in MEMORY["entities"], and recall the same slot later.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


ENTITY_ALIASES = {
    "brother": ("brother", "bro"),
    "sister": ("sister", "sis"),
    "mother": ("mother", "mom", "mama"),
    "father": ("father", "dad", "daddy"),
    "parent": ("parent",),
    "son": ("son",),
    "daughter": ("daughter",),
    "cousin": ("cousin",),
    "uncle": ("uncle",),
    "aunt": ("aunt", "aunty"),
    "boss": ("boss", "manager"),
    "teacher": ("teacher", "professor", "instructor"),
    "doctor": ("doctor",),
    "coworker": ("coworker", "co worker", "co-worker"),
    "neighbor": ("neighbor", "neighbour"),
    "roommate": ("roommate", "room mate"),
    "boyfriend": ("boyfriend", "boy friend", "bf"),
    "partner": ("partner",),
}

ENTITY_LABELS = {
    "brother": "brother",
    "sister": "sister",
    "mother": "mom",
    "father": "dad",
    "parent": "parent",
    "son": "son",
    "daughter": "daughter",
    "cousin": "cousin",
    "uncle": "uncle",
    "aunt": "aunt",
    "boss": "boss",
    "teacher": "teacher",
    "doctor": "doctor",
    "coworker": "coworker",
    "neighbor": "neighbor",
    "roommate": "roommate",
    "boyfriend": "boyfriend",
    "partner": "partner",
}

SLOT_ALIASES = {
    "name": ("name",),
    "favorite_color": ("favorite color", "favourite color"),
    "favorite_food": ("favorite food", "favourite food"),
    "favorite_drink": ("favorite drink", "favourite drink"),
    "birthday": ("birthday", "birth date"),
    "age": ("age",),
    "location": ("location", "address", "city"),
    "phone": ("phone", "phone number"),
    "email": ("email", "email address"),
    "job": ("job", "work", "workplace"),
}

SLOT_LABELS = {
    "name": "name",
    "favorite_color": "favorite color",
    "favorite_food": "favorite food",
    "favorite_drink": "favorite drink",
    "birthday": "birthday",
    "age": "age",
    "location": "location",
    "phone": "phone number",
    "email": "email",
    "job": "job",
}


def _clean_value(value: str) -> str:
    value = str(value or "").strip().strip("\"'“”‘’ ")
    value = re.split(r"[.?!\n\r]", value, maxsplit=1)[0].strip().strip("\"'“”‘’ ")
    value = re.split(
        r"\s+(?:and then|but then|because|so then)\s+",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    return value[:120].strip().strip(",;:")


def _normalize_text(text: str) -> str:
    text = str(text or "").replace("’", "'").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _alt(phrases: list[str] | tuple[str, ...]) -> str:
    return "|".join(re.escape(phrase).replace(r"\ ", r"\s+") for phrase in phrases)


ENTITY_ALT = _alt(tuple(alias for aliases in ENTITY_ALIASES.values() for alias in aliases))
SLOT_ALT = _alt(tuple(alias for aliases in SLOT_ALIASES.values() for alias in aliases))


def _entity_from_alias(alias: str) -> tuple[str, str] | None:
    alias_norm = re.sub(r"\s+", " ", str(alias or "").lower().replace("-", " ")).strip()
    for entity_key, aliases in ENTITY_ALIASES.items():
        normalized_aliases = {
            re.sub(r"\s+", " ", item.lower().replace("-", " ")).strip()
            for item in aliases
        }
        if alias_norm in normalized_aliases:
            return entity_key, ENTITY_LABELS.get(entity_key, entity_key.replace("_", " "))
    return None


def _slot_from_alias(alias: str) -> tuple[str, str] | None:
    alias_norm = re.sub(r"\s+", " ", str(alias or "").lower()).strip()
    for slot, aliases in SLOT_ALIASES.items():
        if alias_norm in aliases:
            return slot, SLOT_LABELS.get(slot, slot.replace("_", " "))
    return None


def parse_entity_save(text: str) -> dict[str, str] | None:
    raw = _normalize_text(text)
    patterns = [
        rf"\bmy\s+(?P<entity>{ENTITY_ALT})(?:'s)?\s+(?P<slot>{SLOT_ALT})\s+(?:is|was)\s+(?P<value>.+)$",
        rf"\bmy\s+(?P<entity>{ENTITY_ALT})\s+(?:is|was)\s+named\s+(?P<value>.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if not match:
            continue
        entity = _entity_from_alias(match.group("entity"))
        if not entity:
            continue
        if "slot" in match.groupdict() and match.group("slot"):
            slot = _slot_from_alias(match.group("slot"))
        else:
            slot = ("name", "name")
        value = _clean_value(match.group("value"))
        if slot and value:
            return {
                "action": "save",
                "entity_key": entity[0],
                "entity_label": entity[1],
                "slot": slot[0],
                "slot_label": slot[1],
                "value": value,
            }
    return None


def parse_entity_recall(text: str) -> dict[str, str] | None:
    raw = _normalize_text(text)
    patterns = [
        rf"\b(?:what|what's|whats|tell me|remember|recall)\s+(?:is|was)?\s*my\s+(?P<entity>{ENTITY_ALT})(?:'s)?\s+(?P<slot>{SLOT_ALT})\??$",
        rf"\bwho\s+(?:is|was)\s+my\s+(?P<entity>{ENTITY_ALT})\??$",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if not match:
            continue
        entity = _entity_from_alias(match.group("entity"))
        if not entity:
            continue
        if "slot" in match.groupdict() and match.group("slot"):
            slot = _slot_from_alias(match.group("slot"))
        else:
            slot = ("name", "name")
        if slot:
            return {
                "action": "recall",
                "entity_key": entity[0],
                "entity_label": entity[1],
                "slot": slot[0],
                "slot_label": slot[1],
            }
    return None


def parse_entity_memory_request(text: str) -> dict[str, str] | None:
    return parse_entity_save(text) or parse_entity_recall(text)


def save_entity_fact(
    memory: dict[str, Any],
    entity_key: str,
    entity_label: str,
    slot: str,
    slot_label: str,
    value: str,
    session_id: str = "",
) -> dict[str, Any]:
    entities = memory.setdefault("entities", {})
    entity = entities.setdefault(
        entity_key,
        {
            "entity_key": entity_key,
            "label": entity_label,
            "kind": "user_connected_entity",
            "slots": {},
            "created_at": datetime.now().isoformat(),
        },
    )
    entity["label"] = entity_label
    entity.setdefault("slots", {})
    entity["slots"][slot] = {
        "value": value,
        "slot": slot,
        "slot_label": slot_label,
        "updated_at": datetime.now().isoformat(),
        "session": session_id,
    }
    entity["updated_at"] = datetime.now().isoformat()
    if slot == "name":
        entity["name"] = value
    return entity


def recall_entity_fact(
    memory: dict[str, Any],
    entity_key: str,
    slot: str,
) -> dict[str, Any] | None:
    entity = memory.get("entities", {}).get(entity_key, {})
    slot_record = entity.get("slots", {}).get(slot)
    if not slot_record:
        return None
    value = _clean_value(slot_record.get("value", ""))
    if not value:
        return None
    return {
        "entity_key": entity_key,
        "entity_label": entity.get("label", ENTITY_LABELS.get(entity_key, entity_key)),
        "slot": slot,
        "slot_label": slot_record.get("slot_label", SLOT_LABELS.get(slot, slot.replace("_", " "))),
        "value": value,
    }


def format_save_response(entity_label: str, slot_label: str, value: str) -> str:
    return f"Got it — your {entity_label}'s {slot_label} is {value}."


def format_recall_response(entity_label: str, slot_label: str, value: str) -> str:
    return f"Your {entity_label}'s {slot_label} is {value}."


def format_missing_response(entity_label: str, slot_label: str) -> str:
    return (
        f"I don't have your {entity_label}'s {slot_label} saved yet. "
        f"Tell me: 'my {entity_label} {slot_label} is ...'"
    )
