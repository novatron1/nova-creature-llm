"""Tests for Question Splitter."""
from nova.tiny_modules.question_splitter import QuestionSplitter
from nova.schema import MeaningPacket


class TestQuestionSplitter:
    def setup_method(self):
        self.splitter = QuestionSplitter()

    def test_single_question(self):
        packet = MeaningPacket(raw_text="What is truth?")
        packet.cleaned_text = "What is truth?"
        packet = self.splitter.process(packet)
        assert len(packet.questions) >= 1

    def test_multi_question(self):
        packet = MeaningPacket(raw_text="What is truth? Why does it matter?")
        packet.cleaned_text = "What is truth? Why does it matter?"
        packet = self.splitter.process(packet)
        assert len(packet.questions) >= 1

    def test_module_chain(self):
        packet = MeaningPacket(raw_text="Test")
        packet.cleaned_text = "Test"
        packet = self.splitter.process(packet)
        assert "question_splitter" in packet.module_chain
