from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_one_hundred_turns_grow_familiarity_without_personality_drift(tmp_path):
    from nova_companion.personality import stable_personality
    from nova_companion.service import CompanionService

    service = CompanionService(database=tmp_path / "memory.db")
    before = stable_personality()
    for index in range(100):
        turn = service.begin_turn(
            f"We are continuing project thread {index}",
            user_id="user-a",
            conversation_id=f"conv-{index % 2}",
            context={},
            decision=None,
        )
        service.finalize_turn(
            turn,
            "I remember the project thread.",
            {"source": "reviewed_conversation_response"},
        )

    after = service.store.load_state("user-a")
    assert after is not None
    assert after.interaction_count == 100
    assert 0.0 <= after.familiarity_score <= 1.0
    assert 0.0 <= after.trust_score <= 1.0
    assert stable_personality() == before


def test_persistence_survives_service_restart(tmp_path):
    from nova_companion.service import CompanionService

    database = tmp_path / "memory.db"
    first = CompanionService(database=database)
    turn = first.begin_turn(
        "We are building Nova together",
        user_id="user-a",
        conversation_id="conv-1",
        context={},
        decision=None,
    )
    first.finalize_turn(turn, "The project is still moving forward.", {"source": "reviewed_conversation_response"})

    second = CompanionService(database=database)
    state = second.store.load_state("user-a")
    assert state is not None
    assert state.interaction_count == 1
    assert second.store.health()["ok"] is True


def test_live_checker_reports_metrics_without_prompt_or_response_content(tmp_path):
    from tools.run_nova_companion_live_check import run_live_check

    class FakeTransport:
        def request(self, method, url, *, json_body=None, timeout_seconds=None):
            assert method == "POST"
            assert url.endswith("/api/chat")
            assert isinstance(json_body, dict)
            return type(
                "Response",
                (),
                {
                    "status": 200,
                    "latency_ms": 12,
                    "body": {
                        "content": "private answer that must not enter the report",
                        "metadata": {
                            "trace": {
                                "source": "local_llm",
                                "companion": {
                                    "enabled": True,
                                    "primary_mode": "companionship",
                                    "memory_count": 1,
                                },
                            }
                        },
                    },
                },
            )()

    output = tmp_path / "live.json"
    report = run_live_check(
        base_url="http://example.test",
        user_id="private-user",
        conversation_id="private-conversation",
        turns=2,
        transport=FakeTransport(),
        output_path=output,
        training_data_path=tmp_path / "missing-training.jsonl",
    )

    serialized = output.read_text(encoding="utf-8")
    assert report["summary"]["turns"] == 2
    assert report["cases"][0]["companion"]["primary_mode"] == "companionship"
    assert "private answer" not in serialized
    assert "private-user" not in serialized
    assert "private-conversation" not in serialized
