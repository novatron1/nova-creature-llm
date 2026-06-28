"""Counterargument Builder - constructs counterarguments."""
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket, Counterargument


class CounterargumentBuilder(TinyModule):
    name = "counterargument_builder"

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Build counterarguments for detected positions."""
        text = packet.cleaned_text.lower()

        # If philosophy question, add standard counterarguments
        if packet.requires_philosophy or "truth" in packet.key_terms:
            packet.counterarguments.append(Counterargument(
                opposing_claim="Truth is subjective and varies by perspective",
                reasoning="Different cultures, time periods, and individuals have different truth frameworks",
                strength="medium",
            ))

        if "meaning" in packet.key_terms:
            packet.counterarguments.append(Counterargument(
                opposing_claim="Meaning is a human construct without objective existence",
                reasoning="What we call meaning may simply be pattern recognition in neural processes",
                strength="medium",
            ))

        if packet.assumptions:
            for a in packet.assumptions:
                packet.counterarguments.append(Counterargument(
                    opposing_claim="The assumption '%s' may not hold" % a.statement[:40],
                    reasoning="Assumptions need verification before being treated as truth",
                    strength="medium",
                ))

        packet.module_chain.append(self.name)
        return packet
