"""Tests for the full pipeline."""
from nova.pipeline import NovaPipeline
from nova.schema import IntentType


class TestPipeline:
    def setup_method(self):
        self.pipeline = NovaPipeline(offline=True)

    def test_pipeline_runs(self):
        response = self.pipeline.run("What is truth?")
        assert response.final_text is not None
        assert len(response.final_text) > 0
        assert response.meaning is not None

    def test_pipeline_math(self):
        response = self.pipeline.run("If a car travels 150 miles in 3 hours, what is the speed?")
        assert response.meaning.requires_math is True
        assert response.final_text is not None
        # Math cortex should have been triggered
        assert any("math" in r.module_name for r in response.specialist_results)

    def test_pipeline_assumptions(self):
        response = self.pipeline.run("Obviously all institutions lie all the time.")
        assert len(response.meaning.assumptions) > 0
        assert len(response.meaning.bias_flags) > 0

    def test_pipeline_philosophy(self):
        response = self.pipeline.run("What is justice?")
        # "What is justice?" should be detected as philosophy-related
        assert response.meaning.requires_philosophy is True or \
               IntentType.PHILOSOPHY in response.meaning.secondary_intents or \
               any("philosopher" in m for m in response.module_chain)

    def test_module_chain(self):
        response = self.pipeline.run("Hello")
        assert len(response.module_chain) > 0
        assert "language_cortex" in response.module_chain

    def test_offline_research(self):
        response = self.pipeline.run("Look up the latest evidence about AI.")
        assert response.meaning.requires_research is True
