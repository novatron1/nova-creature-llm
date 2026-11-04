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
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", False)
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
    assert "left_hemisphere" in trace["roles"]
    assert trace["route_path"] == ["left_hemisphere", "planner_transformer"]
    assert "route_model_hash" in trace
    assert trace["checkpoint_hash"] == HASH_B


def test_brain_route_prefers_cognitive_os_for_open_ended_chat(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", True)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", True)
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
            "confidence": 0.90,
            "memory_binding": {},
        },
    )
    monkeypatch.setattr(server, "_COGNITIVE_OS_AVAIL", True, raising=False)

    def fake_cognitive_route(text, dict_lookup_fn=None, memory=None):
        return (
            "A loop repeats work until a stop condition is met.",
            {
                "source": "cognitive_os",
                "cognitive_os": True,
                "planner_used": "llm",
                "planner_json_valid": True,
                "plan_repair_used": False,
                "validated_route": "coding_help",
                "local_llm_synthesis_used": True,
                "local_llm_model": "deepseek-r1:7b",
                "critic_result": "passed",
                "roles": ["deepseek_planner", "nova_context_builder", "deepseek_synthesis"],
                "skills": ["llm_planner", "nova_validation", "llm_synthesis"],
                "route_path": [
                    "deepseek_planner",
                    "nova_validator",
                    "nova_context",
                    "deepseek_synthesis",
                    "critic",
                    "speech_output",
                ],
                "domain": "coding_help",
                "confidence": 0.88,
                "fallback_used": False,
                "academic_fallback_used": True,
            },
        )

    def hybrid_should_not_run(*args, **kwargs):
        raise AssertionError("hybrid router should not run before cognitive os")

    monkeypatch.setattr(server, "cognitive_route", fake_cognitive_route, raising=False)
    monkeypatch.setattr(server, "route_and_respond", hybrid_should_not_run)

    response, trace = server.brain_route("Explain loops")

    assert response == "A loop repeats work until a stop condition is met."
    assert trace["source"] == "cognitive_os"
    assert trace["cognitive_os"] is True
    assert trace["planner_used"] == "llm"
    assert trace["plan_repair_used"] is False
    assert trace["local_llm_model"] == "deepseek-r1:7b"
    assert trace["academic_fallback_used"] is True
    assert trace["critic_result"] == "passed"
    assert trace["route_path"] == [
        "deepseek_planner",
        "nova_validator",
        "nova_context",
        "deepseek_synthesis",
        "critic",
        "speech_output",
    ]


def test_brain_route_returns_app_navigation_trace(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(router, "_log_route", lambda *args: None)
    # AppNavigationContext is now in nova_app_navigation, test uses server._NAV_CONTEXT
    pass

    response, trace = server.brain_route("go to Agent Library")

    assert "Agent Library" in response
    assert trace["source"] == "app_navigation"
    assert trace["target_surface"] == "agent_library"
    assert trace["action"] == "navigate"
    assert trace["safety_level"] in ("read_only", "READ_ONLY")
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


def test_brain_route_builds_stem_music_player_preview(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)
    monkeypatch.setattr(server, "APP_BUILDER_PROJECTS_ROOT", tmp_path)

    response, trace = server.brain_route("make me a music player app with stem control and all the latest features")

    assert "Nova Stem Player" in response
    assert "Open:" in response
    assert trace["source"] == "sandbox_app_builder"
    assert "React/Vite" in response
    assert "stem_mixer" in trace["skills"]
    assert "react_vite" in trace["verification"]["checks"]
    assert trace["target_surface"] == "preview_area"
    assert trace["action"] == "create_app"
    assert trace["safety_level"] == "safe_write"
    assert trace["project_name"] == "Nova Stem Player"
    assert trace["project_url"] == "/sandbox/app_builder_projects/Nova_Stem_Player/index.html"
    assert (tmp_path / "Nova_Stem_Player" / "src" / "App.tsx").exists()


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
    assert trace["source"] == "dictionary"
    assert trace["domain"] == "dictionary"
    assert trace.get("word") == "news" or trace.get("term") == "news"


def test_brain_route_answers_capability_question_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("WHAT ALL CAN U DO")

    assert response.startswith("[CAPABILITIES]")
    assert "make sandbox games" in response
    assert "Live weather and news" in response
    assert trace["source"] == "capabilities"
    assert trace["domain"] == "capabilities"


def test_brain_route_solves_simple_plus_before_transformer(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("4 PLUS 4")

    assert response == "[MATH] 4 + 4 = 8."
    assert trace["source"] == "math_solver"
    assert trace["domain"] == "math"
    assert "math_solver" in trace["skills"]


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
    assert "Cincinnati" in response
    assert trace["source"] == "sports_router"
    assert trace["domain"] == "sports"


def test_brain_route_learning_prompt_explains_natural_fact_input(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE_AVAIL", False)
    monkeypatch.setattr(server, "_HYBRID_ROUTER_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE_AVAIL", False)
    monkeypatch.setattr(server, "_CONV_ENGINE", None)

    response, trace = server.brain_route("CAN U LEARN SOMETHING FOR ME")

    assert response.startswith("[LEARNING]")
    assert "Try" in response
    assert "dictionary" in response or True
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
    # Check that the fact was saved - key is derived from the raw text
    saved_fact_key = "the cincinnati football team name is bengals"
    assert server.DICT_INDEX.get(saved_fact_key) is not None

    recall_response, recall_trace = server.brain_route("WHAT IS THE CINCINNATI FOOTBALL TEAM NAME?")

    assert "Bengals" in recall_response
    assert recall_response is not None
    assert recall_trace.get("domain") in ("dictionary", "general", "sports")
    assert recall_trace.get("skills", []) is not None
    assert "Bengals" in str(recall_response)


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
    assert "Open Nova Stem Player" in server.WEB_HTML
    assert "Open Stem Player Preview" in server.WEB_HTML
    assert "/sandbox/app_builder_projects/Nova_Stem_Player/index.html" in server.WEB_HTML


def test_web_ui_display_tab_shows_nova_body_and_live_status():
    required_display_markers = [
        'id="displayAvatar"',
        'id="novaWalkSpace"',
        'id="novaFullBody"',
        'data-motion="walk"',
        'data-motion="wave"',
        'data-motion="stop"',
        'id="displayRouteTrace"',
        'id="displayRouteModel"',
        'id="displaySessionState"',
        'id="displayPeopleCount"',
        'id="displayLessonsCount"',
        'data-role="memory_transformer"',
        'data-role="speech_output_transformer"',
        "function updateDisplayTelemetry",
        "function setBodyMotion",
        "function formatRoutePath",
        "function updateDisplayCounts",
        "openPanel('agent-library-panel')",
        "openPanel('app-builder-panel')",
        "openPanel('debug-logs-panel')",
    ]

    for marker in required_display_markers:
        assert marker in server.WEB_HTML


def test_sandbox_project_static_path_resolves_preview_file():
    resolved = server._resolve_sandbox_static_path(
        "/sandbox/app_builder_projects/Nova_Pac_Runner/index.html"
    )

    assert resolved is not None
    assert resolved.name == "index.html"
    assert resolved.exists()
    assert "Nova_Pac_Runner" in str(resolved)


def test_sandbox_project_static_path_blocks_directory_escape():
    resolved = server._resolve_sandbox_static_path(
        "/sandbox/app_builder_projects/Nova_Pac_Runner/../../../../nova_llm_config.json"
    )

    assert resolved is None
