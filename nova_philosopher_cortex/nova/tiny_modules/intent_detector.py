"""Intent Detector - refines intent classification."""
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket, IntentType


class IntentDetector(TinyModule):
    name = "intent_detector"

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Refine intent using deeper heuristics."""
        text = packet.cleaned_text.lower()

        # If raw intent is UNKNOWN but we have questions, mark as QUESTION
        if packet.primary_intent == IntentType.UNKNOWN:
            if packet.questions or text.endswith("?"):
                packet.primary_intent = IntentType.QUESTION

        # If philosophy was detected, check for specific sub-flavors
        if packet.requires_philosophy or IntentType.PHILOSOPHY in packet.secondary_intents:
            packet.module_chain.append(self.name)

        return packet
