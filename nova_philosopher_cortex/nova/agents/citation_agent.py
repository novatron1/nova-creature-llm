"""Citation Agent - manages source citations."""
from nova.agents.base_agent import BaseAgent


class CitationAgent(BaseAgent):
    name = "citation_agent"

    def execute(self, task: str, **kwargs) -> dict:
        return {
            "success": True,
            "message": "Citation agent (simulated). No real sources available in this configuration.",
            "data": {"task": task, "citations": []},
        }

    def is_available(self) -> bool:
        return True
