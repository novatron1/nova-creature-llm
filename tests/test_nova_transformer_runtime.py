from pathlib import Path
import json
import sys

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_checkpoint_registry import CheckpointRegistry
from nova_route_model import RouteExample, train_route_model
from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint
from nova_transformer_runtime import NovaTransformerRuntime, load_promoted_route_model
from nova_training_types import GenerationResult, RoutePrediction

HASH_A = "a" * 64
HASH_B = "b" * 64


class FixedRouteModel:
    model_hash = HASH_A

    def predict(self, text):
        return RoutePrediction("coding", "left_hemisphere", ("planner_transformer",), 0.91, self.model_hash)


class DeterministicModel:
    def __init__(self, text="ok", block_size=64):
        self.config = ModelConfig(block_size=block_size, d_model=32, n_heads=4, n_layers=1, dropout=0.0)
        self.token_ids = [ord(char) + 4 for char in text]
        self.calls = 0

    def eval(self):
        return self

    def __call__(self, tokens):
        logits = torch.zeros((1, tokens.shape[1], 260), dtype=torch.float32)
        token_id = self.token_ids[min(self.calls, len(self.token_ids) - 1)]
        logits[0, -1, token_id] = 1.0
        self.calls += 1
        return logits, None


class ExplodingRouteModel:
    model_hash = HASH_A

    def predict(self, text):
        raise RuntimeError("route boom")


def _register_left_checkpoint(tmp_path):
    path = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "left_hemisphere_baseline.pt"
    digest = save_checkpoint(
        path,
        NovaCausalLM(ModelConfig(block_size=64, d_model=32, n_heads=4, n_layers=1, dropout=0.0)),
        {"role": "left_hemisphere"},
    )
    CheckpointRegistry(tmp_path).register_baseline("left_hemisphere", path, digest)
    return path, digest


def test_runtime_returns_generation_evidence(tmp_path):
    _, digest = _register_left_checkpoint(tmp_path)
    runtime = NovaTransformerRuntime(tmp_path, route_model=FixedRouteModel())
    route = runtime.route("debug this code")
    result = runtime.generate(route.primary_role, "debug this code", max_new_tokens=4)
    assert route.source == "learned_route_model"
    assert result.role == "left_hemisphere"
    assert result.checkpoint_hash == digest
    assert result.to_trace()["source"] == "transformer"


def test_runtime_success_result_is_ok_and_non_empty_with_controlled_model(tmp_path, monkeypatch):
    _, digest = _register_left_checkpoint(tmp_path)
    runtime = NovaTransformerRuntime(tmp_path, route_model=FixedRouteModel())
    monkeypatch.setattr(runtime, "_load_model", lambda role, sha256, path: DeterministicModel("ok"))

    result = runtime.generate("left_hemisphere", "debug this code", max_new_tokens=2)

    assert result.ok is True
    assert result.text == "ok"
    assert result.checkpoint_hash == digest
    assert result.to_trace()["ok"] is True


def test_runtime_failure_after_resolve_preserves_checkpoint_evidence(tmp_path, monkeypatch):
    _, digest = _register_left_checkpoint(tmp_path)
    runtime = NovaTransformerRuntime(tmp_path, route_model=FixedRouteModel())

    def explode_after_resolve(role, sha256, path):
        raise RuntimeError("model load exploded")

    monkeypatch.setattr(runtime, "_load_model", explode_after_resolve)

    result = runtime.generate("left_hemisphere", "debug this code", max_new_tokens=2)

    assert result.ok is False
    assert result.checkpoint_hash == digest
    assert result.checkpoint_path == "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt"
    assert "model load exploded" in result.error
    assert result.to_trace()["checkpoint_hash"] == digest


def test_runtime_rejects_prompt_too_long_to_keep_sep(tmp_path, monkeypatch):
    _, digest = _register_left_checkpoint(tmp_path)
    runtime = NovaTransformerRuntime(tmp_path, route_model=FixedRouteModel())
    monkeypatch.setattr(runtime, "_load_model", lambda role, sha256, path: DeterministicModel("ok", block_size=6))

    result = runtime.generate("left_hemisphere", "abcdef", max_new_tokens=1)

    assert result.ok is False
    assert result.checkpoint_hash == digest
    assert "prompt too long" in result.error


def test_route_model_exception_falls_back_with_error_provenance(tmp_path):
    runtime = NovaTransformerRuntime(tmp_path, route_model=ExplodingRouteModel())

    route = runtime.route("debug this code")

    assert route.source == "baseline_fallback"
    assert runtime.last_route_error == "route boom"


def test_unpromoted_route_model_file_is_not_loaded_as_live_router(tmp_path):
    stale_path = tmp_path / "checkpoints" / "route_model" / "route_model.pt"
    _write_route_classifier(stale_path)

    model = load_promoted_route_model(tmp_path)
    route = model.predict("debug this python code")

    assert route.source == "baseline_fallback"


