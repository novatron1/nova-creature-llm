"""Bias Detector - flags potential bias in text."""
import re
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket


class BiasDetector(TinyModule):
    name = "bias_detector"

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        text = packet.cleaned_text.lower()
        flags = []

        # Loaded language
        loaded = [
            (r'\b(obviously|clearly|undeniably|indisputably|unquestionably)\b',
             "Loaded certainty language"),
            (r'\b(ridiculous|absurd|outrageous|preposterous)\b',
             "Loaded dismissive language"),
            (r'\b(supposedly|allegedly|so-called)\b',
             "Loaded skeptical language"),
            (r'\b(always|never|everyone|no one|nobody|everybody)\b',
             "Absolute generalization"),
            (r'\b(the problem with|the issue is|the trouble with)\b',
             "Loaded framing"),
        ]

        for pattern, label in loaded:
            if re.search(pattern, text):
                flags.append(label)

        # Add unique flags not already present
        for flag in flags:
            if flag not in packet.bias_flags:
                packet.bias_flags.append(flag)

        packet.module_chain.append(self.name)
        return packet
