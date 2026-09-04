import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_reviewed_training import ReviewedTrainingStore, approve_reviewed_lesson, normalize_prompt


def test_normalization_handles_chat_shorthand_without_fuzzy_matching():
    assert normalize_prompt("  Do U love me?! ") == "do you love me"
    assert normalize_prompt("I'm tired.") == "i am tired"


def test_store_loads_only_explicitly_approved_lessons(tmp_path):
    path = tmp_path / "reviewed.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "id": "approved",
                        "approved": True,
                        "aliases": ["hello there"],
                        "response": "Hey.",
                    },
                    {
                        "id": "raw-feedback",
                        "approved": False,
                        "aliases": ["bad grammar"],
                        "response": "Do not load me.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    store = ReviewedTrainingStore(path)

    assert store.lookup("Hello there!").response == "Hey."
    assert store.lookup("bad grammar") is None
    assert store.health_check()["lesson_count"] == 1


def test_store_does_not_fuzzy_match_unrelated_prompt(tmp_path):
    path = tmp_path / "reviewed.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "id": "war",
                        "approved": True,
                        "aliases": ["what do you think about war"],
                        "response": "A nuanced answer.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    store = ReviewedTrainingStore(path)

    assert store.lookup("What do you think about War?").response == "A nuanced answer."
    assert store.lookup("What do you think about warming food?") is None


def test_invalid_schema_fails_closed(tmp_path):
    path = tmp_path / "reviewed.json"
    path.write_text('{"schema_version":"99","entries":[]}', encoding="utf-8")
    store = ReviewedTrainingStore(path)

    assert store.lookup("anything") is None
    health = store.health_check()
    assert health["ok"] is False
    assert health["alias_count"] == 0


def test_approval_updates_existing_alias_instead_of_creating_conflict(tmp_path):
    path = tmp_path / "reviewed.json"
    first = approve_reviewed_lesson(
        path,
        lesson_id="first",
        prompt="Another one",
        response="First approved reply.",
    )
    second = approve_reviewed_lesson(
        path,
        lesson_id="second",
        prompt="Another one!",
        response="Updated approved reply.",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert first["id"] == "first"
    assert second["id"] == "first"
    assert len(payload["entries"]) == 1
    assert ReviewedTrainingStore(path).lookup("another one").response == "Updated approved reply."


def test_approval_can_add_explicit_variations_without_fuzzy_matching(tmp_path):
    path = tmp_path / "reviewed.json"
    lesson = approve_reviewed_lesson(
        path,
        lesson_id="tired-support",
        prompt="I feel worn out",
        response="Let's slow down and handle one small thing.",
        aliases=[
            "I am exhausted",
            "I'm feeling drained",
        ],
    )
    store = ReviewedTrainingStore(path)

    assert len(lesson["aliases"]) == 3
    assert store.lookup("I AM EXHAUSTED!").response.startswith("Let's slow down")
    assert store.lookup("I'm feeling drained.").lesson_id == "tired-support"
    assert store.lookup("I drained the pool") is None
    assert store.health_check()["matcher_version"] == "1.1"


def test_alias_collision_fails_before_replacing_the_valid_store(tmp_path):
    path = tmp_path / "reviewed.json"
    approve_reviewed_lesson(
        path,
        lesson_id="first",
        prompt="Hello Nova",
        response="First approved answer.",
    )
    before = path.read_text(encoding="utf-8")

    try:
        approve_reviewed_lesson(
            path,
            lesson_id="second",
            prompt="Good morning Nova",
            response="Second approved answer.",
            aliases=["Hello Nova"],
        )
    except ValueError as exc:
        assert "duplicate approved alias" in str(exc)
    else:
        raise AssertionError("conflicting aliases must fail closed")

    assert path.read_text(encoding="utf-8") == before
    store = ReviewedTrainingStore(path)
    assert store.lookup("Hello Nova").response == "First approved answer."
    assert store.lookup("Good morning Nova") is None
