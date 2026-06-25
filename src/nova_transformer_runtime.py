from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import torch

from nova_byte_tokenizer import NovaByteTokenizer
from nova_checkpoint_registry import CheckpointRegistry
from nova_route_model import load_route_model, predict_route
from nova_torch_transformer import NovaCausalLM, load_checkpoint
from nova_training_types import (
    DOMAIN_NAMES,
    ROLE_NAMES,
    GenerationResult,
    RoutePrediction,
)


class NovaTransformerRuntime:
    def __init__(self, project_root: Path, route_model=None):
        self.project_root = Path(project_root).resolve()
        self.registry = CheckpointRegistry(self.project_root)
        self.tokenizer = NovaByteTokenizer()
        self.route_model = route_model or load_promoted_route_model(self.project_root)
        self.route_load_error = getattr(self.route_model, "load_error", None)
        self.models: dict[tuple[str, str], NovaCausalLM] = {}
        self.last_route_error: str | None = None

    def route(self, text: str) -> RoutePrediction:
        prediction, route_error = self.route_with_evidence(text)
        self.last_route_error = route_error
        return prediction

    def route_with_evidence(self, text: str) -> tuple[RoutePrediction, str | None]:
        if not isinstance(text, str) or not text.strip():
            text = "general request"

        model = self.route_model or _BaselineRouteModel()
        try:
            if hasattr(model, "predict") and callable(model.predict):
                prediction = model.predict(text)
            elif hasattr(model, "route") and callable(model.route):
                prediction = model.route(text)
            else:
                prediction = _BaselineRouteModel().predict(text)
            return _ensure_route_prediction(prediction), getattr(model, "load_error", None)
        except Exception as exc:
            return _BaselineRouteModel().predict(text), str(exc)

    def generate(self, role: str, prompt: str, max_new_tokens: int = 80) -> GenerationResult:
        started = time.perf_counter()
        checkpoint = None
        checkpoint_path = ""
        checkpoint_hash = ""
        try:
            checkpoint = self.registry.resolve_live(role)
            checkpoint_path = self._trace_checkpoint_path(checkpoint.path)
            checkpoint_hash = checkpoint.sha256
            model = self._load_model(checkpoint.role, checkpoint.sha256, checkpoint.path)
            model.eval()

            prompt_tokens = [
                self.tokenizer.BOS,
                *self.tokenizer.encode(str(prompt), add_special=False),
                self.tokenizer.SEP,
            ]
            if len(prompt_tokens) > model.config.block_size:
                elapsed = max(time.perf_counter() - started, 0.0)
                return GenerationResult(
                    text="",
                    role=checkpoint.role,
                    checkpoint_path=checkpoint_path,
                    checkpoint_hash=checkpoint_hash,
                    tokens_generated=0,
                    elapsed_seconds=elapsed,
                    tokens_per_second=0.0,
                    finish_reason="error",
                    error="prompt too long to preserve BOS/prompt/SEP within transformer block_size",
                )
            max_new_tokens = max(0, int(max_new_tokens))
            generated_tokens: list[int] = []
            finish_reason = "length"

            with torch.no_grad():
                for _ in range(max_new_tokens):
                    context = prompt_tokens + generated_tokens
                    context = context[-model.config.block_size :]
                    token_tensor = torch.tensor([context], dtype=torch.long)
                    logits, _ = model(token_tensor)
                    next_token = int(torch.argmax(logits[0, -1]).item())
                    if next_token == self.tokenizer.EOS:
                        finish_reason = "eos"
                        break
                    generated_tokens.append(next_token)

            elapsed = max(time.perf_counter() - started, 0.0)
            tokens_generated = len(generated_tokens)
            tokens_per_second = tokens_generated / elapsed if elapsed > 0 else 0.0
            text = self.tokenizer.decode(generated_tokens).strip()
            clean_prefix = _readable_prefix_before_junk(text)
            if clean_prefix != text:
                text = clean_prefix
                finish_reason = "eos"
            error = None
            if not text:
                finish_reason = "error"
                error = "transformer generated no decodable text"
            elif _is_unreadable(text):
                finish_reason = "error"
                error = "transformer generated unreadable text"
            elif _is_repetitive(text, generated_tokens):
                finish_reason = "error"
                error = "transformer generated repetitive text"

            return GenerationResult(
                text=text if error is None else "",
                role=checkpoint.role,
                checkpoint_path=checkpoint_path,
                checkpoint_hash=checkpoint_hash,
                tokens_generated=tokens_generated,
                elapsed_seconds=elapsed,
                tokens_per_second=tokens_per_second,
                finish_reason=finish_reason,
                error=error,
            )
        except Exception as exc:
            elapsed = max(time.perf_counter() - started, 0.0)
            return GenerationResult(
                text="",
                role=checkpoint.role if checkpoint is not None else str(role),
                checkpoint_path=checkpoint_path,
                checkpoint_hash=checkpoint_hash,
                tokens_generated=0,
                elapsed_seconds=elapsed,
                tokens_per_second=0.0,
                finish_reason="error",
                error=str(exc),
            )

    def _load_model(self, role: str, sha256: str, path: Path) -> NovaCausalLM:
        cache_key = (role, sha256)
        model = self.models.get(cache_key)
        if model is None:
            model, _ = load_checkpoint(path)
            model.eval()
            self.models[cache_key] = model
        return model

    def _trace_checkpoint_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.project_root).as_posix()
        except ValueError:
            return path.resolve().as_posix()

