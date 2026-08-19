"""Bounded JSON repair and standard-library JSON Schema subset validation."""

from __future__ import annotations

import json
import re
from typing import Any

from .errors import InvalidRequestError


STRUCTURED_OUTPUT_VERSION = "1.0"


def validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "null": type(None),
    }
    if expected in type_map:
        wanted = type_map[expected]
        valid = isinstance(value, wanted)
        if expected in {"number", "integer"} and isinstance(value, bool):
            valid = False
        if not valid:
            return [f"{path} must be {expected}."]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} must be one of {schema['enum']!r}.")
    if isinstance(value, dict):
        for required in schema.get("required") or []:
            if required not in value:
                errors.append(f"{path}.{required} is required.")
        properties = schema.get("properties") or {}
        for name, child in value.items():
            if name in properties:
                errors.extend(validate_json_schema(child, properties[name], f"{path}.{name}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{name} is not allowed.")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            errors.append(f"{path} must contain at least {schema['minItems']} items.")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            errors.append(f"{path} must contain at most {schema['maxItems']} items.")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                errors.extend(validate_json_schema(item, schema["items"], f"{path}[{index}]"))
    return errors


def parse_structured_output(text: str, response_format: dict[str, Any], *, repair_attempts: int = 1) -> Any:
    format_type = str(response_format.get("type") or "").strip()
    if format_type not in {"json_object", "json_schema"}:
        raise InvalidRequestError(f"Unsupported response_format type {format_type!r}.", param="response_format")
    candidate = str(text or "").strip()
    last_error = "empty output"
    for attempt in range(max(0, repair_attempts) + 1):
        try:
            value = json.loads(candidate)
            if not isinstance(value, dict):
                raise ValueError("Structured output must be a JSON object.")
            if format_type == "json_schema":
                wrapper = response_format.get("json_schema") or {}
                schema = wrapper.get("schema") if isinstance(wrapper, dict) else None
                if not isinstance(schema, dict):
                    raise InvalidRequestError("json_schema.schema must be an object.", param="response_format")
                errors = validate_json_schema(value, schema)
                if errors:
                    raise ValueError(" ".join(errors))
            return value
        except json.JSONDecodeError as exc:
            last_error = str(exc)
        except ValueError as exc:
            last_error = str(exc)
        if attempt < repair_attempts:
            candidate = _minor_json_repair(candidate)
    raise InvalidRequestError(f"Nova could not produce valid structured output: {last_error}", param="response_format")


def _minor_json_repair(text: str) -> str:
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        value = value[start : end + 1]
    value = re.sub(r",\s*([}\]])", r"\1", value)
    return value