def test_corrupt_promoted_route_model_falls_back_with_load_error(tmp_path):
    promoted_path = tmp_path / "checkpoints" / "route_model" / "promoted.pt"
    promoted_path.parent.mkdir(parents=True)
    promoted_path.write_bytes(b"not a valid route model")

    runtime = NovaTransformerRuntime(tmp_path)
    route, route_error = runtime.route_with_evidence("debug this code")

    assert route.source == "baseline_fallback"
    assert "promoted route model failed to load" in route_error


def test_route_with_evidence_returns_error_without_shared_runtime_state(tmp_path):
    runtime = NovaTransformerRuntime(tmp_path, route_model=ExplodingRouteModel())

    route, route_error = runtime.route_with_evidence("debug this code")

    assert route.source == "baseline_fallback"
    assert route_error == "route boom"
    assert runtime.last_route_error is None


def test_hybrid_success_trace_is_json_safe_and_exposes_route_provenance(monkeypatch):
    import nova_hybrid_router as router

    prediction = RoutePrediction(
        "coding",
        "left_hemisphere",
        ("left_hemisphere", "planner_transformer"),
        0.91,
        HASH_A,
        source="baseline_fallback",
    )
    generation = GenerationResult(
        "fixed",
        "left_hemisphere",
        "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt",
        HASH_B,
        2,
        0.1,
        20.0,
        "length",
    )

    class FakeBrain:
        last_route_error = None

        def route(self, text):
            return prediction

        def generate(self, role, text, max_new_tokens=80):
            return generation

    monkeypatch.setattr(router, "BRAIN", FakeBrain())
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    response, trace = router.route_and_respond("debug this code")

    assert response == "fixed"
    assert trace["source"] == "transformer"
    assert trace["route_source"] == "baseline_fallback"
    assert trace["route_model_hash"] == HASH_A
    assert trace["checkpoint_hash"] == HASH_B
    assert trace["checkpoint_path"] == "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt"
    assert trace["generation"]["ok"] is True
    assert trace["roles"] == ["left_hemisphere", "planner_transformer"]
    json.dumps(trace)


def test_transformer_only_skips_dictionary_and_memory_and_returns_transformer_error(monkeypatch):
    import nova_hybrid_router as router

    prediction = RoutePrediction("coding", "left_hemisphere", (), 0.8, HASH_A)
    generation = GenerationResult(
        "",
        "left_hemisphere",
        "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt",
        HASH_B,
        0,
        0.1,
        0.0,
        "error",
        "generation boom",
    )

    class FakeBrain:
        last_route_error = None

        def route(self, text):
            return prediction

        def generate(self, role, text, max_new_tokens=80):
            return generation

    dictionary_calls = []

    def dict_lookup(text):
        dictionary_calls.append(text)
        return "dictionary answer"

    memory = {"lessons": {"1": {"text": "debug code lesson stored in memory"}}}
    monkeypatch.setattr(router, "BRAIN", FakeBrain())
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    response, trace = router.route_and_respond(
        "debug code",
        dict_lookup_fn=dict_lookup,
        memory=memory,
        transformer_only=True,
    )

    assert dictionary_calls == []
    assert "Transformer generation failed" in response
    assert trace["source"] == "transformer_error"
    assert trace["route_source"] == "learned_route_model"
    assert trace["generation"]["error"] == "generation boom"
    assert trace["memory_event"] == "transformer_failed"


def test_non_transformer_fallback_keeps_attempted_transformer_failure_evidence(monkeypatch):
    import nova_hybrid_router as router

    prediction = RoutePrediction("coding", "left_hemisphere", (), 0.8, HASH_A)
    generation = GenerationResult(
        "",
        "left_hemisphere",
        "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt",
        HASH_B,
        0,
        0.1,
        0.0,
        "error",
        "generation boom",
    )

    class FakeBrain:
        last_route_error = "route degraded"

        def route(self, text):
            return prediction

        def generate(self, role, text, max_new_tokens=80):
            return generation

    monkeypatch.setattr(router, "BRAIN", FakeBrain())
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    response, trace = router.route_and_respond("debug code")

    assert response
    assert trace["source"] == "fallback"
    assert trace["route_source"] == "learned_route_model"
    assert trace["route_error"] == "route degraded"
    assert trace["generation"]["error"] == "generation boom"
    assert trace["checkpoint_hash"] == HASH_B


def test_route_error_is_captured_per_call_before_shared_state_changes(monkeypatch):
    import nova_hybrid_router as router

    first_prediction = RoutePrediction("coding", "left_hemisphere", (), 0.8, HASH_A)
    second_prediction = RoutePrediction("science", "memory_transformer", (), 0.7, HASH_A)
    generation = GenerationResult(
        "",
        "left_hemisphere",
        "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt",
        HASH_B,
        0,
        0.1,
        0.0,
        "error",
        "generation boom",
    )

    class FakeBrain:
        last_route_error = None

        def __init__(self):
            self.calls = 0

        def route_with_evidence(self, text):
            self.calls += 1
            if self.calls == 1:
                self.last_route_error = "shared state overwritten after first route"
                return first_prediction, "route error A"
            return second_prediction, "route error B"

        def generate(self, role, text, max_new_tokens=80):
            if text == "first request":
                self.route_with_evidence("second request")
            return generation

    monkeypatch.setattr(router, "BRAIN", FakeBrain())
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    response, trace = router.route_and_respond("first request", transformer_only=True)

    assert "Transformer generation failed" in response
    assert trace["route_error"] == "route error A"
    assert trace["domain"] == "coding"


