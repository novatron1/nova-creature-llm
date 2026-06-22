from __future__ import annotations

import hashlib
import math
import random
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import torch

from nova_byte_tokenizer import NovaByteTokenizer
from nova_torch_transformer import load_checkpoint, save_checkpoint
from nova_training_types import ROLE_NAMES


def build_supervised_sequence(
    tokenizer: NovaByteTokenizer,
    prompt: str,
    answer: str,
    block_size: int,
) -> tuple[list[int], list[int]]:
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("answer must be a non-empty string")

    prompt_ids = tokenizer.encode(prompt, add_special=False)
    answer_ids = tokenizer.encode(answer, add_special=False)
    if not answer_ids:
        raise ValueError("answer must produce at least one token")

    token_ids = [tokenizer.BOS, *prompt_ids, tokenizer.SEP, *answer_ids, tokenizer.EOS]
    token_ids = token_ids[:block_size]

    if tokenizer.SEP not in token_ids:
        raise ValueError("supervised sequence lost SEP during truncation")
    sep_index = token_ids.index(tokenizer.SEP)
    if sep_index + 1 >= len(token_ids):
        raise ValueError("supervised sequence lost all answer tokens during truncation")

    targets = token_ids[1:] + [tokenizer.EOS]
    for index in range(min(sep_index, len(targets))):
        targets[index] = -100
    if not any(target != -100 for target in targets):
        raise ValueError("supervised sequence has no answer targets")
    return token_ids, targets


def train_role_candidate(
    role: str,
    baseline_path: str | Path,
    train_rows: Sequence[Mapping[str, Any]],
    validation_rows: Sequence[Mapping[str, Any]],
    output_path: str | Path,
    *,
    seed: int = 0,
    epochs: int = 10,
    batch_size: int = 8,
    learning_rate: float = 3e-4,
) -> dict[str, Any]:
    if role not in ROLE_NAMES:
        raise ValueError(f"invalid role: {role!r}")
    if epochs <= 0:
        raise ValueError("epochs must be positive")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if not math.isfinite(learning_rate) or learning_rate <= 0:
        raise ValueError("learning_rate must be a positive finite number")

    baseline_path = Path(baseline_path)
    output_path = Path(output_path)
    _validate_candidate_path(baseline_path, output_path)

    model, payload = load_checkpoint(baseline_path)
    baseline_metadata = payload.get("metadata", {})
    baseline_role = baseline_metadata.get("role") if isinstance(baseline_metadata, Mapping) else None
    if baseline_role is not None and baseline_role != role:
        raise ValueError(f"baseline role {baseline_role!r} does not match requested role {role!r}")

    tokenizer = NovaByteTokenizer()
    block_size = model.config.block_size
    train_examples = _prepare_examples(tokenizer, train_rows, block_size, "train")
    validation_examples = _prepare_examples(tokenizer, validation_rows, block_size, "validation")

    baseline_sha256 = _sha256_file(baseline_path)
    start_time = time.perf_counter()
    train_loss_history: list[float] = []
    validation_loss_history: list[float] = []
    steps = 0
    checks_without_improvement = 0
    best_validation_loss = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    final_validation_loss = float("nan")

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)
    shuffle_rng = random.Random(seed)

    torch_rng_state = torch.random.get_rng_state()
    try:
        torch.manual_seed(seed)
        baseline_validation_loss = _validation_loss(model, validation_examples, batch_size)

        for epoch in range(epochs):
            model.train()
            shuffled_examples = list(train_examples)
            shuffle_rng.shuffle(shuffled_examples)

            for tokens, targets in _iter_batches(shuffled_examples, batch_size):
                optimizer.zero_grad(set_to_none=True)
                _, loss = model(tokens, targets)
                if loss is None or not torch.isfinite(loss):
                    raise FloatingPointError("non-finite training loss")
                loss.backward()
                _reject_non_finite_gradients(model)
                total_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                if not torch.isfinite(total_norm):
                    raise FloatingPointError("non-finite gradient norm")
                optimizer.step()

                train_loss_history.append(float(loss.detach().cpu()))
                steps += 1

            final_validation_loss = _validation_loss(model, validation_examples, batch_size)
            validation_loss_history.append(final_validation_loss)
            if final_validation_loss < best_validation_loss:
                best_validation_loss = final_validation_loss
                best_state = _clone_state_dict(model.state_dict())
                checks_without_improvement = 0
            else:
                checks_without_improvement += 1
                if checks_without_improvement >= 5:
                    break
    finally:
        torch.random.set_rng_state(torch_rng_state)

    if best_state is None:
        raise RuntimeError("training completed without a validation checkpoint")
    model.load_state_dict(best_state, strict=True)

    duration_seconds = time.perf_counter() - start_time
    metadata = {
        "role": role,
        "seed": seed,
        "train_count": len(train_examples),
        "validation_count": len(validation_examples),
        "baseline_sha256": baseline_sha256,
        "baseline_validation_loss": baseline_validation_loss,
        "best_validation_loss": best_validation_loss,
        "final_validation_loss": final_validation_loss,
        "steps": steps,
        "duration_seconds": duration_seconds,
    }
    candidate_sha256 = save_checkpoint(output_path, model, metadata)

    return {
        **metadata,
        "candidate_sha256": candidate_sha256,
        "checkpoint_path": str(output_path),
        "train_loss_history": train_loss_history,
        "validation_loss_history": validation_loss_history,
        "epochs_ran": len(validation_loss_history),
        "learning_rate": learning_rate,
        "batch_size": batch_size,
    }


