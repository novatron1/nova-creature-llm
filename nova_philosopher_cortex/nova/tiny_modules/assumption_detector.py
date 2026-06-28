"""Assumption Detector - deeper assumption analysis."""
import re
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket, Assumption


class AssumptionDetector(TinyModule):
    name = "assumption_detector"

    ADDITIONAL_PATTERNS = [
        (r'\bit stands to reason\b', True),
        (r'\bit goes without saying\b', True),
        (r'\bas we all know\b', True),
        (r'\bas everyone knows\b', True),
        (r'\bconventional wisdom\b', True),
        (r'\bcommon sense tells us\b', True),
        (r'\bnaturally\b', False),
        (r'\bsurely\b', False),
        (r'\bpresumably\b', False),
        (r'\bpractically\b', False),
        (r'\bvirtually\b', False),
        (r'\bessentially\b', False),
        (r'\bbasically\b', False),
    ]

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        text = packet.cleaned_text.lower()
        for pattern, is_high in self.ADDITIONAL_PATTERNS:
            if re.search(pattern, text):
                packet.assumptions.append(Assumption(
                    statement="Unsupported assumption marker: '%s'" % pattern,
                    trigger_words=[pattern.decode() if isinstance(pattern, bytes) else str(pattern)],
                    is_unsupported=True,
                    risk_level="high" if is_high else "medium",
                ))
        packet.module_chain.append(self.name)
        return packet
