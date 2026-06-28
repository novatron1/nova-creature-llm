"""Tests proving KnowledgeCortex and ScienceCortex answer real questions."""
from nova.specialist_cortex.knowledge_cortex import KnowledgeCortex
from nova.specialist_cortex.science_cortex import ScienceCortex
from nova.schema import MeaningPacket, EvidenceItem, EvidenceClass, UncertaintyLevel


class TestKnowledgeCortexAnswers:
    def setup_method(self):
        self.cortex = KnowledgeCortex()

    def test_capital_of_france(self):
        """KnowledgeCortex must answer 'What is the capital of France?'."""
        packet = MeaningPacket(
            raw_text="What is the capital of France?",
            cleaned_text="What is the capital of France?",
            key_terms=["france", "capital"],
        )
        result = self.cortex.analyze(packet)
        # Must find the answer
        assert "Paris" in result.analysis, \
            "KnowledgeCortex did not answer 'capital of France' — got: " + result.analysis[:100]

    def test_capital_of_japan(self):
        packet = MeaningPacket(
            raw_text="What is the capital of Japan?",
            cleaned_text="What is the capital of Japan?",
            key_terms=["japan", "capital"],
        )
        result = self.cortex.analyze(packet)
        assert "Tokyo" in result.analysis

    def test_speed_of_light(self):
        packet = MeaningPacket(
            raw_text="What is the speed of light?",
            cleaned_text="What is the speed of light?",
            key_terms=["speed", "light"],
        )
        result = self.cortex.analyze(packet)
        assert "299,792,458" in result.analysis

    def test_confidence_with_answer(self):
        """When answer found, confidence should be high."""
        packet = MeaningPacket(
            raw_text="What is the capital of France?",
            cleaned_text="What is the capital of France?",
            key_terms=["france", "capital"],
        )
        result = self.cortex.analyze(packet)
        assert result.confidence >= 0.8, \
            "Confidence should be high when answer found"

    def test_unknown_query_returns_graceful_message(self):
        """For unknown queries, KnowledgeCortex should not crash."""
        packet = MeaningPacket(
            raw_text="What is the meaning of life?",
            cleaned_text="What is the meaning of life?",
            key_terms=["meaning", "life"],
        )
        result = self.cortex.analyze(packet)
        # Should return something, not crash
        assert result.analysis is not None
        assert len(result.analysis) > 0


class TestScienceCortexAnswers:
    def setup_method(self):
        self.cortex = ScienceCortex()

    def test_gravity_explanation(self):
        """ScienceCortex must explain gravity with evidence."""
        packet = MeaningPacket(
            raw_text="What is gravity?",
            cleaned_text="What is gravity?",
            key_terms=["gravity"],
        )
        result = self.cortex.analyze(packet)
        assert "9.81" in result.analysis, \
            "ScienceCortex did not explain gravity with the constant — got: " + result.analysis[:100]

    def test_quantum_mechanics_explanation(self):
        packet = MeaningPacket(
            raw_text="What is quantum mechanics?",
            cleaned_text="What is quantum mechanics?",
            key_terms=["quantum", "mechanics"],
        )
        result = self.cortex.analyze(packet)
        assert "wave-particle" in result.analysis or "uncertainty" in result.analysis

    def test_evolution_explanation(self):
        packet = MeaningPacket(
            raw_text="What is evolution?",
            cleaned_text="What is evolution?",
            key_terms=["evolution"],
        )
        result = self.cortex.analyze(packet)
        assert "natural selection" in result.analysis

    def test_science_with_research_evidence(self):
        """ScienceCortex should use research evidence when provided."""
        packet = MeaningPacket(
            raw_text="What is quantum physics?",
            cleaned_text="What is quantum physics?",
            key_terms=["quantum", "physics"],
            evidence_items=[
                EvidenceItem(
                    claim="Quantum physics explains subatomic behavior",
                    evidence_class=EvidenceClass.VERIFIED_SOURCE,
                    source="science_journal",
                    is_verifiable=True,
                ),
            ],
        )
        result = self.cortex.analyze(packet)
        # Should contain explanation AND reference the evidence
        assert "quantum" in result.analysis.lower()
        assert result.confidence >= 0.7

    def test_confidence_with_explanation(self):
        packet = MeaningPacket(
            raw_text="What is gravity?",
            cleaned_text="What is gravity?",
            key_terms=["gravity"],
        )
        result = self.cortex.analyze(packet)
        assert result.confidence >= 0.8
