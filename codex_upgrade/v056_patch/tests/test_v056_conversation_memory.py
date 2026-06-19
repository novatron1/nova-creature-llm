from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conversation_memory import ConversationMemory

def test_memory_state_roundtrip(tmp_path):
    m = ConversationMemory(tmp_path, thread_id="test")
    ctx = m.build_context("We need conversation memory.")
    assert ctx["active_goal"]
    state = m.update_after_turn("We need conversation memory.", "Planner: do it.", "planner_transformer")
    assert state["turn_count"] == 1
    ctx2 = m.build_context("Do that.")
    assert ctx2["is_followup"] is True
    assert "conversation memory" in ctx2["active_goal"]