def load_promoted_route_model(project_root: str | Path):
    root = Path(project_root)
    path = root / "checkpoints" / "route_model" / "promoted.pt"
    if not path.exists():
        return _BaselineRouteModel()
    sidecar = path.with_suffix(f"{path.suffix}.json")
    if not sidecar.exists():
        return _BaselineRouteModel(f"promoted route model failed to load: missing sidecar {sidecar}")
    try:
        sidecar_metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(sidecar_metadata, dict):
            raise ValueError("promoted route sidecar must contain a JSON object")
        model, metadata = load_route_model(path)
        sidecar_hash = sidecar_metadata.get("model_hash")
        payload_hash = metadata.get("model_hash")
        if sidecar_hash != payload_hash:
            raise ValueError("promoted route sidecar model_hash does not match checkpoint metadata")
        return _RouteModelAdapter(model)
    except Exception as exc:
        return _BaselineRouteModel(f"promoted route model failed to load: {exc}")
    return _BaselineRouteModel()


class _RouteModelAdapter:
    def __init__(self, model):
        self.model = model
        self.model_hash = getattr(model, "route_metadata", {}).get("model_hash", "")

    def predict(self, text: str) -> RoutePrediction:
        return predict_route(self.model, text)


class _BaselineRouteModel:
    model_hash = hashlib.sha256(b"nova-baseline-route-model-v1").hexdigest()

    def __init__(self, load_error: str | None = None) -> None:
        self.load_error = load_error

    _DOMAIN_ROLES = {
        "coding": ("left_hemisphere", ("planner_transformer", "critic_conscience_transformer"), 0.76),
        "math": ("left_hemisphere", ("memory_transformer",), 0.72),
        "science": ("memory_transformer", ("left_hemisphere", "critic_conscience_transformer"), 0.70),
        "philosophy": ("critic_conscience_transformer", ("memory_transformer", "right_hemisphere"), 0.68),
        "psychology": ("right_hemisphere", ("memory_transformer", "critic_conscience_transformer"), 0.68),
        "creative": ("right_hemisphere", ("dream_simulation_transformer",), 0.72),
        "memory_recall": ("memory_transformer", ("critic_conscience_transformer",), 0.78),
        "planning": ("planner_transformer", ("left_hemisphere",), 0.74),
        "critic": ("critic_conscience_transformer", ("memory_transformer",), 0.74),
        "speech": ("speech_output_transformer", ("planner_transformer",), 0.70),
        "dream": ("dream_simulation_transformer", ("right_hemisphere",), 0.70),
        "general": ("speech_output_transformer", ("memory_transformer", "critic_conscience_transformer"), 0.55),
    }
    _KEYWORDS = {
        "coding": ("code", "debug", "python", "javascript", "bug", "function", "class", "api", "server", "database", "git"),
        "math": ("math", "equation", "formula", "solve", "calculate", "algebra", "calculus", "probability"),
        "science": ("science", "physics", "chemistry", "biology", "energy", "atom", "cell", "experiment", "theory"),
        "philosophy": ("philosophy", "ethics", "meaning", "consciousness", "truth", "existence", "free will"),
        "psychology": ("psychology", "emotion", "behavior", "mental", "stress", "trauma", "cognitive", "neuron"),
        "creative": ("draw", "paint", "design", "story", "poem", "creative", "imagine", "compose"),
        "memory_recall": ("remember", "recall", "what did i", "who am i", "do you remember"),
        "planning": ("plan", "steps", "strategy", "schedule", "organize", "roadmap", "how to"),
        "critic": ("verify", "check", "evidence", "proof", "wrong", "mistake", "contradiction", "fact"),
        "speech": ("explain", "summarize", "describe", "clarify", "define", "tell me"),
        "dream": ("what if", "simulate", "pretend", "suppose", "hypothetical", "scenario"),
    }

    def predict(self, text: str) -> RoutePrediction:
        domain = self._classify(text)
        primary_role, support_roles, confidence = self._DOMAIN_ROLES[domain]
        return RoutePrediction(
            domain=domain,
            primary_role=primary_role,
            support_roles=support_roles,
            confidence=confidence,
            model_hash=self.model_hash,
            source="baseline_fallback",
        )

    def route(self, text: str) -> RoutePrediction:
        return self.predict(text)

    def _classify(self, text: str) -> str:
        query = str(text).lower()
        scores: dict[str, int] = {}
        for domain, keywords in self._KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in query)
            if score:
                scores[domain] = score
        if not scores:
            return "general"
        return max(scores, key=scores.get)


