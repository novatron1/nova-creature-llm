"""Research Agent - coordinates real research via web search + fetch.

Uses WebSearchAgent and WebFetchAgent behind the scenes.
"""
from typing import Optional
from nova.agents.base_agent import BaseAgent
from nova.agents.web_search_agent import WebSearchAgent
from nova.agents.web_fetch_agent import WebFetchAgent
from nova.config import get_config


class ResearchAgent(BaseAgent):
    """Coordinates multi-step research: search, fetch top results, return evidence."""

    name = "research_agent"

    def __init__(self):
        self.search_agent = WebSearchAgent()
        self.fetch_agent = WebFetchAgent()

    def execute(self, task: str, **kwargs) -> dict:
        cfg = get_config()
        if not cfg.web.get("enabled", False):
            return {
                "success": False,
                "error": "offline_mode",
                "message": "Web research is not configured. Enable it in config or run without --offline.",
                "data": None,
            }

        # Step 1: Search
        search_result = self.search_agent.execute(task)
        if not search_result["success"]:
            return search_result

        results = search_result["data"].get("results", [])

        # Step 2: Try to fetch the first result's URL for more detail
        fetched_content = None
        for r in results[:1]:
            url = r.get("url", "")
            if url:
                fetch_result = self.fetch_agent.execute(url)
                if fetch_result["success"] and fetch_result["data"].get("content"):
                    fetched_content = fetch_result["data"]["content"][:5000]
                    r["fetched"] = True
                    break

        return {
            "success": True,
            "message": "Research completed with %d result(s)." % len(results),
            "data": {
                "task": task,
                "results": results,
                "fetched_content": fetched_content,
            },
        }

    def is_available(self) -> bool:
        cfg = get_config()
        return cfg.web.get("enabled", False)
