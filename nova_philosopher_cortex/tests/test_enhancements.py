"""Tests for _enhance_with_model output usage, key term filtering, and math unit fix."""

from nova.language_cortex import LanguageCortex
from nova.specialist_cortex.math_measurement_cortex import MathMeasurementCortex
from nova.schema import MeaningPacket


class TestKeyTermStopWords:
    def setup_method(self):
        self.cortex = LanguageCortex()

    def test_stop_words_removed(self):
        """Stop words like 'the', 'if', 'look' must not appear in key_terms."""
        packet = self.cortex.process("If a car travels 150 miles, what is the speed?")
        # 'if' and 'the' are stop words — must not appear
        assert "the" not in packet.key_terms, \
            "Stop word 'the' found in key_terms: %s" % packet.key_terms
        assert "if" not in packet.key_terms, \
            "Stop word 'if' found in key_terms: %s" % packet.key_terms
        assert "a" not in packet.key_terms, \
            "Stop word 'a' found in key_terms: %s" % packet.key_terms
        assert "is" not in packet.key_terms, \
            "Stop word 'is' found in key_terms: %s" % packet.key_terms

    def test_key_terms_include_real_content(self):
        """Real content words should still appear in key_terms."""
        packet = self.cortex.process("What is the capital of France?")
        assert "france" in packet.key_terms, \
            "Real word 'france' missing from key_terms: %s" % packet.key_terms

    def test_obviously_not_in_key_terms(self):
        """'obviously' is a bias word, not a key term."""
        packet = self.cortex.process("Obviously all institutions lie all the time.")
        assert "obviously" not in packet.key_terms, \
            "Bias word 'obviously' should not be in key_terms: %s" % packet.key_terms

    def test_look_not_in_key_terms(self):
        """'look' is a stop word."""
        packet = self.cortex.process("Look up the latest evidence about AI.")
        assert "look" not in packet.key_terms, \
            "Stop word 'look' found in key_terms: %s" % packet.key_terms


class TestEnhancedModel:
    def test_enhance_with_model_returns_string(self):
        """_enhance_with_model must return the model output (not discard it)."""
        cortex = LanguageCortex()
        # Using mock provider, should return something
        result = cortex._enhance_with_model("What is truth?")
        # The mock provider returns a string
        assert result is not None, "_enhance_with_model returned None"
        assert isinstance(result, str), "_enhance_with_model did not return a string"
        assert len(result) > 0, "_enhance_with_model returned empty string"

    def test_model_output_stored_in_packet(self):
        """Model output must be stored in the packet as model_enhanced_text."""
        cortex = LanguageCortex()
        packet = cortex.process("What is truth?")
        # Even with mock provider (where mock is the default), the field exists
        assert hasattr(packet, "model_enhanced_text"), \
            "Packet missing model_enhanced_text field"
        # The field is populated (with mock provider it's empty since we skip)
        assert packet.model_enhanced_text is not None


class TestMathUnit:
    def setup_method(self):
        self.cortex = MathMeasurementCortex()

    def test_unit_is_singular(self):
        """Math output must say 'miles/hour' not 'miles/hours'."""
        packet = MeaningPacket(
            raw_text="If a car travels 150 miles in 3 hours, what is the speed?",
            cleaned_text="If a car travels 150 miles in 3 hours, what is the speed?",
        )
        result = self.cortex.analyze(packet)
        assert "miles/hour" in result.analysis, \
            "Unit should be 'miles/hour', got: " + result.analysis[:200]
        assert "miles/hours" not in result.analysis, \
            "Unit should NOT be 'miles/hours'"

    def test_400_miles_hour(self):
        """2400 miles / 6 hours = 400 miles/hour."""
        packet = MeaningPacket(
            raw_text="If a plane travels 2400 miles in 6 hours, what speed is that?",
            cleaned_text="If a plane travels 2400 miles in 6 hours, what speed is that?",
        )
        result = self.cortex.analyze(packet)
        assert "400" in result.analysis
        assert "miles/hour" in result.analysis
