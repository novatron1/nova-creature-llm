"""Uncertainty Marker - marks confidence levels."""
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket, UncertaintyLevel


class UncertaintyMarker(TinyModule):
    name = "uncertainty_marker"

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Determine overall uncertainty level based on available information."""
        has_assumptions = len(packet.assumptions) > 0
        has_evidence = len(packet.evidence_items) > 0
        has_definitions = len(packet.definitions) > 0
        has_bias = len(packet.bias_flags) > 0
        has_contradictions = len(packet.logic_check.contradictions) > 0

        if has_contradictions:
            packet.uncertainty = UncertaintyLevel.LOW_CONFIDENCE
        elif has_bias and has_assumptions:
            packet.uncertainty = UncertaintyLevel.LOW_CONFIDENCE
        elif has_assumptions and not has_evidence:
            packet.uncertainty = UncertaintyLevel.SPECULATIVE
        elif has_evidence and has_definitions and not has_assumptions:
            packet.uncertainty = UncertaintyLevel.HIGH_CONFIDENCE
        elif has_evidence or has_definitions:
            packet.uncertainty = UncertaintyLevel.MODERATE
        else:
            packet.uncertainty = UncertaintyLevel.UNKNOWN

        packet.module_chain.append(self.name)
        return packet
