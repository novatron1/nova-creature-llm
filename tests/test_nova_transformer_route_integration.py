from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_hybrid_router import route_and_respond


def test_transformer_only_prompts_produce_checkpoint_evidence():
    prompts = [
        "Debug this Python loop.",
        "Make an ordered release plan.",
        "Verify this claim using evidence.",
        "Design a calm blue pattern.",
        "Recall Nova's creator.",
        "Simulate a failed deployment.",
        "Explain routing clearly.",
    ]
    for prompt in prompts:
        response, trace = route_and_respond(prompt, transformer_only=True)
        assert response.strip()
        assert trace["source"] == "transformer"
        assert trace["route_model_hash"]
        assert trace["checkpoint_hash"]
        assert trace["generation"]["ok"] is True
        assert "fallback" not in trace.get("skills", [])
