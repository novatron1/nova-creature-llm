from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_companion_state_defaults_are_bounded_and_stable():
    from nova_companion.models import CompanionState

    state = CompanionState.new("user-a", now="2026-08-18T00:00:00+00:00")

    assert state.user_id == "user-a"
    assert state.relationship_stage == "new"
    assert state.familiarity_score == 0.0
    assert state.trust_score == 0.0
    assert state.nova_current_mood.energy == 0.5
    assert state.personality_version


def test_companion_state_from_row_clamps_untrusted_values():
    from nova_companion.models import CompanionState

    state = CompanionState.from_row(
        {
            "user_id": "user-a",
            "familiarity_score": 9,
            "trust_score": -4,
            "relationship_stage": "invalid",
            "interaction_count": "not-a-number",
            "known_user_preferences_json": "{}",
        }
    )

    assert state.relationship_stage == "new"
    assert state.familiarity_score == 1.0
    assert state.trust_score == 0.0
    assert state.interaction_count == 0
