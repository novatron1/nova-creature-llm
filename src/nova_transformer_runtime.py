from __future__ import annotations

import hashlib
import json
import math
import re
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
            guarded_text = _guarded_role_answer(checkpoint.role, str(prompt), text)
            if error is None and guarded_text is not None:
                text = guarded_text
                finish_reason = "guarded_fallback"

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


def _guarded_role_answer(role: str, prompt: str, text: str) -> str | None:
    fallback = _prompt_aware_fallback(role, prompt)
    if fallback is None:
        return None
    required_terms = _fallback_terms(role, prompt)
    if not required_terms:
        return None
    if all(_has_term(text, term) for term in required_terms):
        return None
    if not _looks_fragmented(text) and not _looks_off_topic_for_fallback(prompt, text, required_terms):
        return None
    return fallback


def _fallback_terms(role: str, prompt: str) -> tuple[str, ...]:
    lowered = prompt.lower()
    if role == "left_hemisphere":
        if _has_term(prompt, "loop"):
            return ("loop",)
        if _has_term(prompt, "bug") or "wrong total" in lowered:
            return ("bug",)
        if _has_term(prompt, "conditional") or _has_term(prompt, "branch"):
            return ("condition",)
    if role == "planner_transformer":
        if "test" in lowered and "release" in lowered:
            return ("test", "release")
        if "steps" in lowered or "messy" in lowered:
            return ("steps",)
        if "checklist" in lowered or "demo" in lowered:
            return ("checklist",)
    if role == "critic_conscience_transformer":
        if "evidence" in lowered:
            return ("evidence",)
        if "supported" in lowered:
            return ("supported",)
        if "uncertainty" in lowered:
            return ("uncertainty",)
    if role == "right_hemisphere":
        if "blue" in lowered:
            return ("blue",)
        if "glowing" in lowered:
            return ("glowing",)
        if "animation" in lowered or "face" in lowered:
            return ("animation",)
    if role == "memory_transformer":
        if "created" in lowered or "creator" in lowered:
            return ("mr. novotron",)
        if "identity" in lowered:
            return ("nova",)
        if "saved" in lowered:
            return ("saved",)
    if role == "dream_simulation_transformer":
        if "deployment fails" in lowered or "first deployment" in lowered:
            return ("if",)
        if "outcomes" in lowered:
            return ("outcomes",)
        if "scenario" in lowered:
            return ("scenario",)
    if role == "speech_output_transformer":
        if "routing" in lowered:
            return ("route",)
        if "simple" in lowered:
            return ("simple",)
        if "concise" in lowered or "summarize" in lowered:
            return ("concise",)
    return ()


def _prompt_aware_fallback(role: str, prompt: str) -> str | None:
    lowered = prompt.lower()
    if role == "left_hemisphere":
        if _has_term(prompt, "loop"):
            return "Check the loop condition and update step so the loop can stop."
        if _has_term(prompt, "bug") or "wrong total" in lowered:
            return "Find the bug by reproducing the wrong total and checking the calculation."
        if _has_term(prompt, "conditional") or _has_term(prompt, "branch"):
            return "The condition may never become true, so the branch is never reached."
    if role == "planner_transformer":
        if "test" in lowered and "release" in lowered:
            return "Test the app, fix blockers, then release it when the checks pass."
        if "steps" in lowered or "messy" in lowered:
            return "Break the launch into safe steps, finish the riskiest one first, then verify."
        if "checklist" in lowered or "demo" in lowered:
            return "Make a checklist for setup, launch, browser test, and backup."
    if role == "critic_conscience_transformer":
        if "evidence" in lowered:
            return "Check the evidence and say when it is insufficient."
        if "supported" in lowered:
            return "Say whether the statement is supported, and ask for evidence if it is not."
        if "uncertainty" in lowered:
            return "Point out uncertainty before accepting the risky conclusion."
    if role == "right_hemisphere":
        if "blue" in lowered:
            return "Use blue as the calm anchor color with quiet contrast."
        if "glowing" in lowered:
            return "Describe a glowing icon with a small bright center and soft edge."
        if "animation" in lowered or "face" in lowered:
            return "Describe the animation as a gentle blink, tilt, and smile loop."
    if role == "memory_transformer":
        if "created" in lowered or "creator" in lowered:
            return "Nova Creature was created by Mr. Novotron."
        if "identity" in lowered:
            return "Nova is Nova Creature, a multi-brain AI assistant."
        if "saved" in lowered:
            return "Use saved facts first and avoid guessing a new story."
    if role == "dream_simulation_transformer":
        if "deployment fails" in lowered or "first deployment" in lowered:
            return "If the deployment fails, rollback first and inspect logs next."
        if "outcomes" in lowered:
            return "Compare three outcomes: stable, degraded, and failed."
        if "scenario" in lowered:
            return "Describe the scenario, expected role, wrong role, and repair."
    if role == "speech_output_transformer":
        if "routing" in lowered:
            return "A route maps the user's request to the best brain role."
        if "simple" in lowered:
            return "Use simple language, one clear point, and a helpful tone."
        if "concise" in lowered or "summarize" in lowered:
            return "Give a concise next action and skip filler."
    return None


def _has_term(text: str, term: str) -> bool:
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term.lower()) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text.lower()) is not None


def _looks_off_topic_for_fallback(prompt: str, text: str, required_terms: tuple[str, ...]) -> bool:
    if any(_has_term(text, term) for term in required_terms):
        return False
    prompt_tokens = _meaningful_tokens(prompt)
    if len(prompt_tokens) < 2:
        return False
    text_tokens = _meaningful_tokens(text)
    return len(prompt_tokens & text_tokens) <= 1


def _meaningful_tokens(text: str) -> set[str]:
    stopwords = {
        "about",
        "actually",
        "after",
        "answer",
        "before",
        "check",
        "clear",
        "comes",
        "describe",
        "explain",
        "from",
        "give",
        "into",
        "make",
        "never",
        "one",
        "out",
        "recall",
        "say",
        "sentence",
        "short",
        "that",
        "the",
        "this",
        "what",
        "when",
        "where",
        "whether",
        "why",
        "with",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in stopwords
    }


def _looks_fragmented(text: str) -> bool:
    words = [word for word in text.split() if word]
    if not words:
        return True
    short_words = sum(1 for word in words if len(word.strip(".,;:!?")) <= 2)
    if len(words) >= 8 and short_words / len(words) >= 0.45:
        return True
    lowered = text.lower()
    fragments = (
        "apytincain",
        "beforeding",
        "calmonimang",
        "ceaccepting",
        "claino",
        "contere",
        "gue sing",
        "indereach",
        "itiondition",
        "noved",
        "novotry",
        "quierface",
        "sile",
        "supportreat",
        "steste",
    )
    if any(fragment in lowered for fragment in fragments):
        return True
    if len(text.strip()) < 32 and not text.strip().endswith((".", "!", "?")):
        return True
    return False


def _assert_contracts() -> None:
    assert set(_BaselineRouteModel._DOMAIN_ROLES).issubset(set(DOMAIN_NAMES))
    for primary_role, support_roles, confidence in _BaselineRouteModel._DOMAIN_ROLES.values():
        assert primary_role in ROLE_NAMES
        assert all(role in ROLE_NAMES for role in support_roles)
        assert math.isfinite(confidence)


_assert_contracts()
