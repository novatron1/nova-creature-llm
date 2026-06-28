"""Definition Checker - checks if key terms are defined."""
import re
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket, Definition, UncertaintyLevel


class DefinitionChecker(TinyModule):
    name = "definition_checker"

    BUILTIN_DEFINITIONS = {
        "truth": "Conformity to fact or reality; accuracy.",
        "knowledge": "Justified true belief; information acquired through experience or education.",
        "consciousness": "Awareness of one's own existence, sensations, thoughts, and environment.",
        "reality": "The state of things as they actually exist, rather than as they may be perceived.",
        "justice": "Fair treatment; moral rightness; the quality of being just.",
        "freedom": "The power to act, speak, or think without hindrance or restraint.",
        "existence": "The fact or state of living or having objective reality.",
        "morality": "Principles concerning the distinction between right and wrong behavior.",
        "ethics": "Moral principles governing behavior; the branch of knowledge dealing with moral principles.",
        "mind": "The faculty of consciousness, thought, and reasoning.",
        "truth": "Conformity to fact or reality; accuracy.",
        "meaning": "What is intended to be communicated; significance.",
        "reason": "The power of the mind to think, understand, and form judgments logically.",
        "logic": "Reasoning conducted according to strict principles of validity.",
        "science": "The systematic study of the structure and behavior of the physical and natural world.",
    }

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Check if key terms have definitions."""
        for term in packet.key_terms:
            if term in self.BUILTIN_DEFINITIONS:
                packet.definitions.append(Definition(
                    term=term,
                    definition=self.BUILTIN_DEFINITIONS[term],
                    source="builtin",
                    confidence=UncertaintyLevel.HIGH_CONFIDENCE,
                ))

        # Also check for undefined terms
        defined_terms = {d.term for d in packet.definitions}
        for term in packet.key_terms:
            if term not in defined_terms:
                # Mark as missing definition
                packet.missing_variables.append(
                    "Undefined term: '%s' needs definition" % term
                )

        packet.module_chain.append(self.name)
        return packet
