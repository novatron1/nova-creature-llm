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


def test_brain_route_handles_temperature_question_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server,
        "_fetch_weather_summary",
        lambda location: f"{location}: 72°F, feels like 74°F, clear.",
    )

    response, trace = server.brain_route("WHAT THE TEMP IN CINCINNATI")

    assert response == "[WEATHER] Cincinnati: 72°F, feels like 74°F, clear."
    assert trace["source"] == "weather_router"
    assert trace["domain"] == "weather"
    assert trace["location"] == "Cincinnati"
    assert "weather_lookup" in trace["skills"]


def test_brain_route_looks_up_news_before_memory_or_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(
        server,
        "_fetch_news_headlines",
        lambda query, limit=3: [
            {"title": "Cincinnati riverfront project advances", "source": "Local 12", "url": "https://example.test/riverfront"},
            {"title": "Reds announce community event", "source": "WCPO", "url": "https://example.test/reds"},
        ],
    )

    response, trace = server.brain_route("CAN U LOOK UP THE NEWS IN CINCINNATI")

    assert response.startswith("[NEWS] Latest Cincinnati headlines:")
    assert "Cincinnati riverfront project advances" in response
    assert "Reds announce community event" in response
    assert trace["source"] == "news_router"
    assert trace["domain"] == "news"
    assert trace["query"] == "Cincinnati"
    assert "news_lookup" in trace["skills"]


def test_brain_route_defines_news_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("WHAT DOES NEWS MEAN")

    assert response.startswith("[DEFINITION] News means")
    assert "recent events" in response
    assert trace["source"] == "definition_router"
    assert trace["domain"] == "definition"
    assert trace["term"] == "news"


def test_brain_route_answers_capability_question_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("WHAT ALL CAN U DO")

    assert response.startswith("[CAPABILITIES]")
    assert "make sandbox games" in response
    assert "look up live weather and news" in response
    assert trace["source"] == "capability_router"
    assert trace["domain"] == "capabilities"


def test_brain_route_solves_simple_plus_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("4 PLUS 4")

    assert response == "[MATH] 4 + 4 = 8."
    assert trace["source"] == "simple_math_router"
    assert trace["domain"] == "math"
    assert "arithmetic" in trace["skills"]


def test_brain_route_blocks_corrupt_transformer_output(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", True)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    def corrupt_route(text, dict_lookup_fn=None, memory=None):
        return (
            "\"b\u001f\ufffdvLN\ufffd\ufffd#P\ufffd{\u0012|\ufffd\ufffd",
            {
                "source": "transformer",
                "roles": ["speech_output_transformer", "memory_transformer"],
                "domain": "general",
                "skills": ["transformer_inference"],
                "confidence": 0.55,
            },
        )

    monkeypatch.setattr(server, "route_and_respond", corrupt_route)

    response, trace = server.brain_route("WHAT IS WAS THAT")

    assert response.startswith("[SAFE FALLBACK]")
    assert "couldn't produce a clean answer" in response
    assert trace["source"] == "safe_fallback"
    assert trace["blocked"] is True
    assert trace["blocker"] == "corrupt_transformer_output"


def test_brain_route_answers_cincinnati_football_team_question(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("WHAT IS CINCINNATI FOOTBALL TEAM CALL?")

    assert response.startswith("[SPORTS]")
    assert "Cincinnati Bengals" in response
    assert "FC Cincinnati" in response
    assert trace["source"] == "sports_fact_router"
    assert trace["domain"] == "sports"


def test_brain_route_learning_prompt_explains_natural_fact_input(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("CAN U LEARN SOMETHING FOR ME")

    assert response.startswith("[LEARNING]")
    assert "plain fact" in response
    assert "dictionary" in response
    assert trace["source"] == "learning_help_router"


def test_brain_route_learns_natural_fact_into_dictionary_and_recalls(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "DICT_PATH", str(tmp_path / "approved_answer_dictionary.json"))
    monkeypatch.setattr(server, "DICT_HITS_PATH", str(tmp_path / "dictionary_hits.jsonl"))
    monkeypatch.setattr(server, "DICT_INDEX", {})
    monkeypatch.setattr(server, "MEMORY_FILE", str(tmp_path / "nova_memory.json"))
    monkeypatch.setattr(server, "MEMORY", {"people": {}, "lessons": {}, "last_person": None})

    learned_response, learned_trace = server.brain_route("THE CINCINNATI FOOTBALL TEAM NAME IS BENGALS")

    assert learned_response.startswith("[LEARNING] Stored")
    assert learned_trace["source"] == "natural_fact_learning"
    assert learned_trace["domain"] == "dictionary"
    assert "dictionary_write" in learned_trace["skills"]
    assert server._dict_lookup("WHAT IS CINCINNATI FOOTBALL TEAM CALL?") == "The Cincinnati football team name is Bengals."

    recall_response, recall_trace = server.brain_route("WHAT IS CINCINNATI FOOTBALL TEAM CALL?")

    assert recall_response == "The Cincinnati football team name is Bengals."
    assert recall_trace["source"] == "dictionary"
    assert recall_trace["domain"] == "dictionary"
    assert recall_trace["memory_event"] == "dictionary_hit"


def test_web_ui_exposes_whole_app_surfaces():
    required_tabs = [
        "data-panel=\"home-panel\"",
        "data-panel=\"chat-panel\"",
        "data-panel=\"display-panel\"",
        "data-panel=\"agent-library-panel\"",
        "data-panel=\"app-builder-panel\"",
        "data-panel=\"memory-panel\"",
        "data-panel=\"tools-panel\"",
        "data-panel=\"research-panel\"",
        "data-panel=\"test-check-panel\"",
        "data-panel=\"saved-projects-panel\"",
        "data-panel=\"preview-panel\"",
        "data-panel=\"debug-logs-panel\"",
        "data-panel=\"scheduler-panel\"",
        "data-panel=\"file-manager-panel\"",
        "data-panel=\"settings-panel\"",
    ]

    for marker in required_tabs:
        assert marker in server.WEB_HTML

    assert "function openPanel" in server.WEB_HTML
    assert "Whole App Navigation" in server.WEB_HTML


def test_web_ui_display_tab_shows_nova_body_and_live_status():
    required_display_markers = [
        'id="displayAvatar"',
        'id="displayRouteTrace"',
        'id="displaySessionState"',
        'id="displayPeopleCount"',
        'id="displayLessonsCount"',
        'data-role="memory_transformer"',
        'data-role="speech_output_transformer"',
        "function updateDisplayTelemetry",
        "function updateDisplayCounts",
        "openPanel('agent-library-panel')",
        "openPanel('app-builder-panel')",
        "openPanel('debug-logs-panel')",
    ]

    for marker in required_display_markers:
        assert marker in server.WEB_HTML
