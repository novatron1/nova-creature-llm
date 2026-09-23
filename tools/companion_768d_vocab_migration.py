"""Append-only tokenizer and model-state migration helpers for Companion 768d."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping


def extend_tokenizer_state(tokenizer_state: Mapping, additions: Iterable[str]) -> dict:
    """Append new curated tokens without changing any existing token ID."""
    state = dict(tokenizer_state)
    original_tokens = list(state.get("tokens") or [])
    if not original_tokens:
        raise ValueError("Tokenizer state must contain a non-empty tokens list")

    special_tokens = {
        token
        for token in ("<unk>", "<|endoftext|>", state.get("unk_token"), state.get("eot_token"))
        if isinstance(token, str)
    }
    tokens = list(original_tokens)
    known = set(tokens)
    for token in additions:
        if not isinstance(token, str) or not token:
            raise ValueError("Tokenizer additions must be non-empty strings")
        if token in special_tokens:
            raise ValueError(f"Cannot append special tokenizer token: {token}")
        if token in known:
            continue
        tokens.append(token)
        known.add(token)

    state["tokens"] = tokens
    state["vocab_size"] = len(tokens)
    return state


def _clone(value):
    clone = getattr(value, "clone", None)
    if callable(clone):
        return clone()
    copy_method = getattr(value, "copy", None)
    if callable(copy_method):
        return copy_method()
    return copy.deepcopy(value)


def _shape(value) -> tuple[int, ...]:
    shape = getattr(value, "shape", None)
    if shape is None:
        raise ValueError("Vocabulary state values must expose a shape")
    return tuple(int(dimension) for dimension in shape)


def _vocab_dimension(source_shape: tuple[int, ...], target_shape: tuple[int, ...], old_vocab: int) -> int | None:
    candidates = [
        index
        for index, (source_dim, target_dim) in enumerate(zip(source_shape, target_shape))
        if source_dim == old_vocab and target_dim > old_vocab
        and all(
            left == right
            for dimension, (left, right) in enumerate(zip(source_shape, target_shape))
            if dimension != index
        )
    ]
    if len(candidates) > 1:
        raise ValueError(f"Ambiguous vocabulary dimension for shapes {source_shape} -> {target_shape}")
    return candidates[0] if candidates else None


def copy_vocab_expanded_state(source_state: Mapping, target_state: Mapping, old_vocab: int) -> dict:
    """Copy an old checkpoint into an already-created expanded model state.

    Parameters with unchanged shapes are copied wholesale. Parameters with one
    expanded dimension copy the first ``old_vocab`` rows/columns and preserve
    the target model's initialization for new token entries.
    """
    if old_vocab <= 0:
        raise ValueError("old_vocab must be positive")
    if set(source_state) != set(target_state):
        missing = sorted(set(source_state) - set(target_state))
        extra = sorted(set(target_state) - set(source_state))
        raise ValueError(f"Model state keys differ; missing={missing}, extra={extra}")

    migrated = {}
    for key in source_state:
        source = source_state[key]
        target = target_state[key]
        source_shape = _shape(source)
        target_shape = _shape(target)
        if source_shape == target_shape:
            migrated[key] = _clone(source)
            continue

        dimension = _vocab_dimension(source_shape, target_shape, old_vocab)
        if dimension is None:
            raise ValueError(f"Unexpected model-state shape change for {key}: {source_shape} -> {target_shape}")

        expanded = _clone(target)
        slices = [slice(None)] * len(target_shape)
        slices[dimension] = slice(0, old_vocab)
        expanded[tuple(slices)] = source
        migrated[key] = expanded
    return migrated
