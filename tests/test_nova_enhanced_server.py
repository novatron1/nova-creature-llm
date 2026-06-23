from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nova_enhanced_server as server


HASH_A = "a" * 64
HASH_B = "b" * 64


def test_chat_payload_accepts_message_field():
    assert server._chat_text_from_body({"message": "Help me debug a Python loop"}) == "Help me debug a Python loop"


def test_chat_payload_preserves_present_text_over_message():
    assert server._chat_text_from_body({"text": "", "message": "fallback"}) == ""


def test_brain_route_exposes_transformer_evidence_from_hybrid_router(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(
        server,
        "pipeline_process",
        lambda text, memory, dict_lookup_fn: {
            "fast_path": False,
            "normalized_text": text,
            "intent": {"primary_intent": "coding_help"},
            "route": ["left_hemisphere", "planner_transformer"],
            "confidence": 0.95,
            "memory_binding": {},
        },
    )

    def fake_route_and_respond(text, dict_lookup_fn=None, memory=None):
        return (
            "Use a loop.",
            {
                "source": "transformer",
                "roles": ["left_hemisphere", "planner_transformer"],
                "route_path": ["left_hemisphere", "planner_transformer"],
                "domain": "coding",
                "skills": ["generated_coding", "transformer_inference"],
                "confidence": 0.91,
                "route_model_hash": HASH_A,
                "checkpoint_hash": HASH_B,
                "generation": {"role": "left_hemisphere", "ok": True},
            },
        )

    monkeypatch.setattr(server, "route_and_respond", fake_route_and_respond)
    response, trace = server.brain_route("Help me debug a Python loop")

    assert response == "Use a loop."
    assert trace["source"] == "transformer"
    assert trace["roles"] == ["left_hemisphere"]
    assert trace["route_path"] == ["left_hemisphere", "planner_transformer"]
    assert trace["route_model_hash"] == HASH_A
    assert trace["checkpoint_hash"] == HASH_B
