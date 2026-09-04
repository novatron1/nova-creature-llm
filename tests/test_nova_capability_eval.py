import base64
from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_capability_eval import (
    CAPABILITY_EVAL_SCHEMA_VERSION,
    CAPABILITY_PACK_VERSION,
    NovaCapabilityEvaluationStore,
    _score_json_equal,
    _score_even_json,
    _score_exact,
    evaluate_loaded_text_models,
    evaluate_user_approved_vision,
    qualify_text_model,
    qualification_text_cases,
)
from nova_protocol import NovaResponse


class _FakeProvider:
    def __init__(self):
        self.calls = []

    def generate(self, request):
        self.calls.append(request)
        answers = {
            "eval-instruction_exact": "NOVA_BLUE_417",
            "eval-continuity_codename": "ORBITAL_PINE_42",
            "eval-reasoning_power_budget": "17",
            "eval-coding_even_filter": '{"result":[2,4]}',
        }
        return NovaResponse(
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            model=request.generation_options.model,
            provider="ollama",
            content=answers[request.conversation_id],
        )


class _FakeRegistry:
    def __init__(self, provider):
        self.provider = provider

    def get_provider(self, provider_id):
        assert provider_id == "ollama"
        return self.provider


class _FakeUrlResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _tiny_png_base64():
    return base64.b64encode(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 48
    ).decode("ascii")


def test_capability_scorers_are_deterministic():
    assert _score_exact("17", " 17. ") == (1.0, "passed")
    assert _score_exact("17", "The answer is 17") == (0.0, "output_mismatch")
    assert _score_even_json('```json\n{"result":[2,4]}\n```') == (1.0, "passed")
    assert _score_even_json('{"result":["2","4"]}') == (0.0, "output_mismatch")
    assert _score_even_json("not json") == (0.0, "invalid_json")
    assert _score_json_equal({"ok": True}, '```json\n{"ok":true}\n```') == (
        1.0,
        "passed",
    )
    assert _score_json_equal([1, 2], "[1,2]") == (1.0, "passed")
    assert _score_json_equal({"ok": True}, '{"ok":"true"}') == (
        0.0,
        "output_mismatch",
    )


def test_middle_qualification_pack_is_bounded_balanced_and_unique():
    cases = qualification_text_cases()

    assert len(cases) == 20
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.capability for case in cases} == {
        "instruction_following",
        "conversation_continuity",
        "reasoning",
        "coding",
        "structured_output",
    }
    assert sum(case.capability == "reasoning" for case in cases) == 6
    assert all(1 <= case.max_tokens <= 64 for case in cases)


def test_capability_store_persists_only_content_free_scores(tmp_path):
    path = tmp_path / "capabilities.json"
    store = NovaCapabilityEvaluationStore(path)
    record = store.record(
        {
            "provider_id": "ollama",
            "model_id": "managed-test",
            "role": "primary",
            "prompt": "PRIVATE PROMPT",
            "output": "PRIVATE OUTPUT",
            "image_base64": "PRIVATE IMAGE",
            "capabilities": {
                "reasoning": {
                    "score": 1,
                    "passed": 1,
                    "total": 1,
                }
            },
        }
    )

    saved = path.read_text(encoding="utf-8")
    assert record["overall_score"] == 1
    assert CAPABILITY_PACK_VERSION in saved
    assert "PRIVATE PROMPT" not in saved
    assert "PRIVATE OUTPUT" not in saved
    assert "PRIVATE IMAGE" not in saved
    assert '"training_used": false' in saved
    assert '"raw_adapter_modes_excluded": true' in saved


def test_recommendations_require_repeated_evidence_and_never_change_routing(tmp_path):
    store = NovaCapabilityEvaluationStore(tmp_path / "capabilities.json")

    def record(model, score, latency=10):
        return store.record(
            {
                "provider_id": "ollama",
                "model_id": model,
                "role": "managed",
                "average_latency_ms": latency,
                "capabilities": {
                    "reasoning": {
                        "score": score,
                        "passed": int(score == 1),
                        "total": 1,
                    }
                },
            }
        )

    record("model-a", 0, 30)
    record("model-a", 1, 20)
    second = record("model-a", 1, 10)
    record("model-b", 1)
    record("model-b", 1)

    recommendations = store.status()["recommendations"]

    assert second["capabilities"]["reasoning"]["runs"] == 3
    assert second["capabilities"]["reasoning"]["score"] == pytest.approx(0.667)
    assert second["average_latency_ms"] == 20
    assert recommendations["status"] == "ready"
    assert recommendations["minimum_runs"] == 3
    assert recommendations["items"] == [
        {
            "task_type": "reasoning",
            "capability": "reasoning",
            "provider_id": "ollama",
            "model_id": "model-a",
            "score": pytest.approx(0.667),
            "runs": 3,
            "reason": "highest_repeated_local_capability_score",
            "alternatives_compared": 0,
        }
    ]
    assert recommendations["advisory_only"] is True
    assert recommendations["automatic_routing"] is False
    assert recommendations["training_used"] is False


