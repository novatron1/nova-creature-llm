from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.world_model import NovaWorldModel, WORLD_MODEL_SCHEMA_VERSION  # noqa: E402
from nova_protocol import NovaGenerationOptions, NovaMessage, NovaRequest, NovaResponse  # noqa: E402


def make_request(**overrides) -> NovaRequest:
    values = {
        "request_id": "req_world_1",
        "user_id": "user_one",
        "client_id": "phone_one",
        "conversation_id": "conv_relationship",
        "session_id": "session_phone",
        "messages": [NovaMessage(role="user", content="What should I say to my girlfriend?")],
        "generation_options": NovaGenerationOptions(model="nova"),
        "privacy_mode": "local_only",
        "metadata": {
            "desktop_context": {
                "sensor_snapshot": {
                    "enabled": True,
                    "source": "phone",
                    "battery": {"level": 0.8},
                    "location": {"latitude": 39.1, "longitude": -84.5},
                    "permissions": {"camera": False, "speaker": True},
                    "userAgent": "private browser fingerprint",
                }
            }
        },
    }
    values.update(overrides)
    return NovaRequest(**values)


def test_world_model_tracks_operational_state_without_copying_sensor_secrets():
    model = NovaWorldModel()
    request = make_request()
    routing = {
        "requested_alias": "nova",
        "selected_provider": "existing-nova",
        "selected_model": "nova-core",
        "remains_local": True,
        "fallback_path": [],
    }

    started = model.begin_turn(request, routing)

    assert started["status"] == "working"
    assert started["current_topic"] == "relationship"
    assert started["active_goal"] == "Give concrete, respectful relationship guidance"
    assert "girlfriend" in started["active_people"]
    assert {"battery", "location"} <= set(started["device_channels"])

    response = NovaResponse(
        request_id=request.request_id,
        conversation_id=request.conversation_id,
        model="nova",
        provider="existing-nova",
        content="Tell her honestly and give her room to respond.",
        metadata={
            "latency_ms": 8.0,
            "trace": {"source": "relationship_coaching", "final_answer_source": "relationship_coaching"},
            "routing": routing,
        },
    )
    completed = model.complete_turn(request, response)
    snapshot = model.view("phone_one", "conv_relationship")["data"]

    assert completed["status"] == "idle"
    assert completed["goal_status"] == "completed"
    assert completed["route_state"]["answer_source"] == "relationship_coaching"
    assert snapshot["schema_version"] == WORLD_MODEL_SCHEMA_VERSION
    assert snapshot["device_context"]["permissions"] == {"camera": False, "speaker": True}
    assert "latitude" not in str(snapshot)
    assert "longitude" not in str(snapshot)
    assert "fingerprint" not in str(snapshot)
    assert snapshot["privacy_mode"] == "local_only"


def test_world_model_isolates_clients_and_records_unresolved_failures():
    model = NovaWorldModel()
    request = make_request(
        request_id="req_failed",
        messages=[NovaMessage(role="user", content="Can you finish this difficult task?")],
    )
    model.begin_turn(
        request,
        {
            "requested_alias": "nova",
            "selected_provider": "existing-nova",
            "selected_model": "nova-core",
            "remains_local": True,
        },
    )

    failed = model.fail_turn(request, "provider_unavailable")

    assert failed["status"] == "error"
    assert failed["unresolved_count"] == 1
    own = model.view("phone_one", "conv_relationship")["data"]
    other = model.view("different_client", "conv_relationship")["data"]
    assert own["unresolved_questions"][0]["text"] == "Can you finish this difficult task?"
    assert own["last_error_category"] == "provider_unavailable"
    assert other is None
    assert model.health_check()["private_chain_of_thought_stored"] is False


def test_world_model_checkpoint_survives_restart_without_persisting_private_content(tmp_path: Path):
    checkpoint = tmp_path / "world-model.json"
    model = NovaWorldModel(persistence="checkpoint", checkpoint_path=checkpoint)
    request = make_request(
        messages=[
            NovaMessage(
                role="user",
                content="Remember this secret prompt while helping my girlfriend: PRIVATE-123",
            )
        ],
        session_id="private-session-id",
        user_id="private-user-id",
    )
    routing = {
        "requested_alias": "nova",
        "selected_provider": "existing-nova",
        "selected_model": "nova-core",
        "remains_local": True,
        "fallback_path": ["existing-nova"],
    }
    model.begin_turn(request, routing)
    model.fail_turn(request, "provider_unavailable")

    raw = checkpoint.read_text(encoding="utf-8")
    restored = NovaWorldModel(persistence="checkpoint", checkpoint_path=checkpoint)
    state = restored.view("phone_one", "conv_relationship")["data"]

    assert state["turn_count"] == 1
    assert state["current_topic"] == "relationship"
    assert state["goal_status"] == "needs_followup"
    assert state["last_error_category"] == "provider_unavailable"
    assert state["unresolved_questions"][0]["text"] == "Follow-up needed from a previous session"
    assert "PRIVATE-123" not in raw
    assert "private-session-id" not in raw
    assert "private-user-id" not in raw
    assert "latitude" not in raw
    assert "longitude" not in raw
    assert "fingerprint" not in raw
    assert json.loads(raw)["privacy"]["private_chain_of_thought_stored"] is False
    assert restored.health_check()["checkpoint_loaded_conversations"] == 1


