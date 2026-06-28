"""Tests for Evidence Classifier."""
from nova.tiny_modules.evidence_classifier import EvidenceClassifier
from nova.schema import MeaningPacket


class TestEvidenceClassifier:
    def setup_method(self):
        self.classifier = EvidenceClassifier()

    def test_measurement_detected(self):
        packet = MeaningPacket(raw_text="It travelled 100 miles in 2 hours.")
        packet.cleaned_text = "It travelled 100 miles in 2 hours."
        packet = self.classifier.process(packet)
        # Should have evidence if measurement found
        assert len(packet.evidence_items) >= 1

    def test_no_evidence(self):
        packet = MeaningPacket(raw_text="I think philosophy is interesting.")
        packet.cleaned_text = "I think philosophy is interesting."
        packet = self.classifier.process(packet)
        assert len(packet.evidence_items) == 0

    def test_source_reference(self):
        packet = MeaningPacket(raw_text="According to a study, this is true.")
        packet.cleaned_text = "According to a study, this is true."
        packet = self.classifier.process(packet)
        assert len(packet.evidence_items) >= 1
