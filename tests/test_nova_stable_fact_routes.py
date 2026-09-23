from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nova_intent_planner import _direct_answer_fast_plan


def test_capital_of_japan_uses_deterministic_route():
    plan = _direct_answer_fast_plan("What is the capital of Japan?", datetime.now(timezone.utc))

    assert plan is not None
    assert plan["needs_llm_synthesis"] is False
    assert plan["_direct_answer"] == "The capital of Japan is Tokyo."
