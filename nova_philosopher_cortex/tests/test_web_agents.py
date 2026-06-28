"""Tests for WebSearchAgent and WebFetchAgent with mocked HTTP."""
from unittest.mock import patch, MagicMock
from nova.agents.web_search_agent import WebSearchAgent
from nova.agents.web_fetch_agent import WebFetchAgent
from nova.agents.research_agent import ResearchAgent
from nova.config import NovaConfig, set_config


class TestWebSearchAgent:
    def setup_method(self):
        cfg = NovaConfig.default()
        cfg.web["enabled"] = True
        set_config(cfg)

    def test_offline_returns_no_fake_data(self):
        """When offline, agent must NOT return fake results."""
        cfg = NovaConfig.default()
        cfg.web["enabled"] = False
        set_config(cfg)

        agent = WebSearchAgent()
        result = agent.execute("test query")
        assert result["success"] is False
        assert result["error"] == "offline_mode"
        assert result["data"] is None

    @patch("urllib.request.urlopen")
    def test_real_http_call_is_made(self, mock_urlopen):
        """WebSearchAgent must make an HTTP request via urllib."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"AbstractText": "Paris is the capital of France.", "Heading": "Paris", "AbstractURL": "https://en.wikipedia.org/wiki/Paris", "AbstractSource": "Wikipedia", "RelatedTopics": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        agent = WebSearchAgent()
        result = agent.execute("capital of France")

        # Verify urllib was actually called
        assert mock_urlopen.called, "HTTP call was NOT made — agent skipped real fetch"
        called_url = mock_urlopen.call_args[0][0].full_url
        assert "duckduckgo.com" in called_url or "api.duckduckgo.com" in called_url or "duckduckgo" in called_url

        # Verify results are from the HTTP response, not hardcoded
        assert result["success"] is True
        results = result["data"]["results"]
        assert len(results) > 0
        # The snippet came from the mocked response, not hardcoded
        assert "Paris" in results[0]["snippet"]
        assert "France" in results[0]["snippet"]

    @patch("urllib.request.urlopen")
    def test_search_results_are_not_hardcoded(self, mock_urlopen):
        """Search results must come from the HTTP response, not a hardcoded fallback."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"AbstractText": "Unique test result 42.", "Heading": "Test", "AbstractURL": "https://test.example.com", "AbstractSource": "TestSource", "RelatedTopics": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        agent = WebSearchAgent()
        result = agent.execute("something unique 42")

        results = result["data"]["results"]
        # The result contains data from the mock response, not a hardcoded message
        assert any("Unique test result 42" in r["snippet"] for r in results)
        assert not any("would run here" in r.get("snippet", "") for r in results)


class TestWebFetchAgent:
    def setup_method(self):
        cfg = NovaConfig.default()
        cfg.web["enabled"] = True
        set_config(cfg)

    def test_offline_returns_no_data(self):
        cfg = NovaConfig.default()
        cfg.web["enabled"] = False
        set_config(cfg)

        agent = WebFetchAgent()
        result = agent.execute("https://example.com")
        assert result["success"] is False
        assert result["error"] == "offline_mode"

    @patch("urllib.request.urlopen")
    def test_fetch_makes_http_call(self, mock_urlopen):
        """WebFetchAgent must make a real HTTP request."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><body>Real fetched content</body></html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        agent = WebFetchAgent()
        result = agent.execute("https://example.com/test")

        assert mock_urlopen.called, "HTTP call was NOT made"
        assert result["success"] is True
        assert "Real fetched content" in result["data"]["content"]


class TestResearchAgent:
    def setup_method(self):
        cfg = NovaConfig.default()
        cfg.web["enabled"] = True
        set_config(cfg)

    def test_offline_no_fake_results(self):
        cfg = NovaConfig.default()
        cfg.web["enabled"] = False
        set_config(cfg)

        agent = ResearchAgent()
        result = agent.execute("test")
        assert result["success"] is False
        assert result["error"] == "offline_mode"
        assert result["data"] is None

    @patch("urllib.request.urlopen")
    def test_research_coordinates_search_and_fetch(self, mock_urlopen):
        """ResearchAgent must call search and return real results."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"AbstractText": "Research result.", "Heading": "Result", "AbstractURL": "https://example.com", "AbstractSource": "Web", "RelatedTopics": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        agent = ResearchAgent()
        result = agent.execute("test research query")

        assert result["success"] is True
        results = result["data"]["results"]
        assert len(results) == 1
        assert results[0]["source"] == "duckduckgo_instant"
        assert results[0]["snippet"] == "Research result."
