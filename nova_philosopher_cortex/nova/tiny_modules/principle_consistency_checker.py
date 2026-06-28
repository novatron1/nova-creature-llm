"""Principle Consistency Checker - checks against Nova's core principles."""
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket, LogicCheck, LogicStatus


class PrincipleConsistencyChecker(TinyModule):
    name = "principle_consistency_checker"

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Check consistency with Nova's core principles."""
        issues = []

        # Principle: separate fact from inference
        ev_classes = {e.evidence_class for e in packet.evidence_items}
        if not ev_classes:
            issues.append("No evidence classification - cannot separate fact from inference")

        # Principle: identify missing variables
        if packet.questions and not packet.missing_variables:
            issues.append("Consider defining what variables are needed for a complete answer")

        # Principle: define terms
        if packet.key_terms and len(packet.definitions) < len(packet.key_terms):
            undefined = [t for t in packet.key_terms
                         if t not in [d.term for d in packet.definitions]]
            if undefined:
                issues.append("Undefined key terms: %s" % ", ".join(undefined[:3]))

        # Principle: mark uncertainty
        if packet.uncertainty.name == "UNKNOWN":
            issues.append("Uncertainty level not determined")

        if issues:
            packet.logic_check = LogicCheck(
                status=LogicStatus.INCOMPLETE,
                issues=packet.logic_check.issues + issues,
            )

        packet.module_chain.append(self.name)
        return packet
