"""Tests for Research Agents."""
from nova.agents.agent_factory import AgentFactory
from nova.agents.research_agent import ResearchAgent


class TestResearchAgents:
    def test_factory_creates_research(self):
        agent = AgentFactory.create("research")
        assert agent is not None
        assert agent.name == "research_agent"

    def test_offline_research(self):
        agent = ResearchAgent()
        result = agent.execute("test task")
        assert result["success"] is False or result["error"] == "offline_mode"

    def test_factory_list(self):
        agents = AgentFactory.list_available()
        assert "research" in agents
        assert "web_search" in agents

    def test_factory_invalid(self):
        agent = AgentFactory.create("nonexistent")
        assert agent is None