def _prepare_examples(
    tokenizer: NovaByteTokenizer,
    rows: Sequence[Mapping[str, Any]],
    block_size: int,
    split_name: str,
) -> list[tuple[list[int], list[int]]]:
    examples: list[tuple[list[int], list[int]]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{split_name} row {index} must be a mapping")
        if row.get("task_type") == "route":
            continue
        if "answer" not in row:
            raise ValueError(f"{split_name} row {index} is missing answer")
        prompt = row.get("prompt")
        answer = row.get("answer")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{split_name} row {index} must have a non-empty prompt")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"{split_name} row {index} must have a non-empty answer")
        examples.append(build_supervised_sequence(tokenizer, prompt, answer, block_size))
    if not examples:
        raise ValueError(f"{split_name} rows produced no answer examples")
    return examples


def _iter_batches(
    examples: Sequence[tuple[list[int], list[int]]],
    batch_size: int,
) -> Iterable[tuple[torch.Tensor, torch.Tensor]]:
    for start in range(0, len(examples), batch_size):
        batch = examples[start : start + batch_size]
        max_len = max(len(tokens) for tokens, _ in batch)
        token_rows: list[list[int]] = []
        target_rows: list[list[int]] = []
        for tokens, targets in batch:
            pad_len = max_len - len(tokens)
            token_rows.append([*tokens, *([NovaByteTokenizer.PAD] * pad_len)])
            target_rows.append([*targets, *([-100] * pad_len)])
        yield (
            torch.tensor(token_rows, dtype=torch.long),
            torch.tensor(target_rows, dtype=torch.long),
        )


def _validation_loss(
    model: torch.nn.Module,
    examples: Sequence[tuple[list[int], list[int]]],
    batch_size: int,
) -> float:
    model.eval()
    total_loss = 0.0
    total_targets = 0
    with torch.no_grad():
        for tokens, targets in _iter_batches(examples, batch_size):
            _, loss = model(tokens, targets)
            if loss is None or not torch.isfinite(loss):
                raise FloatingPointError("non-finite validation loss")
            target_count = int((targets != -100).sum().item())
            if target_count <= 0:
                raise ValueError("validation batch has no answer targets")
            total_loss += float(loss.detach().cpu()) * target_count
            total_targets += target_count
    if total_targets <= 0:
        raise ValueError("validation rows produced no answer targets")
    return total_loss / total_targets


def _reject_non_finite_gradients(model: torch.nn.Module) -> None:
    for name, parameter in model.named_parameters():
        if parameter.grad is not None and not torch.isfinite(parameter.grad).all():
            raise FloatingPointError(f"non-finite gradient detected: {name}")


def _clone_state_dict(state_dict: Mapping[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    return {name: tensor.detach().cpu().clone() for name, tensor in state_dict.items()}


def _validate_candidate_path(baseline_path: Path, output_path: Path) -> None:
    if baseline_path.resolve() == output_path.resolve():
        raise ValueError("candidate output path must not equal baseline path")
    path_text = str(output_path).lower()
    forbidden_markers = ("baseline", "winner", "live")
    if any(marker in path_text for marker in forbidden_markers):
        raise ValueError("candidate output path must not look like a baseline, winner, or live path")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
