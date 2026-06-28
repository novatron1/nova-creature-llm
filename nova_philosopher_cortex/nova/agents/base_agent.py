"""Base agent class."""
from abc import ABC, abstractmethod
from typing import Optional


class BaseAgent(ABC):
    """Base class for all research/data agents."""

    name: str = "base_agent"

    @abstractmethod
    def execute(self, task: str, **kwargs) -> dict:
        """Execute a task and return results."""
        pass

    def is_available(self) -> bool:
        """Check if this agent can run."""
        return False
