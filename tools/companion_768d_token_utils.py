"""Tokenizer helpers shared by local tests and the Kaggle continuation runner."""

from __future__ import annotations

from collections.abc import Iterable
import re


def _token_id(tokenizer, *, class_attribute: str, fallback_token: str, id_names: tuple[str, ...]) -> int | None:
    for name in id_names:
        value = getattr(tokenizer, name, None)
        if value is not None:
            return int(value)

    token_name = getattr(type(tokenizer), class_attribute, None)
    if token_name is None:
        token_name = getattr(tokenizer, class_attribute, fallback_token)
    if token_name is None:
        token_name = fallback_token

    tokens = getattr(tokenizer, "tokens", None)
    if isinstance(tokens, Iterable):
        for index, token in enumerate(tokens):
            if token == token_name:
                return index

    encoded = list(tokenizer.encode(token_name))
    if len(encoded) == 1:
        return int(encoded[0])
    return None


def unknown_token_id(tokenizer) -> int | None:
    return _token_id(
        tokenizer,
        class_attribute="UNK",
        fallback_token="<unk>",
        id_names=("unk_token_id", "unk_id", "unknown_id"),
    )


def _token_string_items(tokenizer) -> list[tuple[str, int]]:
    """Return token text/id pairs from the common curated-tokenizer schemas."""
    sources = (
        getattr(tokenizer, "tokens", None),
        getattr(tokenizer, "itos", None),
        getattr(tokenizer, "vocab", None),
    )
    items: list[tuple[str, int]] = []
    for source in sources:
        if isinstance(source, dict):
            for token, token_id in source.items():
                if isinstance(token, str) and isinstance(token_id, int):
                    items.append((token, token_id))
        elif isinstance(source, (list, tuple)):
            for token_id, token in enumerate(source):
                if isinstance(token, str):
                    items.append((token, token_id))
        if items:
            break
    return items


def _greedy_known_token_ids(text: str, token_map: list[tuple[str, int]]) -> list[int] | None:
    """Greedily encode text using exact known token strings."""
    ordered = sorted(token_map, key=lambda item: len(item[0]), reverse=True)
    output: list[int] = []
    position = 0
    while position < len(text):
        match = next(
            ((token, token_id) for token, token_id in ordered if token and text.startswith(token, position)),
            None,
        )
        if match is None:
            return None
        token, token_id = match
        output.append(token_id)
        position += len(token)
    return output


def encode_with_unknown_fallback(text: str, tokenizer) -> tuple[list[int], dict]:
    """Encode text while rescuing unknown segments with exact known pieces.

    The function never invents IDs. If a segment cannot be represented by the
    restored tokenizer's exposed token strings, its original encoding is kept
    and the unresolved unknown count is reported.
    """
    original_ids = [int(value) for value in tokenizer.encode(text)]
    unk_id = unknown_token_id(tokenizer)
    original_unknown_count = original_ids.count(unk_id) if unk_id is not None else 0
    report = {
        "original_unknown_count": original_unknown_count,
        "rescued_count": 0,
        "unresolved_count": 0,
        "used_fallback": False,
    }
    if not original_unknown_count or unk_id is None:
        return original_ids, report

    excluded = {getattr(type(tokenizer), "UNK", None), getattr(type(tokenizer), "EOT", None)}
    token_map = [(token, token_id) for token, token_id in _token_string_items(tokenizer) if token not in excluded]
    if not token_map:
        report["unresolved_count"] = original_unknown_count
        return original_ids, report

    output: list[int] = []
    for segment in re.findall(r"\s+|\S+", text):
        segment_ids = [int(value) for value in tokenizer.encode(segment)]
        if unk_id not in segment_ids:
            output.extend(segment_ids)
            continue
        rescued_ids = _greedy_known_token_ids(segment, token_map)
        if rescued_ids is None:
            output.extend(segment_ids)
            report["unresolved_count"] += segment_ids.count(unk_id)
            continue
        output.extend(rescued_ids)
        report["rescued_count"] += 1
        report["used_fallback"] = True

    return output, report


def end_of_text_token_id(tokenizer) -> int:
    token_id = _token_id(
        tokenizer,
        class_attribute="EOT",
        fallback_token="<|endoftext|>",
        id_names=("eot_token_id", "eot_id", "end_of_text_id", "eos_token_id"),
    )
    if token_id is None:
        raise ValueError("Could not identify the tokenizer end-of-text token")
    return token_id


def tokenize_documents_with_boundaries(documents: list[str], tokenizer) -> list[int]:
    values: list[int] = []
    eot_id = end_of_text_token_id(tokenizer)
    for text in documents:
        encoded, _ = encode_with_unknown_fallback(text, tokenizer)
        values.extend(encoded)
        values.append(eot_id)
    if not values:
        raise ValueError("The tokenizer produced zero tokens")
    return values


def truncate_at_end_of_text(text: str, tokenizer) -> str:
    token = getattr(type(tokenizer), "EOT", None)
    if token is None:
        token = getattr(tokenizer, "EOT", "<|endoftext|>")
    return text.split(token, 1)[0]


def build_loss_mask(text: str, tokenizer, *, encoded_ids: list[int] | None = None) -> list[int]:
    """Mask prompt/header tokens and retain answer/statement tokens."""
    markers = ("Answer:", "Statement:", "Definition:")
    boundary = None
    for marker in markers:
        position = text.find(marker)
        if position >= 0:
            boundary = position + len(marker)
            break
    if boundary is None:
        sentence_end = text.find(". ")
        boundary = sentence_end + 2 if sentence_end >= 0 else 0

    encoded = list(encoded_ids) if encoded_ids is not None else encode_with_unknown_fallback(text, tokenizer)[0]
    prefix_length = len(encode_with_unknown_fallback(text[:boundary], tokenizer)[0])
    prefix_length = min(prefix_length, len(encoded))
    return [0] * prefix_length + [1] * (len(encoded) - prefix_length)
