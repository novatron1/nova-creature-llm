from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import torch
from torch import nn
from torch.nn import functional as F

from nova_byte_tokenizer import NovaByteTokenizer
from nova_training_types import DOMAIN_NAMES, ROLE_NAMES, RoutePrediction

DEFAULT_BLOCK_SIZE = 128
DEFAULT_HIDDEN_SIZE = 64
DEFAULT_BATCH_SIZE = 16
DEFAULT_LEARNING_RATE = 0.01


@dataclass(frozen=True)
class RouteExample:
    text: str
    domain: str
    primary_role: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be a non-empty string")
        if self.domain not in DOMAIN_NAMES:
            raise ValueError(f"invalid domain: {self.domain!r}")
        if self.primary_role not in ROLE_NAMES:
            raise ValueError(f"invalid primary_role: {self.primary_role!r}")


class NovaRouteClassifier(nn.Module):
    def __init__(self, vocab_size: int, hidden_size: int, domain_count: int, role_count: int):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, hidden_size, padding_idx=0)
        self.encoder = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.GELU(),
            nn.Dropout(0.1),
        )
        self.domain_head = nn.Linear(hidden_size, domain_count)
        self.role_head = nn.Linear(hidden_size, role_count)

    def forward(self, token_ids, mask):
        embedded = self.embedding(token_ids)
        pooled = (embedded * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True).clamp_min(1)
        hidden = self.encoder(pooled)
        return self.domain_head(hidden), self.role_head(hidden)


def train_route_model(
    examples: Sequence[RouteExample],
    *,
    seed: int = 0,
    epochs: int = 40,
    validation_examples: Sequence[RouteExample] | None = None,
    output_path: str | Path | None = None,
    hidden_size: int = DEFAULT_HIDDEN_SIZE,
    block_size: int = DEFAULT_BLOCK_SIZE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    allow_train_fallback_for_output: bool = False,
) -> tuple[NovaRouteClassifier, dict]:
    rows = _coerce_examples(examples, "examples")
    validation_source = "holdout" if validation_examples is not None else "train_fallback"
    if output_path is not None and validation_examples is None and not allow_train_fallback_for_output:
        raise ValueError(
            "validation_examples must be provided when output_path is used; "
            "pass allow_train_fallback_for_output=True to explicitly save a train-fallback artifact"
        )
    validation_rows = _coerce_examples(validation_examples, "validation_examples") if validation_examples is not None else rows
    if epochs <= 0:
        raise ValueError("epochs must be positive")
    if hidden_size <= 0:
        raise ValueError("hidden_size must be positive")
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if not math.isfinite(learning_rate) or learning_rate <= 0:
        raise ValueError("learning_rate must be finite and positive")

    _set_seed(seed)
    tokenizer = NovaByteTokenizer()
    class_maps = _class_maps()
    model = NovaRouteClassifier(
        tokenizer.vocab_size,
        hidden_size,
        len(class_maps["id_to_domain"]),
        len(class_maps["id_to_role"]),
    )
    _attach_route_metadata(model, tokenizer, block_size, class_maps)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    best_state = copy.deepcopy(model.state_dict())
    best_metrics = evaluate_route_model(model, validation_rows)
    best_loss = float("inf")

    for epoch in range(epochs):
        model.train()
        epoch_order = list(range(len(rows)))
        random.Random(seed + epoch).shuffle(epoch_order)

        for start in range(0, len(epoch_order), batch_size):
            batch_rows = [rows[index] for index in epoch_order[start : start + batch_size]]
            token_ids, mask, domain_targets, role_targets = _tensorize(batch_rows, tokenizer, block_size, class_maps)

            optimizer.zero_grad(set_to_none=True)
            domain_logits, role_logits = model(token_ids, mask)
            loss = F.cross_entropy(domain_logits, domain_targets) + F.cross_entropy(role_logits, role_targets)
            if not torch.isfinite(loss):
                raise ValueError("non-finite training loss while fitting route model")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0, error_if_nonfinite=True)
            optimizer.step()

        current_metrics = evaluate_route_model(model, validation_rows)
        current_loss = _evaluation_loss(model, validation_rows, tokenizer, block_size, class_maps)
        if (
            current_metrics["macro_f1"] > best_metrics["macro_f1"]
            or (
                current_metrics["macro_f1"] == best_metrics["macro_f1"]
                and current_metrics["primary_role_accuracy"] > best_metrics["primary_role_accuracy"]
            )
            or (
                current_metrics["macro_f1"] == best_metrics["macro_f1"]
                and current_metrics["primary_role_accuracy"] == best_metrics["primary_role_accuracy"]
                and current_loss < best_loss
            )
        ):
            best_state = copy.deepcopy(model.state_dict())
            best_metrics = current_metrics
            best_loss = current_loss

    model.load_state_dict(best_state)
    model_hash = _hash_state_dict(model.state_dict())
    metadata = {
        "seed": seed,
        "epochs": epochs,
        "hidden_size": hidden_size,
        "block_size": block_size,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "train_count": len(rows),
        "validation_count": len(validation_rows),
        "validation_source": validation_source,
        "class_maps": class_maps,
        "best_metrics": best_metrics,
        "model_hash": model_hash,
    }
    model.route_metadata = metadata

    if output_path is not None:
        save_route_model(model, output_path, metadata=metadata)
        metadata = dict(metadata)
        metadata["output_path"] = str(output_path)
        model.route_metadata = metadata

    return model, metadata


