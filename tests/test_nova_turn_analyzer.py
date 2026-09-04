from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_turn_analyzer import analyze_turn
from nova_conversation_intelligence import understand_conversation_turn


def test_greeting_stays_fast_without_agent_steps():
    state = analyze_turn("hi")
    assert state.reasoning_mode == "fast"
    assert state.tools_required is False
    assert state.max_tool_steps == 0


def test_architecture_request_selects_deep_reasoning():
    state = analyze_turn("Analyze this architecture and compare the design tradeoffs.")
    assert state.reasoning_mode == "deep"
    assert state.complexity in {"medium", "high"}
    assert state.tools_required is False


def test_calculus_request_selects_deep_reasoning_without_tools():
    state = analyze_turn(
        "Differentiate f(x) = x^3 - 4x + 7 and give one short justification."
    )
    assert state.reasoning_mode == "deep"
    assert state.tools_required is False
    assert state.complexity in {"medium", "high"}


def test_explicit_deep_origin_of_life_question_stays_deep_with_shared_decision():
    prompt = (
        "Now I want you to think deep about how a human could even come to be "
        "on a cooling planet, how different species and DNA could develop from "
        "earlier chemistry, and why we cannot demonstrate the whole process in a laboratory."
    )
    decision = understand_conversation_turn(prompt)

    state = analyze_turn(prompt, conversation_decision=decision)

    assert state.reasoning_mode == "deep"
    assert state.requested_depth == "thorough"
    assert state.tools_required is False


def test_hypothetical_deployment_debug_plan_is_not_an_authorized_action():
    state = analyze_turn(
        "API latency tripled immediately after a deployment. Give the first "
        "three evidence-based actions you would take."
    )
    assert state.reasoning_mode == "verify"
    assert state.tools_required is False
    assert state.risk_level == "medium"


def test_file_action_selects_bounded_agent_mode():
    state = analyze_turn("Read the project file and run the test suite.", max_tool_steps=4)
    assert state.reasoning_mode == "agent"
    assert state.tools_required is True
    assert state.project_context_required is True
    assert state.max_tool_steps == 4


def test_high_stakes_current_request_selects_verify():
    state = analyze_turn("Verify the latest legal rule and cite the current source.")
    assert state.reasoning_mode == "verify"
    assert state.certainty_required is True
    assert state.current_information_required is True
    assert state.risk_level == "high"


def test_mixed_financial_stress_and_investment_guidance_stays_verified():
    prompt = "I need money; what financial investment should I make?"
    decision = understand_conversation_turn(prompt)

    state = analyze_turn(prompt, conversation_decision=decision)

    assert state.topic == "high_stakes_finance"
    assert state.reasoning_mode == "verify"
    assert state.certainty_required is True
    assert state.risk_level == "high"


def test_safe_trace_never_contains_prompt_text():
    state = analyze_turn("Remember that my private nickname is Star.")
    trace = state.safe_trace()
    assert "user_text" not in trace
    assert trace["user_text_length"] > 0
