"""Evidence Classifier - classifies the type of evidence provided."""
import re
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket, EvidenceItem, EvidenceClass, UncertaintyLevel


class EvidenceClassifier(TinyModule):
    name = "evidence_classifier"

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Scan text and classify any evidence claims."""
        text = packet.cleaned_text

        # Check for measurement claims
        if re.search(r'\b\d+\.?\d*\s*(miles|km|kg|g|lbs|hours|minutes|seconds|mph|kmh|°|%)', text):
            packet.evidence_items.append(EvidenceItem(
                claim="Contains numeric measurement data",
                evidence_class=EvidenceClass.MEASUREMENT,
                is_verifiable=True,
                confidence=UncertaintyLevel.HIGH_CONFIDENCE,
            ))

        # Check for source attribution
        if re.search(r'\b(according to|study says|research shows|found that|reported)\b', text.lower()):
            packet.evidence_items.append(EvidenceItem(
                claim="References external source",
                evidence_class=EvidenceClass.VERIFIED_SOURCE,
                source="attributed",
                is_verifiable=True,
                confidence=UncertaintyLevel.MODERATE,
            ))

        # Check for logical deduction
        if re.search(r'\b(therefore|thus|hence|consequently|so|because|since)\b', text.lower()):
            packet.evidence_items.append(EvidenceItem(
                claim="Makes logical deduction",
                evidence_class=EvidenceClass.LOGICAL_DEDUCTION,
                is_verifiable=False,
                confidence=UncertaintyLevel.MODERATE,
            ))

        packet.module_chain.append(self.name)
        return packet
