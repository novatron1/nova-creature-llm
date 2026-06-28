"""Source Quality Agent - evaluates source reliability."""
from nova.agents.base_agent import BaseAgent


class SourceQualityAgent(BaseAgent):
    name = "source_quality_agent"

    def execute(self, task: str, **kwargs) -> dict:
        return {
            "success": True,
            "message": "Source quality agent (simulated). No sources to evaluate in offline mode.",
            "data": {"task": task, "quality_score": 0.0},
        }

    def is_available(self) -> bool:
        return True
