from __future__ import annotations

import copy
import hashlib
import io
import json
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
) -> tuple[NovaRouteClassifier, dict]:
    rows = _coerce_examples(examples, "examples")
    validation_rows = _coerce_examples(validation_examples, "validation_examples") if validation_examples is not None else rows
    if epochs <= 0:
        raise ValueError("epochs must be positive")
    if hidden_size <= 0:
        raise ValueError("hidden_size must be positive")
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if learning_rate <= 0:
        raise ValueError("learning_rate must be positive")

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
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
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
    macro_f1, per_role_f1 = _macro_f1(role_true, role_pred, len(class_maps["id_to_role"]))

    return {
        "domain_accuracy": domain_accuracy,
        "primary_role_accuracy": role_accuracy,
        "macro_f1": macro_f1,
        "per_role_f1": {
            class_maps["id_to_role"][index]: score
            for index, score in enumerate(per_role_f1)
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
    saved_metadata.setdefault("model_hash", _hash_state_dict(model.state_dict()))
    saved_metadata.setdefault("class_maps", getattr(model, "route_class_maps", _class_maps()))
    saved_metadata.setdefault("block_size", int(getattr(model, "route_block_size", DEFAULT_BLOCK_SIZE)))
    saved_metadata.setdefault("hidden_size", _infer_hidden_size(model))

    payload = {
        "state_dict": model.state_dict(),
        "metadata": saved_metadata,
        "class_maps": saved_metadata["class_maps"],
    }
    torch.save(payload, path)

    sidecar_path = _sidecar_path(path)
    sidecar_path.write_text(json.dumps(saved_metadata, indent=2, sort_keys=True), encoding="utf-8")
    model.route_metadata = saved_metadata
    return saved_metadata


def load_route_model(path: str | Path) -> tuple[NovaRouteClassifier, dict]:
    payload = torch.load(Path(path), map_location="cpu")
    metadata = dict(payload.get("metadata", {}))
    class_maps = metadata.get("class_maps") or payload.get("class_maps") or _class_maps()
    hidden_size = int(metadata.get("hidden_size", DEFAULT_HIDDEN_SIZE))
    block_size = int(metadata.get("block_size", DEFAULT_BLOCK_SIZE))

    model = NovaRouteClassifier(
        NovaByteTokenizer.vocab_size,
        hidden_size,
        len(class_maps["id_to_domain"]),
        len(class_maps["id_to_role"]),
    )
    model.load_state_dict(payload["state_dict"])
    _attach_route_metadata(model, NovaByteTokenizer(), block_size, class_maps)
    metadata.setdefault("model_hash", _hash_state_dict(model.state_dict()))
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
    torch.set_num_threads(1)


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


def _macro_f1(true_ids: Sequence[int], predicted_ids: Sequence[int], class_count: int) -> tuple[float, list[float]]:
    active_labels = set(true_ids) | set(predicted_ids)
    per_class = [0.0 for _ in range(class_count)]
    if not active_labels:
        return 0.0, per_class

    for label in active_labels:
        true_positive = sum(1 for truth, prediction in zip(true_ids, predicted_ids) if truth == label and prediction == label)
        false_positive = sum(1 for truth, prediction in zip(true_ids, predicted_ids) if truth != label and prediction == label)
        false_negative = sum(1 for truth, prediction in zip(true_ids, predicted_ids) if truth == label and prediction != label)
        denominator = (2 * true_positive) + false_positive + false_negative
        per_class[label] = 0.0 if denominator == 0 else (2 * true_positive) / denominator

    return sum(per_class[label] for label in active_labels) / len(active_labels), per_class


def _hash_state_dict(state_dict: dict) -> str:
    buffer = io.BytesIO()
    cpu_state = {key: value.detach().cpu() for key, value in state_dict.items()}
    torch.save(cpu_state, buffer)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def _sidecar_path(path: Path) -> Path:
    suffix = path.suffix
    if suffix:
        return path.with_suffix(f"{suffix}.json")
    return path.with_name(f"{path.name}.json")


def _infer_hidden_size(model: NovaRouteClassifier) -> int:
    return int(model.embedding.embedding_dim)
