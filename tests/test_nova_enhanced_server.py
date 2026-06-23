from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nova_enhanced_server as server
import nova_hybrid_router as router


HASH_A = "a" * 64
HASH_B = "b" * 64


def test_chat_payload_accepts_message_field():
    assert server._chat_text_from_body({"message": "Help me debug a Python loop"}) == "Help me debug a Python loop"


def test_chat_payload_preserves_present_text_over_message():
    assert server._chat_text_from_body({"text": "", "message": "fallback"}) == ""


def test_brain_route_exposes_transformer_evidence_from_hybrid_router(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
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


def test_brain_route_returns_app_navigation_trace(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(router, "_log_route", lambda *args: None)
    monkeypatch.setattr(router, "APP_NAV_CONTEXT", router.AppNavigationContext())

    response, trace = server.brain_route("go to Agent Library")

    assert "Agent Library" in response
    assert trace["source"] == "app_navigation"
    assert trace["target_surface"] == "agent_library"
    assert trace["action"] == "navigate"
    assert trace["safety_level"] == "read_only"
    assert [step["kind"] for step in trace["steps"]] == ["understand", "navigate", "verify"]
    assert trace["verification"]["status"] == "planned"
    assert trace["verification"]["method"] == "structured_navigation_plan"


def test_brain_route_builds_pacman_game_preview(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)

    response, trace = server.brain_route("make a Pac-Man game that moves on its own and has scoring")

    assert "Nova Pac Runner" in response
    assert "Open:" in response
    assert trace["source"] == "sandbox_game_builder"
    assert "Three.js/WebGL" in response
    assert "three_webgl" in trace["skills"]
    assert "three_webgl" in trace["verification"]["checks"]
    assert trace["target_surface"] == "preview_area"
    assert trace["action"] == "create_game"
    assert trace["safety_level"] == "safe_write"
    assert trace["project_name"] == "Nova Pac Runner"
    assert trace["project_url"] == "/sandbox/app_builder_projects/Nova_Pac_Runner/index.html"
    assert (tmp_path / "Nova_Pac_Runner" / "index.html").exists()