def test_world_model_checkpoint_migrates_legacy_records_and_expires_old_state(tmp_path: Path):
    checkpoint = tmp_path / "world-model.json"
    now = datetime.now(timezone.utc)
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "boards": [
                    {
                        "client_id": "phone",
                        "conversation_id": "fresh",
                        "current_topic": "coding",
                        "active_goal": "Repair the app",
                        "goal_status": "completed",
                        "turn_count": 7,
                        "unresolved_questions": [{"text": "legacy prompt must not load"}],
                        "unresolved_count": 1,
                        "route_state": {
                            "provider": "existing-nova",
                            "answer_source": "cognitive_os",
                            "private_reasoning": "must not load",
                        },
                        "updated_at": now.isoformat(),
                    },
                    {
                        "client_id": "phone",
                        "conversation_id": "expired",
                        "turn_count": 99,
                        "updated_at": (now - timedelta(days=60)).isoformat(),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    restored = NovaWorldModel(
        persistence="checkpoint",
        checkpoint_path=checkpoint,
        max_age_days=30,
    )
    fresh = restored.view("phone", "fresh")["data"]

    assert fresh["turn_count"] == 7
    assert fresh["unresolved_questions"][0]["text"] == "Follow-up needed from a previous session"
    assert "private_reasoning" not in fresh["route_state"]
    assert restored.view("phone", "expired")["data"] is None
    assert restored.health_check()["checkpoint_expired_conversations"] == 1


def test_world_model_quarantines_corrupt_checkpoint_without_blocking_nova(tmp_path: Path):
    checkpoint = tmp_path / "world-model.json"
    checkpoint.write_text("{not-json", encoding="utf-8")

    restored = NovaWorldModel(persistence="checkpoint", checkpoint_path=checkpoint)
    health = restored.health_check()

    assert health["ok"] is True
    assert health["checkpoint_quarantined"] is True
    assert health["checkpoint_error"].startswith("invalid_checkpoint:")
    assert not checkpoint.exists()
    assert list(tmp_path.glob("world-model.json.corrupt-*"))
    assert restored.view("phone", "missing")["data"] is None


def test_world_model_serializes_simultaneous_checkpoint_writes(tmp_path: Path):
    checkpoint = tmp_path / "world-model.json"
    model = NovaWorldModel(
        maximum_conversations=32,
        persistence="checkpoint",
        checkpoint_path=checkpoint,
    )
    routing = {
        "requested_alias": "nova",
        "selected_provider": "existing-nova",
        "selected_model": "nova-core",
        "remains_local": True,
    }

    def finish_turn(index: int) -> None:
        request = make_request(
            request_id=f"req_concurrent_{index}",
            conversation_id=f"conversation_{index}",
            messages=[NovaMessage(role="user", content=f"Help with coding task {index}")],
        )
        model.begin_turn(request, routing)
        model.complete_turn(
            request,
            NovaResponse(
                request_id=request.request_id,
                conversation_id=request.conversation_id,
                model="nova",
                provider="existing-nova",
                content="Completed safely.",
                metadata={"routing": routing},
            ),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(finish_turn, range(16)))

    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    restored = NovaWorldModel(persistence="checkpoint", checkpoint_path=checkpoint)

    assert len(payload["boards"]) == 16
    assert restored.health_check()["checkpoint_loaded_conversations"] == 16
    assert restored.health_check()["checkpoint_error"] is None
    assert not checkpoint.with_suffix(".json.tmp").exists()


def test_world_model_import_is_explicit_and_reapplies_privacy_filter(tmp_path: Path):
    checkpoint = tmp_path / "imported-world-model.json"
    model = NovaWorldModel(persistence="checkpoint", checkpoint_path=checkpoint)
    result = model.import_checkpoint_payload(
        {
            "schema_version": "1.0",
            "boards": [
                {
                    "client_id": "phone_one",
                    "conversation_id": "portable_conversation",
                    "current_topic": "coding",
                    "active_goal": "PRIVATE PROMPT MUST NOT BECOME A GOAL",
                    "active_people": ["friend", "PRIVATE PERSON"],
                    "unresolved_count": 1,
                    "turn_count": 4,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "prompt": "PRIVATE IMPORTED PROMPT",
                    "response": "PRIVATE IMPORTED RESPONSE",
                }
            ],
        }
    )
    raw = checkpoint.read_text(encoding="utf-8")
    state = model.view("phone_one", "portable_conversation")["data"]

    assert result == {"ok": True, "imported": 1, "rejected": 0, "merge": True}
    assert state["turn_count"] == 4
    assert state["active_goal"] == "Continue the current conversation coherently"
    assert state["active_people"] == ["friend"]
    assert "PRIVATE" not in raw
