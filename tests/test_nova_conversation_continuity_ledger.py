from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_conversation_summary import (  # noqa: E402
    ConversationSummary,
    render_conversation_summary,
    roll_conversation_summary,
)
from nova_gateway.world_model import NovaWorldModel  # noqa: E402
from nova_gateway import GatewayConfig  # noqa: E402
from nova_gateway.core import NovaGatewayCore  # noqa: E402
from nova_protocol import NovaGenerationOptions, NovaMessage, NovaRequest  # noqa: E402


def test_summary_keeps_unanswered_question_commitment_and_emotional_context() -> None:
    history = [
        {
            "role": "user",
            "content": "Why did you say the Earth evidence was strong?",
        },
        {
            "role": "assistant",
            "content": "I'll explain the strongest checks next.",
        },
    ] * 6

    update = roll_conversation_summary(
        ConversationSummary(),
        history,
        "Okay",
        "Let's continue.",
        keep_recent_messages=4,
    )

    assert any("Why did you say" in item for item in update.summary.unresolved_questions)
    assert any("explain" in item.lower() for item in update.summary.commitments)

    emotional = roll_conversation_summary(
        update.summary,
        [
            {"role": "user", "content": "I feel worried about my girlfriend."},
            {"role": "assistant", "content": "I hear you. We can take this slowly."},
        ]
        * 4,
        "Okay",
        "I'm with you.",
        keep_recent_messages=4,
    )
    assert emotional.summary.emotional_context == ("anxious",)
    assert "girlfriend" in emotional.summary.active_entities


def test_summary_tracks_corrections_and_renders_continuity_as_untrusted() -> None:
    update = roll_conversation_summary(
        None,
        [
            {"role": "user", "content": "Correction: the model is Qwen, not Dolphin."},
            {"role": "assistant", "content": "Understood. I will use Qwen next."},
        ]
        * 4,
        "Continue",
        "Okay.",
        keep_recent_messages=4,
    )

    restored = ConversationSummary.from_value(update.summary.to_dict())
    rendered = render_conversation_summary(restored)

    assert restored.corrections == ("Correction: the model is Qwen, not Dolphin.",)
    assert "Unresolved user questions" in rendered
    assert "Nova commitments" in rendered
    assert "Corrections" in rendered
    assert "untrusted historical context" in rendered


def test_world_model_continuity_is_client_isolated_and_restart_safe(tmp_path: Path) -> None:
    checkpoint = tmp_path / "world.json"
    model = NovaWorldModel(
        persistence="checkpoint",
        checkpoint_path=checkpoint,
    )

    phone = model.record_continuity(
        "phone",
        "c1",
        {
            "active_topic": "relationship",
            "unresolved_count": 1,
            "commitment_count": 2,
            "correction_count": 0,
            "active_entities": ["girlfriend"],
            "emotional_context": ["anxious"],
            "prompt": "PRIVATE PHONE PROMPT",
        },
    )
    desktop = model.record_continuity(
        "desktop",
        "c1",
        {
            "active_topic": "coding",
            "unresolved_count": 0,
            "commitment_count": 1,
            "correction_count": 1,
            "active_entities": ["Nova"],
            "emotional_context": [],
            "response": "PRIVATE DESKTOP RESPONSE",
        },
    )

    assert phone["continuity"]["active_topic"] == "relationship"
    assert desktop["continuity"]["active_topic"] == "coding"
    assert (
        model.view("phone", "c1")["data"]["continuity"]["active_topic"]
        == "relationship"
    )
    assert (
        model.view("desktop", "c1")["data"]["continuity"]["active_topic"]
        == "coding"
    )

    raw = checkpoint.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert payload["schema_version"] == "1.2"
    assert "PRIVATE PHONE PROMPT" not in raw
    assert "PRIVATE DESKTOP RESPONSE" not in raw

    restored = NovaWorldModel(
        persistence="checkpoint",
        checkpoint_path=checkpoint,
    )
    assert (
        restored.view("phone", "c1")["data"]["continuity"]["active_topic"]
        == "relationship"
    )
    assert (
        restored.view("desktop", "c1")["data"]["continuity"]["active_topic"]
        == "coding"
    )


def test_world_model_continuity_rejects_free_form_text() -> None:
    model = NovaWorldModel()

    result = model.record_continuity(
        "phone",
        "c1",
        {
            "active_topic": "not-an-allowlisted-topic",
            "unresolved_count": 999,
            "commitment_count": -1,
            "active_entities": ["secret-person-name", "girlfriend"],
            "emotional_context": ["private diary text", "positive"],
        },
    )

    assert result["continuity"] == {
        "active_topic": "general_conversation",
        "unresolved_count": 8,
        "commitment_count": 0,
        "correction_count": 0,
        "active_entities": ["girlfriend"],
        "emotional_context": ["positive"],
    }


def test_gateway_records_provider_summary_continuity_after_completion(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "gateway-world.json"
    world_model = NovaWorldModel(
        persistence="checkpoint",
        checkpoint_path=checkpoint,
    )

    def runner(_text: str, _context: dict) -> tuple[str, dict]:
        return (
            "I will explain that next.",
            {
                "source": "cognitive_os",
                "conversation_summary": {
                    "schema_version": "1.0",
                    "revision": 3,
                    "topics": ["Why is the Earth round?"],
                    "unresolved_questions": ["Why is the Earth round?"],
                    "commitments": ["I will explain that next."],
                    "corrections": [],
                    "active_entities": ["earth"],
                    "emotional_context": [],
                },
            },
        )

    core = NovaGatewayCore(
        runner,
        config=GatewayConfig(),
        register_ollama=False,
        world_model=world_model,
    )
    request = NovaRequest(
        request_id="req-continuity",
        client_id="phone",
        conversation_id="thread-1",
        messages=[NovaMessage(role="user", content="Why?")],
        generation_options=NovaGenerationOptions(model="nova"),
    )

    response = core.generate(request)

    assert response.metadata["world_model"]["continuity"] == {
        "active_topic": "science",
        "unresolved_count": 1,
        "commitment_count": 1,
        "correction_count": 0,
        "active_entities": ["earth"],
        "emotional_context": [],
    }
