"""OpenAI and Nova-native adapters around the provider-neutral protocol."""

from __future__ import annotations

from datetime import datetime
import json
import time
from typing import Any, Iterable

from nova_protocol import (
    NovaAttachment,
    NovaGenerationOptions,
    NovaMessage,
    NovaRequest,
    NovaResponse,
    NovaStreamEvent,
    NovaToolDefinition,
    new_id,
)
from nova_evaluation_policy import sanitize_external_metadata

from .auth import AuthContext
from .errors import InvalidRequestError, UnsupportedFeatureError


SUPPORTED_CHAT_FIELDS = {
    "model", "messages", "temperature", "top_p", "max_tokens", "max_completion_tokens", "stream", "stop",
    "tools", "tool_choice", "response_format", "seed", "user", "metadata", "frequency_penalty", "presence_penalty",
    "stream_options",
}


def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("metadata")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidRequestError("metadata must be an object.", param="metadata")
    return sanitize_external_metadata(value)


def _messages(items: Any) -> list[NovaMessage]:
    if not isinstance(items, list) or not items:
        raise InvalidRequestError("messages must be a non-empty array.", param="messages")
    messages: list[NovaMessage] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise InvalidRequestError("Each message must be an object.", param=f"messages[{index}]")
        role = str(item.get("role") or "")
        metadata: dict[str, Any] = {}
        if item.get("tool_calls") is not None:
            metadata["tool_calls"] = item.get("tool_calls")
        messages.append(
            NovaMessage(
                role=role,
                content=item.get("content"),
                name=item.get("name"),
                tool_call_id=item.get("tool_call_id"),
                metadata=metadata,
            )
        )
    if not any(message.role == "user" for message in messages):
        raise InvalidRequestError("At least one user message is required.", param="messages")
    return messages


def _attachments(messages: list[NovaMessage]) -> list[NovaAttachment]:
    output: list[NovaAttachment] = []
    for message in messages:
        if not isinstance(message.content, list):
            continue
        for item in message.content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "")
            if item_type in {"image_url", "input_image"}:
                source = item.get("image_url")
                url = source.get("url") if isinstance(source, dict) else source
                output.append(
                    NovaAttachment(
                        media_type="image/*", source_type="url" if url else "reference",
                        url=str(url) if url else None,
                        metadata={"api_item_type": item_type, "file_id": item.get("file_id")},
                    )
                )
            elif item_type in {"input_audio", "audio"}:
                audio = item.get("input_audio") or item
                output.append(
                    NovaAttachment(
                        media_type=str(audio.get("format") or "audio/*"), source_type="inline",
                        data=audio.get("data"), metadata={"api_item_type": item_type},
                    )
                )
    return output


def _tools(items: Any) -> list[NovaToolDefinition]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise InvalidRequestError("tools must be an array.", param="tools")
    output: list[NovaToolDefinition] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("type") != "function" or not isinstance(item.get("function"), dict):
            raise UnsupportedFeatureError("Only function tools are supported.", param=f"tools[{index}]")
        function = item["function"]
        output.append(
            NovaToolDefinition(
                name=function.get("name", ""),
                description=str(function.get("description") or ""),
                input_schema=dict(function.get("parameters") or {"type": "object"}),
                metadata={"strict": bool(function.get("strict", False)), "api_source": "openai"},
            )
        )
    return output


def _response_tools(items: Any) -> list[NovaToolDefinition]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise InvalidRequestError("tools must be an array.", param="tools")
    output: list[NovaToolDefinition] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("type") != "function":
            raise UnsupportedFeatureError("Only Responses function tools are supported.", param=f"tools[{index}]")
        if isinstance(item.get("function"), dict):
            function = item["function"]
        else:
            function = item
        output.append(
            NovaToolDefinition(
                name=function.get("name", ""), description=str(function.get("description") or ""),
                input_schema=dict(function.get("parameters") or {"type": "object"}),
                metadata={"strict": bool(function.get("strict", False)), "api_source": "openai_responses"},
            )
        )
    return output