def test_fallback_response_uses_prediction_domain_when_legacy_domain_differs(monkeypatch):
    import nova_hybrid_router as router

    prediction = RoutePrediction("science", "memory_transformer", (), 0.7, HASH_A)
    generation = GenerationResult(
        "",
        "memory_transformer",
        "checkpoints/brain_slots/memory_transformer/memory_transformer_baseline.pt",
        HASH_B,
        0,
        0.1,
        0.0,
        "error",
        "generation boom",
    )

    class FakeBrain:
        def route_with_evidence(self, text):
            return prediction, None

        def generate(self, role, text, max_new_tokens=80):
            return generation

    monkeypatch.setattr(router, "BRAIN", FakeBrain())
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    response, trace = router.route_and_respond("debug python code")

    assert "science training covers physics" in response
    assert "programming knowledge" not in response
    assert trace["domain"] == "science"


def test_app_navigation_commands_short_circuit_hybrid_router(monkeypatch):
    import nova_hybrid_router as router

    monkeypatch.setattr(router, "_log_route", lambda *args: None)
    dictionary_calls = []

    def dict_lookup(text):
        dictionary_calls.append(text)
        return "dictionary should not win"

    response, trace = router.route_and_respond(
        "go to Agent Library",
        dict_lookup_fn=dict_lookup,
        memory={"lessons": {"1": {"text": "Agent Library memory hit"}}},
    )

    assert dictionary_calls == []
    assert "Agent Library" in response
    assert trace["source"] == "app_navigation"
    assert trace["target_surface"] == "agent_library"
    assert trace["action"] == "navigate"


def test_generic_chat_still_uses_existing_transformer_path(monkeypatch):
    import nova_hybrid_router as router

    prediction = RoutePrediction("coding", "left_hemisphere", (), 0.8, HASH_A)
    generation = GenerationResult(
        "fixed",
        "left_hemisphere",
        "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt",
        HASH_B,
        1,
        0.1,
        10.0,
        "length",
    )

    class FakeBrain:
        last_route_error = None

        def route_with_evidence(self, text):
            return prediction, None

        def generate(self, role, text, max_new_tokens=80):
            return generation

    monkeypatch.setattr(router, "BRAIN", FakeBrain())
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    response, trace = router.route_and_respond("help me debug python")

    assert response == "fixed"
    assert trace["source"] == "transformer"
    assert trace["domain"] == "coding"


def test_agent_question_is_not_hijacked_by_app_navigation(monkeypatch):
    import nova_hybrid_router as router

    prediction = RoutePrediction("coding", "left_hemisphere", (), 0.8, HASH_A)
    generation = GenerationResult(
        "normal answer",
        "left_hemisphere",
        "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt",
        HASH_B,
        2,
        0.1,
        20.0,
        "length",
    )

    class FakeBrain:
        last_route_error = None

        def route_with_evidence(self, text):
            return prediction, None

        def generate(self, role, text, max_new_tokens=80):
            return generation

    monkeypatch.setattr(router, "BRAIN", FakeBrain())
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    response, trace = router.route_and_respond("can you explain how to make an agent in Python?")

    assert response == "normal answer"
    assert trace["source"] == "transformer"


def test_generic_verify_after_navigation_uses_transformer_path(monkeypatch):
    import nova_hybrid_router as router

    prediction = RoutePrediction("critic", "critic_conscience_transformer", (), 0.82, HASH_A)
    generation = GenerationResult(
        "evidence answer",
        "critic_conscience_transformer",
        "checkpoints/brain_slots/critic_conscience_transformer/critic_conscience_transformer_baseline.pt",
        HASH_B,
        3,
        0.1,
        30.0,
        "length",
    )

    class FakeBrain:
        last_route_error = None

        def route_with_evidence(self, text):
            return prediction, None

        def generate(self, role, text, max_new_tokens=80):
            return generation

    monkeypatch.setattr(router, "APP_NAV_CONTEXT", router.AppNavigationContext())
    monkeypatch.setattr(router, "BRAIN", FakeBrain())
    monkeypatch.setattr(router, "_log_route", lambda *args: None)

    _, nav_trace = router.route_and_respond("go to Agent Library", transformer_only=False)
    response, trace = router.route_and_respond("verify this claim using evidence", transformer_only=False)

    assert nav_trace["source"] == "app_navigation"
    assert response == "evidence answer"
    assert trace["source"] == "transformer"
    assert trace["domain"] == "critic"


def _write_route_classifier(path: Path) -> str:
    examples = [
        RouteExample("debug python code", "coding", "left_hemisphere"),
        RouteExample("make a release plan", "planning", "planner_transformer"),
    ]
    _, metadata = train_route_model(
        examples,
        validation_examples=examples,
        output_path=path,
        epochs=1,
        hidden_size=8,
        block_size=16,
        batch_size=2,
        seed=17,
    )
    return metadata["model_hash"]
