"""Tests for Assumption Detector."""
from nova.tiny_modules.assumption_detector import AssumptionDetector
from nova.schema import MeaningPacket


class TestAssumptionDetector:
    def setup_method(self):
        self.detector = AssumptionDetector()

    def test_no_assumptions(self):
        packet = MeaningPacket(raw_text="What is the speed of light?")
        packet.cleaned_text = "What is the speed of light?"
        packet = self.detector.process(packet)
        assert len(packet.assumptions) == 0

    def test_assumption_detected(self):
        packet = MeaningPacket(raw_text="As we all know, the earth is flat.")
        packet.cleaned_text = "As we all know, the earth is flat."
        packet = self.detector.process(packet)
        assert len(packet.assumptions) > 0

    def test_chain(self):
        packet = MeaningPacket(raw_text="Test")
        packet.cleaned_text = "Test"
        packet = self.detector.process(packet)
        assert "assumption_detector" in packet.module_chain
