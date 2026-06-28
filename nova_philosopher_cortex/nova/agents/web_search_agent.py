"""Web Search Agent - performs real web searches via DuckDuckGo Instant Answer API.

Uses urllib from stdlib — no extra packages needed.
When offline mode is active, returns a clear offline message.
"""
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional
from nova.agents.base_agent import BaseAgent
from nova.config import get_config


DUCKDUCKGO_API = "https://api.duckduckgo.com/"
REQUEST_TIMEOUT = 10


class WebSearchAgent(BaseAgent):
    name = "web_search_agent"

    def execute(self, task: str, **kwargs) -> dict:
        cfg = get_config()
        if not cfg.web.get("enabled", False):
            return {
                "success": False,
                "error": "offline_mode",
                "message": "Web search is not available in offline mode.",
                "data": None,
            }

        try:
            results = self._search_duckduckgo(task, cfg)
            return {
                "success": True,
                "message": "Search completed.",
                "data": {"task": task, "results": results},
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Web search failed: %s" % str(e),
                "data": {"task": task, "results": []},
            }

    def _search_duckduckgo(self, query: str, cfg) -> list[dict]:
        """Real HTTP search via DuckDuckGo Instant Answer API.

        Returns a list of result dicts with 'title', 'url', 'snippet' keys.
        """
        params = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
            "t": "nova_philosopher_cortex",
        })
        url = DUCKDUCKGO_API + "?" + params

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": cfg.web.get("user_agent", "NovaPhilosopherCortex/0.1"),
            },
        )

        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())

        results = []

        # Instant Answer (abstract)
        if data.get("AbstractText"):
            results.append({
                "source": "duckduckgo_instant",
                "title": data.get("Heading", ""),
                "url": data.get("AbstractURL", ""),
                "snippet": data.get("AbstractText", ""),
                "source_name": data.get("AbstractSource", ""),
            })

        # Definition
        if data.get("Definition"):
            results.append({
                "source": "duckduckgo_definition",
                "title": data.get("Heading", ""),
                "snippet": data.get("Definition", ""),
                "url": data.get("DefinitionURL", ""),
            })

        # Related topics
        for topic in data.get("RelatedTopics", []):
            if "Text" in topic:
                results.append({
                    "source": "duckduckgo_related",
                    "title": topic.get("Text", "")[:80],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                })
            elif "Topics" in topic:
                for sub in topic["Topics"]:
                    if "Text" in sub:
                        results.append({
                            "source": "duckduckgo_related",
                            "title": sub.get("Text", "")[:80],
                            "snippet": sub.get("Text", ""),
                            "url": sub.get("FirstURL", ""),
                        })

        return results

    def is_available(self) -> bool:
        cfg = get_config()
        return cfg.web.get("enabled", False)
