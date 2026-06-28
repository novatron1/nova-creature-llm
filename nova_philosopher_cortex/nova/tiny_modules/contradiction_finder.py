"""Contradiction Finder - identifies internal contradictions."""
import re
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket, LogicCheck, LogicStatus


class ContradictionFinder(TinyModule):
    name = "contradiction_finder"

    CONTRADICTORY_PAIRS = [
        (r'\ball\b', r'\bnone\b'),
        (r'\balways\b', r'\bnever\b'),
        (r'\beveryone\b', r'\bno one\b'),
        (r'\beverything\b', r'\bnothing\b'),
        (r'\bdoes\b', r"\bdoes not\b"),
        (r'\bis\b', r"\bis not\b"),
        (r'\bcan\b', r'\bcannot\b'),
        (r'\bwill\b', r"\bwill not\b"),
    ]

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Check for internal contradictions."""
        text = packet.cleaned_text.lower()
        found_contradictions = []

        for pattern_a, pattern_b in self.CONTRADICTORY_PAIRS:
            has_a = bool(re.search(pattern_a, text))
            has_b = bool(re.search(pattern_b, text))
            if has_a and has_b:
                found_contradictions.append(
                    "Contains both '%s' and '%s'" % (pattern_a, pattern_b)
                )

        if found_contradictions:
            if packet.logic_check.status != LogicStatus.VALID:
                packet.logic_check.status = LogicStatus.CONTRADICTORY
            packet.logic_check.contradictions.extend(found_contradictions)

        packet.module_chain.append(self.name)
        return packet
