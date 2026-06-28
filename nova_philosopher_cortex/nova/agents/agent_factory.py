"""Agent Factory - creates and manages agents."""
from typing import Optional
from nova.agents.base_agent import BaseAgent
from nova.agents.research_agent import ResearchAgent
from nova.agents.web_search_agent import WebSearchAgent
from nova.agents.web_fetch_agent import WebFetchAgent
from nova.agents.data_gathering_agent import DataGatheringAgent
from nova.agents.citation_agent import CitationAgent
from nova.agents.source_quality_agent import SourceQualityAgent


class AgentFactory:
    """Creates agents by name."""

    _registry = {
        "research": ResearchAgent,
        "web_search": WebSearchAgent,
        "web_fetch": WebFetchAgent,
        "data_gathering": DataGatheringAgent,
        "citation": CitationAgent,
        "source_quality": SourceQualityAgent,
    }

    @classmethod
    def create(cls, agent_type: str, **kwargs) -> Optional[BaseAgent]:
        agent_class = cls._registry.get(agent_type)
        if agent_class:
            return agent_class(**kwargs)
        return None

    @classmethod
    def list_available(cls) -> list[str]:
        return list(cls._registry.keys())
