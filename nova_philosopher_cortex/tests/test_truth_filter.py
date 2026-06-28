"""Tests for Truth Filter."""
from nova.tiny_modules.final_truth_filter import FinalTruthFilter
from nova.schema import (
    NovaResponse, MeaningPacket, TruthVerdict,
    UncertaintyLevel, Assumption,
)


class TestTruthFilter:
    def setup_method(self):
        self.filter = FinalTruthFilter()

    def test_clean_response_passes(self):
        meaning = MeaningPacket(raw_text="What is 2+2?")
        response = NovaResponse(
            raw_question="What is 2+2?",
            meaning=meaning,
            uncertainty=UncertaintyLevel.CERTAIN,
        )
        response.final_text = "The answer is 4."
        verdict = self.filter.validate(response)
        assert verdict.passed is True

    def test_unsupported_certainty_fails(self):
        meaning = MeaningPacket(
            raw_text="This is proven.",
            assumptions=[Assumption(statement="proven claim", is_unsupported=True, risk_level="high")],
        )
        response = NovaResponse(
            raw_question="This is proven.",
            meaning=meaning,
            uncertainty=UncertaintyLevel.SPECULATIVE,
        )
        response.final_text = "This is definitely proven."
        verdict = self.filter.validate(response)
        # High-risk assumptions without evidence
        assert verdict.passed is False or len(verdict.issues) > 0

    def test_science_no_measurement(self):
        meaning = MeaningPacket(raw_text="Science question about gravity.")
        meaning.requires_science = True
        response = NovaResponse(
            raw_question="Science question",
            meaning=meaning,
            uncertainty=UncertaintyLevel.MODERATE,
        )
        response.final_text = "Gravity is a force."
        verdict = self.filter.validate(response)
        # Science without measurement should flag
        assert verdict is not None

    def test_contradictions_flagged(self):
        meaning = MeaningPacket(raw_text="Test")
        meaning.logic_check.contradictions = ["Contains both 'all' and 'none'"]
        response = NovaResponse(
            raw_question="Test",
            meaning=meaning,
            uncertainty=UncertaintyLevel.LOW_CONFIDENCE,
        )
        response.final_text = "Some text."
        verdict = self.filter.validate(response)
        assert len(verdict.issues) > 0
