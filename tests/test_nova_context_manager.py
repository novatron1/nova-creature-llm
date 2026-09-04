from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_context_manager import manage_context


def test_context_manager_compacts_old_turns_and_preserves_current_request():
    request = "CURRENT REQUEST MUST REMAIN COMPLETE: compare the two architectures."
    conversation = [
        {"role": "user", "content": f"Old user turn {index}: " + "detail " * 120}
        if index % 2 == 0
        else {"role": "assistant", "content": f"Old Nova turn {index}: " + "answer " * 120}
        for index in range(20)
    ]
    managed = manage_context(
        system="Nova identity.\nNova identity.\nKeep facts accurate.",
        current_request=request,
        conversation=conversation,
        memory="The user explicitly prefers local-first software.",
        rag_evidence="Source [1] says the interface is provider-independent. " * 100,
        tools_observations="obsolete output\n" * 30,
        context_window=2048,
    )

    assert managed.current_request == request
    assert managed.diagnostics.compacted is True
    assert managed.diagnostics.removed_duplicate_system_lines == 1
    assert managed.diagnostics.summarized_conversation_turns > 0
    assert managed.diagnostics.removed_tool_outputs > 0
    assert "local-first" in managed.memory


def test_context_manager_records_unavoidable_request_truncation():
    managed = manage_context(
        system="Nova",
        current_request="word " * 10000,
        context_window=1024,
    )
    assert managed.diagnostics.current_request_truncated is True
    assert managed.diagnostics.notes
    assert "Context compacted" in managed.current_request


def test_context_diagnostics_are_content_free():
    managed = manage_context(
        system="secret system content",
        current_request="private request",
        context_window=2048,
    )
    trace = managed.diagnostics.safe_trace()
    serialized = str(trace)
    assert "secret system content" not in serialized
    assert "private request" not in serialized

