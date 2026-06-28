"""Data Gathering Agent - collects and structures data."""
from nova.agents.base_agent import BaseAgent


class DataGatheringAgent(BaseAgent):
    name = "data_gathering_agent"

    def execute(self, task: str, **kwargs) -> dict:
        return {
            "success": True,
            "message": "Data gathering agent (simulated). Configure real providers for live data.",
            "data": {"task": task, "collected": 0},
        }

    def is_available(self) -> bool:
        return True
