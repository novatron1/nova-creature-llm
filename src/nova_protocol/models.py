"""Provider-neutral wire and core schemas for Nova Creature.

These dataclasses are deliberately independent from OpenAI, Ollama, Anthropic,
or any other provider vocabulary. External adapters translate to and from these
objects at the compatibility boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, ClassVar
import uuid


PROTOCOL_VERSION = "1.1"
API_VERSION = "nova/v1"
ALLOWED_MESSAGE_ROLES = {"system", "developer", "user", "assistant", "tool"}
ALLOWED_PRIVACY_MODES = {
    "local_only",
    "local_preferred",
    "balanced",
    "remote_allowed",
    "user_confirmation_required",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class ProtocolValidationError(ValueError):
    """A Nova protocol object failed safe validation."""


class Serializable:
    """Small JSON serialization mixin shared by protocol dataclasses."""

    schema_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


@dataclass
class NovaMessage(Serializable):
    role: str
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        self.role = str(self.role or "").strip().lower()
        if self.role not in ALLOWED_MESSAGE_ROLES:
            raise ProtocolValidationError(f"Unsupported Nova message role: {self.role!r}")
        if not isinstance(self.content, (str, list, dict)) and self.content is not None:
            raise ProtocolValidationError("Message content must be text, structured content, or null.")
        if self.name is not None:
            self.name = str(self.name)[:128]
        if self.tool_call_id is not None:
            self.tool_call_id = str(self.tool_call_id)[:160]
        if not isinstance(self.metadata, dict):
            raise ProtocolValidationError("Message metadata must be an object.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NovaMessage":
        if not isinstance(data, dict):
            raise ProtocolValidationError("Each message must be an object.")
        return cls(
            role=data.get("role", ""),
            content=data.get("content"),
            name=data.get("name"),
            tool_call_id=data.get("tool_call_id"),
            metadata=dict(data.get("metadata") or {}),
            schema_version=str(data.get("schema_version") or PROTOCOL_VERSION),
        )

    def text_content(self) -> str:
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, list):
            parts: list[str] = []
            for item in self.content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") in {"text", "input_text", "output_text"}:
                    parts.append(str(item.get("text") or ""))
            return "\n".join(part for part in parts if part)
        if isinstance(self.content, dict):
            return str(self.content.get("text") or "")
        return ""


@dataclass
class NovaAttachment(Serializable):
    attachment_id: str = field(default_factory=lambda: new_id("att"))
    media_type: str = "application/octet-stream"
    source_type: str = "reference"
    local_path: str | None = None
    url: str | None = None
    data: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = PROTOCOL_VERSION

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NovaAttachment":
        if not isinstance(data, dict):
            raise ProtocolValidationError("Each attachment must be an object.")
        return cls(
            attachment_id=str(data.get("attachment_id") or new_id("att")),
            media_type=str(data.get("media_type") or "application/octet-stream"),
            source_type=str(data.get("source_type") or "reference"),
            local_path=data.get("local_path"),
            url=data.get("url"),
            data=data.get("data"),
            metadata=dict(data.get("metadata") or {}),
            schema_version=str(data.get("schema_version") or PROTOCOL_VERSION),
        )


@dataclass
class NovaToolDefinition(Serializable):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        self.name = str(self.name or "").strip()
        if not self.name or len(self.name) > 128:
            raise ProtocolValidationError("Tool name must contain 1-128 characters.")
        if not isinstance(self.input_schema, dict):
            raise ProtocolValidationError("Tool input_schema must be an object.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NovaToolDefinition":
        if not isinstance(data, dict):
            raise ProtocolValidationError("Each tool must be an object.")
        return cls(
            name=data.get("name", ""),
            description=str(data.get("description") or ""),
            input_schema=dict(data.get("input_schema") or {"type": "object"}),
            metadata=dict(data.get("metadata") or {}),
            schema_version=str(data.get("schema_version") or PROTOCOL_VERSION),
        )


@dataclass
class NovaGenerationOptions(Serializable):
    model: str = "nova"
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None
    seed: int | None = None
    stream: bool = False
    response_format: dict[str, Any] | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        self.model = str(self.model or "nova").strip()
        if self.temperature is not None and not 0 <= float(self.temperature) <= 2:
            raise ProtocolValidationError("temperature must be between 0 and 2.")
        if self.top_p is not None and not 0 <= float(self.top_p) <= 1:
            raise ProtocolValidationError("top_p must be between 0 and 1.")
        if self.max_tokens is not None and not 1 <= int(self.max_tokens) <= 1_000_000:
            raise ProtocolValidationError("max_tokens must be a positive bounded integer.")
        if self.frequency_penalty is not None and not -2 <= float(self.frequency_penalty) <= 2:
            raise ProtocolValidationError("frequency_penalty must be between -2 and 2.")
        if self.presence_penalty is not None and not -2 <= float(self.presence_penalty) <= 2:
            raise ProtocolValidationError("presence_penalty must be between -2 and 2.")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NovaGenerationOptions":
        values = dict(data or {})
        return cls(
            model=values.get("model", "nova"),
            temperature=values.get("temperature"),
            top_p=values.get("top_p"),
            max_tokens=values.get("max_tokens"),
            stop=values.get("stop"),
            seed=values.get("seed"),
            stream=bool(values.get("stream", False)),
            response_format=values.get("response_format"),
            frequency_penalty=values.get("frequency_penalty"),
            presence_penalty=values.get("presence_penalty"),
            metadata=dict(values.get("metadata") or {}),
            schema_version=str(values.get("schema_version") or PROTOCOL_VERSION),
        )


@dataclass
class NovaRequest(Serializable):
    request_id: str = field(default_factory=lambda: new_id("req"))
    user_id: str = "local-user"
    client_id: str = "local-client"
    conversation_id: str = field(default_factory=lambda: new_id("conv"))
    session_id: str = field(default_factory=lambda: new_id("sess"))
    messages: list[NovaMessage] = field(default_factory=list)
    attachments: list[NovaAttachment] = field(default_factory=list)
    tools: list[NovaToolDefinition] = field(default_factory=list)
    tool_choice: Any = None
    generation_options: NovaGenerationOptions = field(default_factory=NovaGenerationOptions)
    requested_modalities: list[str] = field(default_factory=lambda: ["text"])
    privacy_mode: str = "local_preferred"
    metadata: dict[str, Any] = field(default_factory=dict)
    api_source: str = "nova_native"
    api_version: str = API_VERSION
    schema_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if not self.messages:
            raise ProtocolValidationError("NovaRequest requires at least one message.")
        if self.privacy_mode not in ALLOWED_PRIVACY_MODES:
            raise ProtocolValidationError(f"Unsupported privacy mode: {self.privacy_mode!r}")
        if not all(isinstance(item, NovaMessage) for item in self.messages):
            raise ProtocolValidationError("NovaRequest messages must be NovaMessage objects.")
        if not isinstance(self.metadata, dict):
            raise ProtocolValidationError("Request metadata must be an object.")
        self.request_id = str(self.request_id or new_id("req"))[:160]
        self.user_id = str(self.user_id or "anonymous")[:160]
        self.client_id = str(self.client_id or "unknown-client")[:160]
        self.conversation_id = str(self.conversation_id or new_id("conv"))[:160]
        self.session_id = str(self.session_id or new_id("sess"))[:160]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NovaRequest":
        if not isinstance(data, dict):
            raise ProtocolValidationError("Nova request body must be an object.")
        return cls(
            request_id=str(data.get("request_id") or new_id("req")),
            user_id=str(data.get("user_id") or "local-user"),
            client_id=str(data.get("client_id") or "local-client"),
            conversation_id=str(data.get("conversation_id") or new_id("conv")),
            session_id=str(data.get("session_id") or new_id("sess")),
            messages=[NovaMessage.from_dict(item) for item in data.get("messages") or []],
            attachments=[NovaAttachment.from_dict(item) for item in data.get("attachments") or []],
            tools=[NovaToolDefinition.from_dict(item) for item in data.get("tools") or []],
            tool_choice=data.get("tool_choice"),
            generation_options=NovaGenerationOptions.from_dict(data.get("generation_options")),
            requested_modalities=[str(item) for item in data.get("requested_modalities") or ["text"]],
            privacy_mode=str(data.get("privacy_mode") or "local_preferred"),
            metadata=dict(data.get("metadata") or {}),
            api_source=str(data.get("api_source") or "nova_native"),
            api_version=str(data.get("api_version") or API_VERSION),
            schema_version=str(data.get("schema_version") or PROTOCOL_VERSION),
        )

    def last_user_text(self) -> str:
        for message in reversed(self.messages):
            if message.role == "user":
                return message.text_content().strip()
        return ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class NovaToolCall(Serializable):
    tool_call_id: str = field(default_factory=lambda: new_id("call"))
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    status: str = "requested"
    result: Any = None
    error: str | None = None
    schema_version: str = PROTOCOL_VERSION

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NovaToolCall":
        return cls(
            tool_call_id=str(data.get("tool_call_id") or new_id("call")),
            name=str(data.get("name") or ""),
            arguments=dict(data.get("arguments") or {}),
            status=str(data.get("status") or "requested"),
            result=data.get("result"),
            error=data.get("error"),
            schema_version=str(data.get("schema_version") or PROTOCOL_VERSION),
        )


@dataclass
class NovaResponse(Serializable):
    response_id: str = field(default_factory=lambda: new_id("resp"))
    request_id: str = ""
    conversation_id: str = ""
    model: str = "nova"
    provider: str = "nova-core"
    content: str = ""
    finish_reason: str = "stop"
    tool_calls: list[NovaToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = PROTOCOL_VERSION

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NovaResponse":
        return cls(
            response_id=str(data.get("response_id") or new_id("resp")),
            request_id=str(data.get("request_id") or ""),
            conversation_id=str(data.get("conversation_id") or ""),
            model=str(data.get("model") or "nova"),
            provider=str(data.get("provider") or "nova-core"),
            content=str(data.get("content") or ""),
            finish_reason=str(data.get("finish_reason") or "stop"),
            tool_calls=[NovaToolCall.from_dict(item) for item in data.get("tool_calls") or []],
            usage=dict(data.get("usage") or {}),
            created_at=str(data.get("created_at") or utc_now()),
            metadata=dict(data.get("metadata") or {}),
            errors=list(data.get("errors") or []),
            schema_version=str(data.get("schema_version") or PROTOCOL_VERSION),
        )


@dataclass
class NovaStreamEvent(Serializable):
    event_type: str
    response_id: str
    sequence: int
    delta: str = ""
    tool_call: NovaToolCall | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    done: bool = False
    schema_version: str = PROTOCOL_VERSION

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NovaStreamEvent":
        tool_call = data.get("tool_call")
        return cls(
            event_type=str(data.get("event_type") or "content.delta"),
            response_id=str(data.get("response_id") or new_id("resp")),
            sequence=int(data.get("sequence") or 0),
            delta=str(data.get("delta") or ""),
            tool_call=NovaToolCall.from_dict(tool_call) if isinstance(tool_call, dict) else None,
            usage=dict(data.get("usage") or {}),
            metadata=dict(data.get("metadata") or {}),
            error=data.get("error"),
            done=bool(data.get("done", False)),
            schema_version=str(data.get("schema_version") or PROTOCOL_VERSION),
        )


__all__ = [
    "ALLOWED_MESSAGE_ROLES",
    "ALLOWED_PRIVACY_MODES",
    "API_VERSION",
    "NovaAttachment",
    "NovaGenerationOptions",
    "NovaMessage",
    "NovaRequest",
    "NovaResponse",
    "NovaStreamEvent",
    "NovaToolCall",
    "NovaToolDefinition",
    "PROTOCOL_VERSION",
    "ProtocolValidationError",
    "new_id",
    "utc_now",
]
