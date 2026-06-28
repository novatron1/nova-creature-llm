"""Tests for the Language Cortex."""
import pytest
from nova.language_cortex import LanguageCortex
from nova.schema import IntentType


class TestLanguageCortex:
    def setup_method(self):
        self.cortex = LanguageCortex()

    def test_process_question(self):
        packet = self.cortex.process("What is truth?")
        assert packet.raw_text == "What is truth?"
        # "What is truth?" is classified as QUESTION with PHILOSOPHY secondary
        assert IntentType.PHILOSOPHY in packet.secondary_intents or packet.requires_philosophy
        assert len(packet.questions) > 0

    def test_process_math(self):
        packet = self.cortex.process("If a plane travels 2400 miles in 6 hours, what speed is that?")
        # Math detection: "speed" keyword + number + "miles" + "hours"
        assert packet.requires_math is True

    def test_process_science(self):
        packet = self.cortex.process("What is quantum physics?")
        assert packet.primary_intent == IntentType.SCIENCE or packet.requires_science

    def test_process_greeting(self):
        packet = self.cortex.process("Hello")
        assert packet.primary_intent == IntentType.GREETING

    def test_assumption_detection_obviously(self):
        packet = self.cortex.process("Obviously all institutions lie all the time.")
        assert len(packet.assumptions) > 0
        assert packet.bias_flags is not None

    def test_bias_detection(self):
        packet = self.cortex.process("Everyone knows that this is clearly true.")
        assert len(packet.assumptions) > 0
        # Should have bias flags for absolute language and false certainty
        assert len(packet.bias_flags) >= 1

    def test_question_extraction(self):
        packet = self.cortex.process("What is truth? Why is it important?")
        assert len(packet.questions) >= 1

    def test_key_terms(self):
        packet = self.cortex.process("What is consciousness?")
        assert len(packet.key_terms) > 0

    def test_clean_text(self):
        packet = self.cortex.process("  What   is   truth?  ")
        assert packet.cleaned_text == "What is truth?"

    def test_research_detection(self):
        packet = self.cortex.process("Look up the latest evidence about AI.")
        assert packet.requires_research is True
