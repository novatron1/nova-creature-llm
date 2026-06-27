from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_local_llm_connector
import nova_llm_synthesizer as synthesizer


def test_synthesizer_uses_raw_output_from_local_llm_response(monkeypatch):
    class FakeConnector:
        def generate(self, context_packet):
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Final answer from DeepSeek.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "You are Nova.",
            "user_question": "Explain loops.",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "Final answer from DeepSeek."


def test_synthesizer_sends_built_prompt_to_local_llm(monkeypatch):
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Robots should test code before users see it.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    synthesizer.generate(
        {
            "system_prompt": "System rules here.",
            "user_question": "Why test robot code?",
        }
    )

    assert "raw_prompt" in captured
    assert "System rules here." in captured["raw_prompt"]
    assert "Why test robot code?" in captured["raw_prompt"]
    assert captured["local_llm_model"] == "qwen2.5:1.5b"
    assert captured["local_llm_timeout"] <= 45


def test_synthesizer_removes_internal_nova_speaker_label(monkeypatch):
    class FakeConnector:
        def generate(self, context_packet):
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="Extra draft text.\n\nNova: Final clean answer.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "System rules here.",
            "user_question": "Why test robot code?",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "Final clean answer."


def test_synthesizer_uses_compact_prompt_for_college_question(monkeypatch):
    captured = {}

    class FakeConnector:
        def generate(self, context_packet):
            captured.update(context_packet)
            return SimpleNamespace(
                local_llm_used=True,
                raw_output="x = 4.",
                fallback_reason=None,
            )

    monkeypatch.setattr(nova_local_llm_connector, "LocalLLMConnector", FakeConnector)

    answer, ok, error = synthesizer.generate(
        {
            "system_prompt": "Very long system prompt " * 50,
            "user_question": "College algebra: solve 2x + 3 = 11.",
            "route": "general_conversation",
        }
    )

    assert ok is True
    assert error is None
    assert answer == "x = 4."
    assert captured["raw_prompt"].startswith("Answer the academic question directly.")
    assert "Very long system prompt" not in captured["raw_prompt"]
    assert captured["local_llm_model"] == "deepseek-r1:7b"
    assert captured["local_llm_timeout"] >= 120


def test_synthesizer_prefers_clean_answer_label_when_complete():
    cleaned = synthesizer._clean_synthesized_answer(
        "Draft line that repeats itself.\n\nAnswer:\nThe correct line is `print('hello')` because the original missed a closing parenthesis."
    )

    assert cleaned == "The correct line is `print('hello')` because the original missed a closing parenthesis."


def test_synthesizer_keeps_first_complete_answer_when_final_label_is_truncated():
    cleaned = synthesizer._clean_synthesized_answer(
        "Newton's second law says force equals mass times acceleration. A heavier object needs more force for the same acceleration.\n\nFinal answer: Newton's second law says force equals mass"
    )

    assert cleaned == (
        "Newton's second law says force equals mass times acceleration. "
        "A heavier object needs more force for the same acceleration."
    )
