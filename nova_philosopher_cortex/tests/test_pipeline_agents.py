"""Tests proving pipeline invokes agents and results reach the final answer."""
from unittest.mock import patch, MagicMock
from nova.pipeline import NovaPipeline
from nova.config import NovaConfig, set_config
from nova.schema import EvidenceClass


class TestPipelineAgentIntegration:
    def setup_method(self):
        self.cfg = NovaConfig.default()
        self.cfg.web["enabled"] = True
        set_config(self.cfg)

    @patch("urllib.request.urlopen")
    def test_pipeline_invokes_research_agent(self, mock_urlopen):
        """Pipeline must invoke research agents when research is needed."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"AbstractText": "Test research evidence.", "Heading": "Test", "AbstractURL": "https://test.example.com", "AbstractSource": "Wiki", "RelatedTopics": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        pipeline = NovaPipeline(offline=False)
        response = pipeline.run("Look up the latest evidence about artificial intelligence.")

        # Pipeline must have called the research agent
        assert "research_agent" in response.module_chain, \
            "Pipeline did NOT call research_agent"

    @patch("urllib.request.urlopen")
    def test_agent_results_reach_specialists(self, mock_urlopen):
        """Research evidence must be attached to the packet for specialists to use."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"AbstractText": "Paris is the capital of France.", "Heading": "Paris", "AbstractURL": "https://en.wikipedia.org/wiki/Paris", "AbstractSource": "Wikipedia", "RelatedTopics": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        pipeline = NovaPipeline(offline=False)
        response = pipeline.run("Look up the capital of France.")

        # Evidence from web search should be attached
        assert len(response.meaning.evidence_items) > 0, \
            "No evidence items attached after research"

        # At least one piece of evidence should be from a web source
        web_sources = [
            e for e in response.meaning.evidence_items
            if e.evidence_class in (EvidenceClass.VERIFIED_SOURCE, EvidenceClass.DIRECT_OBSERVATION)
        ]
        assert len(web_sources) > 0, \
            "No web-sourced evidence items found — agent results not reaching packet"

    @patch("urllib.request.urlopen")
    def test_research_not_called_when_not_needed(self, mock_urlopen):
        """Pipeline must NOT call research agent when research is not needed."""
        mock_resp = MagicMock()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        pipeline = NovaPipeline(offline=False)
        response = pipeline.run("What is 2+2?")

        # Should NOT have research_agent in chain for non-research queries
        assert "research_agent" not in response.module_chain, \
            "Research agent was called for a non-research query"

    def test_offline_research_does_not_call_http(self):
        """When offline, pipeline must NOT attempt web research."""
        cfg = NovaConfig.default()
        cfg.web["enabled"] = False
        set_config(cfg)

        pipeline = NovaPipeline(offline=True)
        response = pipeline.run("Look up the latest evidence about AI.")

        assert "research_agent" in response.module_chain, \
            "Pipeline should note research was requested"
        # No evidence items from web should exist
        web_evidence = [
            e for e in response.meaning.evidence_items
            if e.evidence_class in (EvidenceClass.VERIFIED_SOURCE, EvidenceClass.DIRECT_OBSERVATION)
        ]
        assert len(web_evidence) == 0, \
            "Offline pipeline should not have web evidence"
