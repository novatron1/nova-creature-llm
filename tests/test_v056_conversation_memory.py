from pathlib import Path
import sys
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conversation_memory import ConversationMemory

def load_packaged_conversation_memory():
    packaged_path = ROOT / "codex_upgrade" / "v056_patch" / "src" / "conversation_memory.py"
    spec = importlib.util.spec_from_file_location("packaged_conversation_memory", packaged_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.ConversationMemory


def test_memory_state_roundtrip(tmp_path):
    for memory_cls, suffix in (
        (ConversationMemory, "runtime"),
        (load_packaged_conversation_memory(), "packaged"),
    ):
        m = memory_cls(tmp_path / suffix, thread_id="test")
        ctx = m.build_context("We need conversation memory.")
        assert ctx["active_goal"]
        state = m.update_after_turn("We need conversation memory.", "Planner: do it.", "planner_transformer")
        assert state["turn_count"] == 1
        ctx2 = m.build_context("Do that.")
        assert ctx2["is_followup"] is True
        assert "conversation memory" in ctx2["active_goal"]