@torch.no_grad()
def evaluate_route_model(model: NovaRouteClassifier, examples: Sequence[RouteExample]) -> dict:
    rows = _coerce_examples(examples, "examples")
    tokenizer = getattr(model, "route_tokenizer", NovaByteTokenizer())
    block_size = int(getattr(model, "route_block_size", DEFAULT_BLOCK_SIZE))
    class_maps = getattr(model, "route_class_maps", _class_maps())

    model.eval()
    token_ids, mask, domain_targets, role_targets = _tensorize(rows, tokenizer, block_size, class_maps)
    domain_logits, role_logits = model(token_ids, mask)
    domain_predictions = domain_logits.argmax(dim=1)
    role_predictions = role_logits.argmax(dim=1)

    role_true = role_targets.tolist()
    role_pred = role_predictions.tolist()
    domain_true = domain_targets.tolist()
    domain_pred = domain_predictions.tolist()

    role_accuracy = _accuracy(role_true, role_pred)
    domain_accuracy = _accuracy(domain_true, domain_pred)
    macro_f1_active, macro_f1_all_roles, per_role_f1, per_role_support = _macro_f1(
        role_true,
        role_pred,
        len(class_maps["id_to_role"]),
    )

    return {
        "domain_accuracy": domain_accuracy,
        "primary_role_accuracy": role_accuracy,
        "macro_f1": macro_f1_active,
        "macro_f1_active": macro_f1_active,
        "macro_f1_all_roles": macro_f1_all_roles,
        "per_role_f1": {
            class_maps["id_to_role"][index]: score
            for index, score in enumerate(per_role_f1)
        },
        "per_role_support": {
            class_maps["id_to_role"][index]: support
            for index, support in enumerate(per_role_support)
        },
        "support": len(rows),
    }


@torch.no_grad()
def predict_route(model: NovaRouteClassifier, text: str) -> RoutePrediction:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    tokenizer = getattr(model, "route_tokenizer", NovaByteTokenizer())
    block_size = int(getattr(model, "route_block_size", DEFAULT_BLOCK_SIZE))
    class_maps = getattr(model, "route_class_maps", _class_maps())
    model_hash = getattr(model, "route_metadata", {}).get("model_hash") or _hash_state_dict(model.state_dict())

    model.eval()
    tokens = _encode_text(tokenizer, text, block_size)
    token_ids = torch.tensor([tokens], dtype=torch.long)
    mask = (token_ids != tokenizer.PAD).to(torch.float32)
    domain_logits, role_logits = model(token_ids, mask)
    domain_id = int(domain_logits.argmax(dim=1).item())
    role_probabilities = F.softmax(role_logits, dim=1)[0]
    role_id = int(role_probabilities.argmax().item())
    top_role_ids = role_probabilities.argsort(descending=True)[:3].tolist()

    return RoutePrediction(
        domain=class_maps["id_to_domain"][domain_id],
        primary_role=class_maps["id_to_role"][role_id],
        support_roles=tuple(class_maps["id_to_role"][index] for index in top_role_ids),
        confidence=float(role_probabilities[role_id].item()),
        model_hash=model_hash,
    )