def _ensure_route_prediction(value: Any) -> RoutePrediction:
    if isinstance(value, RoutePrediction):
        return value
    if isinstance(value, dict):
        return RoutePrediction(
            domain=value.get("domain", "general"),
            primary_role=value.get("primary_role", "speech_output_transformer"),
            support_roles=tuple(value.get("support_roles", ())),
            confidence=float(value.get("confidence", 0.0)),
            model_hash=value.get("model_hash", _BaselineRouteModel.model_hash),
            source=value.get("source", "learned_route_model"),
        )
    raise TypeError("route model must return RoutePrediction")


def _is_repetitive(text: str, tokens: list[int]) -> bool:
    compact = "".join(text.split())
    if len(compact) >= 8 and len(set(compact)) <= 2:
        return True
    byte_tokens = [token for token in tokens if NovaByteTokenizer.BYTE_OFFSET <= token < NovaByteTokenizer.vocab_size]
    if len(byte_tokens) >= 8 and len(set(byte_tokens[-8:])) <= 2:
        return True
    return False


def _readable_prefix_before_junk(text: str) -> str:
    if not text:
        return text
    stop_at = len(text)
    for index, character in enumerate(text):
        if character == "\ufffd":
            stop_at = index
            break
        if ord(character) < 32 and character not in {"\n", "\r", "\t"}:
            stop_at = index
            break
        if not (character.isprintable() or character.isspace()):
            stop_at = index
            break
    if stop_at == len(text):
        return text
    prefix = text[:stop_at].strip()
    if _has_useful_readable_text(prefix):
        return prefix
    return text


def _has_useful_readable_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) < 4:
        return False
    alphanumeric_count = sum(1 for character in stripped if character.isalnum())
    return alphanumeric_count >= 3


def _is_unreadable(text: str) -> bool:
    if not text.strip():
        return True
    replacement_count = text.count("\ufffd")
    control_count = sum(
        1
        for character in text
        if ord(character) < 32 and character not in {"\n", "\r", "\t"}
    )
    if replacement_count >= 2 or control_count:
        return True
    visible_count = sum(1 for character in text if character.isprintable() or character.isspace())
    return visible_count / max(len(text), 1) < 0.9


def _assert_contracts() -> None:
    assert set(_BaselineRouteModel._DOMAIN_ROLES).issubset(set(DOMAIN_NAMES))
    for primary_role, support_roles, confidence in _BaselineRouteModel._DOMAIN_ROLES.values():
        assert primary_role in ROLE_NAMES
        assert all(role in ROLE_NAMES for role in support_roles)
        assert math.isfinite(confidence)


_assert_contracts()
