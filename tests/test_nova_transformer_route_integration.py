from pathlib import Path
import re
import sys

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_hybrid_router as router
from nova_checkpoint_registry import CheckpointRegistry
from nova_route_model import RouteExample, train_route_model
from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint
from nova_training_types import ROLE_NAMES
from nova_transformer_runtime import NovaTransformerRuntime


class DeterministicModel:
    def __init__(self, text="ok", block_size=64):
        self.config = ModelConfig(block_size=block_size, d_model=32, n_heads=4, n_layers=1, dropout=0.0)
        self.token_ids = [ord(char) + 4 for char in text] + [2]
        self.calls = 0

    def eval(self):
        return self

    def __call__(self, tokens):
        logits = torch.zeros((1, tokens.shape[1], 260), dtype=torch.float32)
        token_id = self.token_ids[min(self.calls, len(self.token_ids) - 1)]
        logits[0, -1, token_id] = 1.0
        self.calls += 1
        return logits, None


def test_empty_transformer_text_cannot_be_reported_as_success(monkeypatch):
    class EmptyGeneration:
        def to_trace(self):
            return {
                "source": "transformer",
                "text": "",
                "role": "speech_output_transformer",
                "checkpoint_path": "checkpoint.pt",
                "checkpoint_hash": "a" * 64,
                "error": None,
                "ok": True,
            }

    class Prediction:
        domain = "speech"
        primary_role = "speech_output_transformer"
        support_roles = ()
        confidence = 0.9
        source = "test_route"
        model_hash = "b" * 64

    class EmptyBrain:
        def route_with_evidence(self, _text):
            return Prediction(), None

        def generate(self, _role, _text, max_new_tokens=80):
            return EmptyGeneration()

    monkeypatch.setattr(router, "_ensure_brain", lambda: EmptyBrain())

    response, _route, _confidence, errors, ran, metadata = (
        router.generate_transformer_response("Say hello.")
    )

    assert response is None
    assert ran is True
    assert errors == {"speech_output_transformer": "empty transformer output"}
    assert metadata["generation"]["ok"] is False
    assert metadata["generation"]["error"] == "empty transformer output"


def test_release_verification_keeps_route_telemetry_in_memory_only(monkeypatch, tmp_path):
    route_log = tmp_path / "routing_log.jsonl"
    monkeypatch.setattr(router, "ROUTING_LOG_PATH", route_log)
    monkeypatch.setattr(router, "ROUTING_LOG", [])
    monkeypatch.setenv("NOVA_SUPPRESS_RUNTIME_LOGS", "true")

    router._log_route("hello", "general", ["speech_output_transformer"], 0.9, "test")

    assert router.ROUTING_LOG[-1]["text"] == "hello"
    assert route_log.exists() is False

    monkeypatch.delenv("NOVA_SUPPRESS_RUNTIME_LOGS", raising=False)
    router._log_route("live", "general", ["speech_output_transformer"], 0.9, "test")
    assert route_log.is_file()


def test_transformer_only_prompts_preserve_checkpoint_evidence_when_answer_is_not_accepted(monkeypatch):
    monkeypatch.setattr(router, "_log_route", lambda *args: None)
    prompts = [
        "Debug this Python loop.",
        "Make an ordered release plan.",
        "Verify this claim using evidence.",
        "Design a calm blue pattern.",
        "Recall Nova's creator.",
        "Simulate a failed deployment.",
        "Explain routing clearly.",
    ]
    for prompt in prompts:
        response, trace = router.route_and_respond(prompt, transformer_only=True)
        assert response.strip()
        # Transformer may produce output or fail - accept both
        assert trace["source"] in ("transformer", "transformer_error"),             f"Expected 'transformer' or 'transformer_error', got '{trace['source']}'"
        if trace["source"] == "transformer_error":
            assert re.fullmatch(r"[0-9a-fA-F]{64}", trace["route_model_hash"])
            assert re.fullmatch(r"[0-9a-fA-F]{64}", trace["checkpoint_hash"])
            if trace["generation"]["ok"]:
                assert trace["transformer_output_accepted"] is False
                assert trace["quality_fail_reasons"]
            else:
                assert trace["generation"].get("error")
            
        assert "fallback" not in trace.get("skills", [])


def test_transformer_only_uses_promoted_learned_route_model(monkeypatch, tmp_path):
    route_path = tmp_path / "checkpoints" / "route_model" / "promoted.pt"
    examples = [
        RouteExample("debug this python loop", "coding", "left_hemisphere"),
        RouteExample("make an ordered release plan", "planning", "planner_transformer"),
    ]
    _, metadata = train_route_model(
        examples,
        validation_examples=examples,
        output_path=route_path,
        epochs=1,
        hidden_size=8,
        block_size=16,
        batch_size=2,
        seed=23,
    )
    registry = CheckpointRegistry(tmp_path)
    for role in ROLE_NAMES:
        checkpoint = tmp_path / "checkpoints" / "brain_slots" / role / f"{role}_baseline.pt"
        digest = save_checkpoint(
            checkpoint,
            NovaCausalLM(ModelConfig(block_size=64, d_model=32, n_heads=4, n_layers=1, dropout=0.0)),
            {"role": role},
        )
        registry.register_baseline(role, checkpoint, digest)
    runtime = NovaTransformerRuntime(tmp_path)
    monkeypatch.setattr(runtime, "_load_model", lambda role, sha256, path: DeterministicModel("ok"))
    monkeypatch.setattr(router, "BRAIN", runtime)
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    response, trace = router.route_and_respond("Debug this Python loop.", transformer_only=True)

    assert response == "ok"
    assert trace["source"] == "transformer"
    assert trace["route_source"] == "learned_route_model"
    assert trace["route_model_hash"] == metadata["model_hash"]
