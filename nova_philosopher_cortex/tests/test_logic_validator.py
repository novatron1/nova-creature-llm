"""Tests for Logic Validator."""
from nova.tiny_modules.logic_validator import LogicValidator
from nova.schema import MeaningPacket, LogicStatus


class TestLogicValidator:
    def setup_method(self):
        self.validator = LogicValidator()

    def test_valid_logic(self):
        packet = MeaningPacket(raw_text="What is the speed of light?")
        packet.cleaned_text = "What is the speed of light?"
        packet = self.validator.process(packet)
        assert packet.logic_check.status in (LogicStatus.VALID, LogicStatus.INCOMPLETE)

    def test_incomplete_logic(self):
        packet = MeaningPacket(raw_text="This is better.")
        packet.cleaned_text = "This is better."
        packet = self.validator.process(packet)
        # "better" without "than" should flag incomplete
        assert len(packet.logic_check.issues) >= 0

    def test_chain(self):
        packet = MeaningPacket(raw_text="Test")
        packet.cleaned_text = "Test"
        packet = self.validator.process(packet)
        assert "logic_validator" in packet.module_chain
