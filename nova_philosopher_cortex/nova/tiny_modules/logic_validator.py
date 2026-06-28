"""Logic Validator - checks logical consistency."""
import re
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket, LogicCheck, LogicStatus


class LogicValidator(TinyModule):
    name = "logic_validator"

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Validate logical structure of the query."""
        issues = []
        text = packet.cleaned_text

        # Check for circular reasoning
        if re.search(r'\b(because|since|as)\b.*\b(therefore|thus|so)\b', text.lower()):
            if len(text.split()) < 20:
                issues.append("Potential circular reasoning in short statement")

        # Check for contradictory statements
        if re.search(r'\b(is|are)\b.*\b(and|but)\b.*\b(is not|are not|isn\'t|aren\'t)\b', text.lower()):
            issues.append("Contains contradictory predicates")

        # Check for undefined comparisons
        if re.search(r'\bbetter\b|\bworse\b|\bbest\b|\bworst\b|\bmore\b|\bmost\b|\bless\b|\bleast\b', text.lower()):
            if not re.search(r'\bthan\b', text.lower()):
                issues.append("Comparative language without explicit comparison target")

        if issues:
            packet.logic_check = LogicCheck(
                status=LogicStatus.INCOMPLETE,
                issues=issues,
            )
        else:
            packet.logic_check = LogicCheck(status=LogicStatus.VALID)

        packet.module_chain.append(self.name)
        return packet