def openai_chat_to_nova(payload: dict[str, Any], auth: AuthContext) -> NovaRequest:
    if not isinstance(payload, dict):
        raise InvalidRequestError("Request body must be an object.")
    unknown = set(payload) - SUPPORTED_CHAT_FIELDS
    important_unsupported = unknown & {"audio", "modalities", "prediction", "service_tier", "logprobs", "top_logprobs"}
    if important_unsupported:
        field = sorted(important_unsupported)[0]
        raise UnsupportedFeatureError(f"Chat Completions field {field!r} is not supported by Nova yet.", param=field)
    metadata = _metadata(payload)
    max_tokens = payload.get("max_completion_tokens")
    if max_tokens is None:
        max_tokens = payload.get("max_tokens")
    options = NovaGenerationOptions(
        model=str(payload.get("model") or "nova"), temperature=payload.get("temperature"), top_p=payload.get("top_p"),
        max_tokens=max_tokens, stop=payload.get("stop"), seed=payload.get("seed"), stream=bool(payload.get("stream", False)),
        response_format=payload.get("response_format"), frequency_penalty=payload.get("frequency_penalty"),
        presence_penalty=payload.get("presence_penalty"), metadata={"stream_options": payload.get("stream_options") or {}},
    )
    scopes = sorted(auth.scopes)
    metadata["client_scopes"] = scopes
    metadata.pop("memory_mode", None)  # Server policy cannot be weakened by client metadata.
    messages = _messages(payload.get("messages"))
    return NovaRequest(
        request_id=str(metadata.get("request_id") or new_id("req")), user_id=str(payload.get("user") or metadata.get("user_id") or "anonymous"),
        client_id=auth.client_id, conversation_id=str(metadata.get("conversation_id") or new_id("conv")),
        session_id=str(metadata.get("session_id") or new_id("sess")), messages=messages, attachments=_attachments(messages),
        tools=_tools(payload.get("tools")), tool_choice=payload.get("tool_choice"), generation_options=options,
        privacy_mode=str(metadata.get("privacy_mode") or "local_preferred"), metadata=metadata,
        api_source="openai_chat_completions", api_version="v1",
    )


def nova_to_openai_chat(response: NovaResponse) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": response.content}
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.tool_call_id, "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments, separators=(",", ":"))},
            }
            for call in response.tool_calls
        ]
    payload: dict[str, Any] = {
        "id": response.response_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response.model,
        "choices": [{"index": 0, "message": message, "finish_reason": response.finish_reason, "logprobs": None}],
        "system_fingerprint": "nova-core-v1",
        "nova_metadata": {
            "request_id": response.request_id, "conversation_id": response.conversation_id,
            "provider": response.provider, "usage_estimated": bool(response.usage.get("estimated", True)),
            "routing": response.metadata.get("routing"),
        },
    }
    exact_keys = {"prompt_tokens", "completion_tokens", "total_tokens"}
    if exact_keys.issubset(response.usage) and not response.usage.get("estimated"):
        payload["usage"] = {key: response.usage[key] for key in exact_keys}
    return payload


def openai_chat_stream_chunks(request: NovaRequest, events: Iterable[NovaStreamEvent]) -> Iterable[dict[str, Any]]:
    first = True
    for event in events:
        delta: dict[str, Any] = {}
        finish_reason = None
        if first:
            delta["role"] = "assistant"
            first = False
        if event.delta:
            delta["content"] = event.delta
        if event.tool_call:
            delta["tool_calls"] = [{
                "index": 0, "id": event.tool_call.tool_call_id, "type": "function",
                "function": {"name": event.tool_call.name, "arguments": json.dumps(event.tool_call.arguments)},
            }]
        if event.done:
            finish_reason = "stop" if not event.error else "error"
        chunk = {
            "id": event.response_id, "object": "chat.completion.chunk", "created": int(time.time()),
            "model": request.generation_options.model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason, "logprobs": None}],
            "system_fingerprint": "nova-core-v1",
        }
        if event.done and event.usage and not event.usage.get("estimated"):
            chunk["usage"] = event.usage
        yield chunk