def save_route_model(
    model: NovaRouteClassifier,
    output_path: str | Path,
    *,
    metadata: dict | None = None,
) -> dict:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    saved_metadata = dict(metadata or getattr(model, "route_metadata", {}))
    saved_metadata["model_hash"] = _hash_state_dict(model.state_dict())
    saved_metadata.setdefault("class_maps", getattr(model, "route_class_maps", _class_maps()))
    saved_metadata.setdefault("block_size", int(getattr(model, "route_block_size", DEFAULT_BLOCK_SIZE)))
    saved_metadata.setdefault("hidden_size", _infer_hidden_size(model))
    _validate_class_maps(saved_metadata["class_maps"])

    payload = {
        "state_dict": model.state_dict(),
        "metadata": saved_metadata,
        "class_maps": saved_metadata["class_maps"],
    }
    torch.save(payload, path)

    sidecar_path = _sidecar_path(path)
    sidecar_path.write_text(
        json.dumps(saved_metadata, allow_nan=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    model.route_metadata = saved_metadata
    return saved_metadata


def load_route_model(path: str | Path) -> tuple[NovaRouteClassifier, dict]:
    payload = _safe_torch_load(Path(path))
    if not isinstance(payload, dict):
        raise ValueError("route model payload must be a dictionary")
    if "state_dict" not in payload or "metadata" not in payload:
        raise ValueError("route model payload missing required state_dict or metadata")

    state_dict = payload["state_dict"]
    if not isinstance(state_dict, dict) or not state_dict:
        raise ValueError("route model state_dict must be a non-empty dictionary")
    if not all(isinstance(key, str) and torch.is_tensor(value) for key, value in state_dict.items()):
        raise ValueError("route model state_dict must contain string keys and tensor values")

    metadata = payload["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError("route model metadata must be a dictionary")
    metadata = dict(metadata)

    class_maps = metadata.get("class_maps")
    if class_maps is None:
        class_maps = payload.get("class_maps")
    _validate_class_maps(class_maps)
    if "class_maps" in payload and payload["class_maps"] != class_maps:
        raise ValueError("route model class_maps disagree between payload and metadata")

    expected_hash = metadata.get("model_hash")
    actual_hash = _hash_state_dict(state_dict)
    if not isinstance(expected_hash, str):
        raise ValueError("route model metadata missing model_hash")
    if expected_hash != actual_hash:
        raise ValueError("route model model_hash does not match state_dict")

    hidden_size = _positive_int(metadata.get("hidden_size"), "hidden_size")
    block_size = _positive_int(metadata.get("block_size"), "block_size")

    model = NovaRouteClassifier(
        NovaByteTokenizer.vocab_size,
        hidden_size,
        len(class_maps["id_to_domain"]),
        len(class_maps["id_to_role"]),
    )
    try:
        model.load_state_dict(state_dict)
    except RuntimeError as exc:
        raise ValueError("route model state_dict does not match expected classifier architecture") from exc
    _attach_route_metadata(model, NovaByteTokenizer(), block_size, class_maps)
    metadata["model_hash"] = actual_hash
    model.route_metadata = metadata
    return model, metadata


def route_examples_from_rows(
    rows: Iterable[dict],
    *,
    include_answer_rows: bool = False,
) -> list[RouteExample]:
    route_examples: list[RouteExample] = []
    for row in rows:
        task_type = row.get("task_type")
        if task_type != "route" and not (include_answer_rows and task_type == "answer"):
            continue
        text = row.get("text") or row.get("prompt") or row.get("input")
        domain = row.get("domain")
        primary_role = row.get("primary_role") or row.get("role")
        if text is None or domain is None or primary_role is None:
            continue
        route_examples.append(RouteExample(str(text), str(domain), str(primary_role)))
    return route_examples


def _set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)


def _class_maps() -> dict:
    id_to_domain = list(DOMAIN_NAMES)
    id_to_role = list(ROLE_NAMES)
    return {
        "domain_to_id": {name: index for index, name in enumerate(id_to_domain)},
        "id_to_domain": id_to_domain,
        "role_to_id": {name: index for index, name in enumerate(id_to_role)},
        "id_to_role": id_to_role,
    }


def _attach_route_metadata(
    model: NovaRouteClassifier,
    tokenizer: NovaByteTokenizer,
    block_size: int,
    class_maps: dict,
) -> None:
    model.route_tokenizer = tokenizer
    model.route_block_size = block_size
    model.route_class_maps = class_maps


def _coerce_examples(examples: Sequence[RouteExample] | None, field_name: str) -> list[RouteExample]:
    if examples is None:
        raise ValueError(f"{field_name} must not be None")
    rows = list(examples)
    if not rows:
        raise ValueError(f"{field_name} must not be empty")
    for index, row in enumerate(rows):
        if not isinstance(row, RouteExample):
            raise TypeError(f"{field_name}[{index}] must be a RouteExample")
        if row.domain not in DOMAIN_NAMES:
            raise ValueError(f"invalid domain at {field_name}[{index}]: {row.domain!r}")
        if row.primary_role not in ROLE_NAMES:
            raise ValueError(f"invalid primary_role at {field_name}[{index}]: {row.primary_role!r}")
    return rows


def _tensorize(
    rows: Sequence[RouteExample],
    tokenizer: NovaByteTokenizer,
    block_size: int,
    class_maps: dict,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    encoded = [_encode_text(tokenizer, row.text, block_size) for row in rows]
    token_ids = torch.tensor(encoded, dtype=torch.long)
    mask = (token_ids != tokenizer.PAD).to(torch.float32)
    domain_targets = torch.tensor([class_maps["domain_to_id"][row.domain] for row in rows], dtype=torch.long)
    role_targets = torch.tensor([class_maps["role_to_id"][row.primary_role] for row in rows], dtype=torch.long)
    return token_ids, mask, domain_targets, role_targets


def _encode_text(tokenizer: NovaByteTokenizer, text: str, block_size: int) -> list[int]:
    token_ids = tokenizer.encode(text)[:block_size]
    if len(token_ids) < block_size:
        token_ids = [*token_ids, *([tokenizer.PAD] * (block_size - len(token_ids)))]
    return token_ids


@torch.no_grad()
def _evaluation_loss(
    model: NovaRouteClassifier,
    rows: Sequence[RouteExample],
    tokenizer: NovaByteTokenizer,
    block_size: int,
    class_maps: dict,
) -> float:
    model.eval()
    token_ids, mask, domain_targets, role_targets = _tensorize(rows, tokenizer, block_size, class_maps)
    domain_logits, role_logits = model(token_ids, mask)
    loss = F.cross_entropy(domain_logits, domain_targets) + F.cross_entropy(role_logits, role_targets)
    return float(loss.item())


def _accuracy(true_ids: Sequence[int], predicted_ids: Sequence[int]) -> float:
    if not true_ids:
        return 0.0
    correct = sum(1 for truth, prediction in zip(true_ids, predicted_ids) if truth == prediction)
    return correct / len(true_ids)


def _macro_f1(true_ids: Sequence[int], predicted_ids: Sequence[int], class_count: int) -> tuple[float, float, list[float], list[int]]:
    active_labels = set(true_ids) | set(predicted_ids)
    per_class = [0.0 for _ in range(class_count)]
    per_class_support = [0 for _ in range(class_count)]
    if not active_labels:
        return 0.0, 0.0, per_class, per_class_support

    for label in active_labels:
        per_class_support[label] = sum(1 for truth in true_ids if truth == label)
        true_positive = sum(1 for truth, prediction in zip(true_ids, predicted_ids) if truth == label and prediction == label)
        false_positive = sum(1 for truth, prediction in zip(true_ids, predicted_ids) if truth != label and prediction == label)
        false_negative = sum(1 for truth, prediction in zip(true_ids, predicted_ids) if truth == label and prediction != label)
        denominator = (2 * true_positive) + false_positive + false_negative
        per_class[label] = 0.0 if denominator == 0 else (2 * true_positive) / denominator

    macro_active = sum(per_class[label] for label in active_labels) / len(active_labels)
    macro_all = sum(per_class) / class_count if class_count else 0.0
    return macro_active, macro_all, per_class, per_class_support


def _hash_state_dict(state_dict: dict) -> str:
    digest = hashlib.sha256()
    for key in sorted(state_dict):
        value = state_dict[key]
        if not torch.is_tensor(value):
            raise ValueError("state_dict values must be tensors")
        tensor = value.detach().cpu().contiguous()
        digest.update(key.encode("utf-8"))
        digest.update(str(tensor.dtype).encode("utf-8"))
        digest.update(json.dumps(list(tensor.shape), separators=(",", ":")).encode("utf-8"))
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def _sidecar_path(path: Path) -> Path:
    suffix = path.suffix
    if suffix:
        return path.with_suffix(f"{suffix}.json")
    return path.with_name(f"{path.name}.json")


def _infer_hidden_size(model: NovaRouteClassifier) -> int:
    return int(model.embedding.embedding_dim)


def _safe_torch_load(path: Path) -> object:
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        return torch.load(path, map_location="cpu")


def _validate_class_maps(class_maps: object) -> None:
    if not isinstance(class_maps, dict):
        raise ValueError("route model class_maps must be a dictionary")
    expected = _class_maps()
    required_keys = {"domain_to_id", "id_to_domain", "role_to_id", "id_to_role"}
    if set(class_maps) != required_keys:
        raise ValueError("route model class_maps keys do not match expected schema")
    if class_maps != expected:
        raise ValueError("route model class_maps do not match DOMAIN_NAMES and ROLE_NAMES")


def _positive_int(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"route model metadata {field_name} must be a positive integer")
    return value
