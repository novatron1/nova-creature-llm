"""Web Fetch Agent - fetches and processes web content using real HTTP.

Uses urllib from stdlib — no extra packages needed.
"""
import urllib.request
import urllib.error
from typing import Optional
from nova.agents.base_agent import BaseAgent
from nova.config import get_config


REQUEST_TIMEOUT = 15
MAX_CONTENT_BYTES = 256 * 1024  # 256KB


class WebFetchAgent(BaseAgent):
    name = "web_fetch_agent"

    def execute(self, task: str, **kwargs) -> dict:
        cfg = get_config()
        if not cfg.web.get("enabled", False):
            return {
                "success": False,
                "error": "offline_mode",
                "message": "Web fetch is not available in offline mode.",
                "data": None,
            }

        url = task.strip()
        if not url.startswith(("http://", "https://")):
            return {
                "success": False,
                "error": "invalid_url",
                "message": "URL must start with http:// or https://",
                "data": None,
            }

        try:
            content = self._fetch_url(url)
            return {
                "success": True,
                "message": "Page fetched successfully.",
                "data": {"url": url, "content": content},
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Web fetch failed: %s" % str(e),
                "data": {"url": url, "content": None},
            }

    def _fetch_url(self, url: str) -> str:
        """Fetch a URL and return its text content."""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": get_config().web.get("user_agent", "NovaPhilosopherCortex/0.1"),
            },
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read(MAX_CONTENT_BYTES)

        # Try to decode as UTF-8, fall back to latin-1
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")

        # Basic HTML tag stripping for readability
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", "\"").replace("&#39;", "'")
        return text

    def is_available(self) -> bool:
        cfg = get_config()
        return cfg.web.get("enabled", False)