def _response_input_messages(value: Any) -> list[NovaMessage]:
    if isinstance(value, str):
        return [NovaMessage(role="user", content=value)]
    if not isinstance(value, list) or not value:
        raise InvalidRequestError("Responses input must be text or a non-empty array.", param="input")
    messages: list[NovaMessage] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise InvalidRequestError("Responses input items must be objects.", param=f"input[{index}]")
        item_type = item.get("type")
        if item_type not in {None, "message"}:
            raise UnsupportedFeatureError(f"Responses input item type {item_type!r} is not supported yet.", param=f"input[{index}].type")
        messages.append(NovaMessage(role=str(item.get("role") or "user"), content=item.get("content", "")))
    return messages


def openai_response_to_nova(payload: dict[str, Any], auth: AuthContext) -> NovaRequest:
    for unsupported in ("background", "conversation", "reasoning", "prompt", "service_tier", "max_tool_calls"):
        if payload.get(unsupported) not in (None, False):
            raise UnsupportedFeatureError(f"Responses field {unsupported!r} is not supported yet.", param=unsupported)
    if payload.get("include"):
        raise UnsupportedFeatureError("Responses field 'include' is not supported yet.", param="include")
    if payload.get("store") is True:
        raise UnsupportedFeatureError("Server-side Responses storage is not implemented; use Nova conversation IDs.", param="store")
    metadata = _metadata(payload)
    metadata["client_scopes"] = sorted(auth.scopes)
    metadata.pop("memory_mode", None)  # Server policy cannot be weakened by client metadata.
    if payload.get("previous_response_id"):
        metadata["previous_response_id"] = str(payload["previous_response_id"])
        metadata["continuation_status"] = "identifier_preserved_no_server_side_replay"
    messages = _response_input_messages(payload.get("input"))
    if payload.get("instructions"):
        messages.insert(0, NovaMessage(role="developer", content=str(payload["instructions"])))
    response_format = payload.get("response_format")
    text_config = payload.get("text")
    if response_format is None and isinstance(text_config, dict) and isinstance(text_config.get("format"), dict):
        raw_format = dict(text_config["format"])
        if raw_format.get("type") == "json_schema" and "schema" in raw_format:
            response_format = {"type": "json_schema", "json_schema": raw_format}
        else:
            response_format = raw_format
    options = NovaGenerationOptions(
        model=str(payload.get("model") or "nova"), temperature=payload.get("temperature"), top_p=payload.get("top_p"),
        max_tokens=payload.get("max_output_tokens"), stream=bool(payload.get("stream", False)), response_format=response_format,
    )
    return NovaRequest(
        request_id=str(metadata.get("request_id") or new_id("req")), user_id=str(metadata.get("user_id") or "anonymous"),
        client_id=auth.client_id, conversation_id=str(metadata.get("conversation_id") or new_id("conv")),
        session_id=str(metadata.get("session_id") or new_id("sess")), messages=messages, attachments=_attachments(messages),
        tools=_response_tools(payload.get("tools")), tool_choice=payload.get("tool_choice"), generation_options=options,
        privacy_mode=str(metadata.get("privacy_mode") or "local_preferred"), metadata=metadata,
        api_source="openai_responses", api_version="v1",
    )


def nova_to_openai_response(response: NovaResponse) -> dict[str, Any]:
    output = [{
        "id": new_id("msg"), "type": "message", "status": "completed", "role": "assistant",
        "content": [{"type": "output_text", "text": response.content, "annotations": []}],
    }]
    return {
        "id": response.response_id, "object": "response", "created_at": int(time.time()), "status": "completed",
        "model": response.model, "output": output, "output_text": response.content, "error": None,
        "incomplete_details": None, "metadata": {"nova_request_id": response.request_id, "conversation_id": response.conversation_id},
        "usage": None if response.usage.get("estimated", True) else response.usage,
    }
