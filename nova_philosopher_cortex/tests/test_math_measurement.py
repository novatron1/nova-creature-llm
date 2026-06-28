"""Tests for Math & Measurement Cortex."""
from nova.specialist_cortex.math_measurement_cortex import MathMeasurementCortex
from nova.schema import MeaningPacket


class TestMathMeasurement:
    def setup_method(self):
        self.cortex = MathMeasurementCortex()

    def test_speed_calculation(self):
        packet = MeaningPacket(raw_text="If a plane travels 2400 miles in 6 hours, what speed is that?")
        packet.cleaned_text = "If a plane travels 2400 miles in 6 hours, what speed is that?"
        result = self.cortex.analyze(packet)
        assert "400" in result.analysis
        assert "miles/hour" in result.analysis or "miles/hours" in result.analysis

    def test_car_speed(self):
        packet = MeaningPacket(raw_text="If a car travels 150 miles in 3 hours, what is the speed?")
        packet.cleaned_text = "If a car travels 150 miles in 3 hours, what is the speed?"
        result = self.cortex.analyze(packet)
        assert "50" in result.analysis
        assert "miles/hour" in result.analysis or "miles/hours" in result.analysis

    def test_module_name(self):
        packet = MeaningPacket(raw_text="Test")
        packet.cleaned_text = "Test"
        result = self.cortex.analyze(packet)
        assert result.module_name == "math_cortex"
