from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_app_navigation import (
    AppNavigationContext,
    SafetyLevel,
    plan_app_navigation,
)


def test_surface_navigation_commands_resolve_canonical_pages():
    context = AppNavigationContext()

    agent = plan_app_navigation("go to Agent Library", context)
    builder = plan_app_navigation("open the builder", context)
    logs = plan_app_navigation("look at the logs", context)

    assert agent.recognized is True
    assert agent.intent.target_surface == "agent_library"
    assert agent.intent.action == "navigate"
    assert agent.intent.safety_level == SafetyLevel.READ_ONLY
    assert agent.steps[0].kind == "understand"
    assert any(step.kind == "navigate" and step.target == "agent_library" for step in agent.steps)

    assert builder.recognized is True
    assert builder.intent.target_surface == "app_builder"
    assert logs.recognized is True
    assert logs.intent.target_surface == "debug_logs"


def test_unknown_chat_is_not_claimed_by_navigation_router():
    context = AppNavigationContext()

    result = plan_app_navigation("what is the quadratic formula?", context)

    assert result.recognized is False
    assert result.intent is None
    assert result.trace()["source"] == "app_navigation_miss"