def test_legacy_capability_records_migrate_to_one_evidence_run(tmp_path):
    path = tmp_path / "capabilities.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "records": {
                    "ollama/legacy": {
                        "provider_id": "ollama",
                        "model_id": "legacy",
                        "role": "primary",
                        "capabilities": {
                            "coding": {
                                "score": 1,
                                "passed": 1,
                                "total": 1,
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    status = NovaCapabilityEvaluationStore(path).status()
    capability = status["records"][0]["capabilities"]["coding"]

    assert status["schema_version"] == CAPABILITY_EVAL_SCHEMA_VERSION
    assert capability["runs"] == 1
    assert capability["last_score"] == 1
    assert status["recommendations"]["status"] == "collecting_evidence"


def test_shadow_recommendation_observes_evidence_without_changing_route(tmp_path):
    store = NovaCapabilityEvaluationStore(tmp_path / "capabilities.json")
    for _ in range(3):
        store.record(
            {
                "provider_id": "ollama",
                "model_id": "local-general",
                "role": "primary",
                "average_latency_ms": 20,
                "capabilities": {
                    "instruction_following": {
                        "score": 1,
                        "passed": 1,
                        "total": 1,
                    }
                },
            }
        )

    matched = store.shadow_recommendation("general")
    pending = store.shadow_recommendation("coding")

    assert matched["status"] == "evidence_match"
    assert matched["recommended_model"] == "local-general"
    assert matched["score"] == 1
    assert matched["runs"] == 3
    assert matched["automatic_routing"] is False
    assert matched["route_changed"] is False
    assert matched["training_used"] is False
    assert matched["content_logged"] is False
    assert pending["status"] == "insufficient_evidence"
    assert pending["recommended_model"] is None


def test_middle_tier_gate_enforces_only_full_repeated_pack_evidence(tmp_path):
    store = NovaCapabilityEvaluationStore(tmp_path / "capabilities.json")

    absent = store.middle_tier_qualification("ollama", "middle-test", "reasoning")
    assert absent["enforced"] is False
    assert absent["status"] == "not_evaluated"

    for _ in range(3):
        store.record(
            {
                "provider_id": "ollama",
                "model_id": "middle-test",
                "role": "middle",
                "capabilities": {
                    "instruction_following": {"score": 1, "passed": 4, "total": 4},
                    "conversation_continuity": {"score": 0.25, "passed": 1, "total": 4},
                    "reasoning": {"score": 0.667, "passed": 4, "total": 6},
                    "coding": {"score": 0.75, "passed": 3, "total": 4},
                    "structured_output": {"score": 1, "passed": 2, "total": 2},
                },
            }
        )

    rejected = store.middle_tier_qualification(
        "ollama",
        "middle-test",
        "reasoning",
    )
    assert rejected["enforced"] is True
    assert rejected["eligible"] is False
    assert rejected["status"] == "not_qualified"
    assert rejected["target_capability"] == "reasoning"
    assert rejected["content_logged"] is False


def test_loaded_text_evaluation_uses_provider_protocol_and_excludes_raw(
    monkeypatch,
    tmp_path,
):
    import nova_model_memory

    monkeypatch.setattr(
        nova_model_memory,
        "list_ollama_loaded_models",
        lambda: [
            {"name": "managed-test", "size_bytes": 100},
            {"name": "nova-dolphin3-lora", "size_bytes": 200},
        ],
    )
    monkeypatch.setattr(
        nova_model_memory,
        "configured_ollama_model_role",
        lambda model: "raw" if "dolphin" in model else "primary",
    )
    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **_kwargs: nullcontext({"allowed": True}),
    )
    provider = _FakeProvider()
    store = NovaCapabilityEvaluationStore(tmp_path / "capabilities.json")

    result = evaluate_loaded_text_models(
        _FakeRegistry(provider),
        store=store,
        maximum_models=3,
        timeout_seconds=5,
    )

    assert result["ok"] is True
    assert result["evaluated_models"] == 1
    assert len(provider.calls) == 4
    assert all(call.privacy_mode == "local_only" for call in provider.calls)
    assert all(call.api_source == "nova_capability_eval" for call in provider.calls)
    evaluated = next(item for item in result["results"] if item.get("status") == "evaluated")
    skipped = next(item for item in result["results"] if item.get("status") != "evaluated")
    assert evaluated["overall_score"] == 1
    assert evaluated["grade"] == "strong"
    assert skipped["status"] == "skipped_raw_user_model"
    assert result["raw_adapter_modes_excluded"] is True
    assert result["training_used"] is False


def test_specific_middle_qualification_requires_repeated_clean_evidence(
    monkeypatch,
    tmp_path,
):
    import nova_capability_eval
    import nova_model_memory

    cases = (
        nova_capability_eval.CapabilityEvalCase(
            "one",
            "instruction_following",
            (("user", "Return ONE"),),
            lambda output: _score_exact("ONE", output),
        ),
        nova_capability_eval.CapabilityEvalCase(
            "two",
            "conversation_continuity",
            (("user", "Return TWO"),),
            lambda output: _score_exact("TWO", output),
        ),
        nova_capability_eval.CapabilityEvalCase(
            "three",
            "reasoning",
            (("user", "Return THREE"),),
            lambda output: _score_exact("THREE", output),
        ),
        nova_capability_eval.CapabilityEvalCase(
            "four",
            "coding",
            (("user", "Return FOUR"),),
            lambda output: _score_exact("FOUR", output),
        ),
        nova_capability_eval.CapabilityEvalCase(
            "five",
            "structured_output",
            (("user", "Return FIVE"),),
            lambda output: _score_exact("FIVE", output),
        ),
    )
    monkeypatch.setattr(nova_capability_eval, "qualification_text_cases", lambda: cases)
    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **_kwargs: nullcontext({"allowed": True}),
    )

    class Provider:
        def list_models(self):
            return [
                SimpleNamespace(
                    model_id="middle-test",
                    metadata={"size": 2_000_000_000},
                )
            ]

        def generate(self, request):
            answer = {
                "eval-one": "ONE",
                "eval-two": "TWO",
                "eval-three": "THREE",
                "eval-four": "FOUR",
                "eval-five": "FIVE",
            }[request.conversation_id]
            return NovaResponse(
                request_id=request.request_id,
                conversation_id=request.conversation_id,
                model="middle-test",
                provider="ollama",
                content=answer,
            )

    result = qualify_text_model(
        _FakeRegistry(Provider()),
        model_id="middle-test",
        store=NovaCapabilityEvaluationStore(tmp_path / "capabilities.json"),
        repeated_runs=3,
        timeout_seconds=5,
    )

    assert result["status"] == "qualified"
    assert result["eligible_for_middle"] is True
    assert result["overall_score"] == 1
    assert result["attempted_cases"] == 15
    assert result["primary_model_changed"] is False
    assert result["route_changed"] is False
    assert result["content_logged"] is False
    assert len(result["runs"]) == 3


def test_user_approved_vision_discards_image_and_output(
    monkeypatch,
    tmp_path,
):
    import nova_capability_eval
    import nova_model_memory

    monkeypatch.setattr(
        nova_model_memory,
        "managed_model_residency",
        lambda *_args, **_kwargs: nullcontext({"allowed": True}),
    )
    monkeypatch.setattr(
        nova_model_memory,
        "configured_ollama_base_url",
        lambda: "http://127.0.0.1:11434",
    )
    monkeypatch.setattr(
        nova_capability_eval.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeUrlResponse(
            {"response": "A creature appears in a chat window."}
        ),
    )
    store_path = tmp_path / "capabilities.json"
    store = NovaCapabilityEvaluationStore(store_path)

    result = evaluate_user_approved_vision(
        model_id="vision-test",
        image_base64=_tiny_png_base64(),
        expected_keywords=["creature", "chat"],
        store=store,
        timeout_seconds=5,
    )

    assert result["ok"] is True
    assert result["passed"] is True
    assert result["score"] == 1
    assert result["image_persisted"] is False
    assert result["output_persisted"] is False
    saved = store_path.read_text(encoding="utf-8")
    assert _tiny_png_base64() not in saved
    assert "A creature appears" not in saved


@pytest.mark.parametrize(
    ("image", "keywords", "message"),
    [
        ("not-base64", ["thing"], "valid base64"),
        (_tiny_png_base64(), [], "at least one expected keyword"),
    ],
)
def test_vision_evaluation_validates_explicit_inputs(
    tmp_path,
    image,
    keywords,
    message,
):
    with pytest.raises(ValueError, match=message):
        evaluate_user_approved_vision(
            model_id="vision-test",
            image_base64=image,
            expected_keywords=keywords,
            store=NovaCapabilityEvaluationStore(tmp_path / "capabilities.json"),
        )
