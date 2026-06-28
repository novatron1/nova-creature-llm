"""Final Truth Filter - validates final output before presentation."""
from nova.tiny_modules.base import TinyModule
from nova.schema import (
    MeaningPacket, TruthVerdict, NovaResponse,
    UncertaintyLevel, EvidenceClass,
)


class FinalTruthFilter(TinyModule):
    name = "final_truth_filter"

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Filter the packet for truthfulness before presentation."""
        # This module sets truth filter info on the packet
        # The final application happens in pipeline.py
        packet.module_chain.append(self.name)
        return packet

    def validate(self, draft: NovaResponse) -> TruthVerdict:
        """Validate a draft response for truthfulness."""
        issues = []
        unsupported_claims = []

        # Check for unsupported certainty
        if draft.uncertainty in (UncertaintyLevel.UNKNOWN, UncertaintyLevel.SPECULATIVE):
            if "proven" in draft.final_text.lower() or "definitely" in draft.final_text.lower():
                issues.append("Claims certainty without evidence")
                unsupported_claims.append("Overconfident language without support")

        # Check if meaning packet has evidence
        if draft.meaning:
            has_evidence = len(draft.meaning.evidence_items) > 0
            has_assumptions = len(draft.meaning.assumptions) > 0
            has_contradictions = len(draft.meaning.logic_check.contradictions) > 0

            if not has_evidence and not has_assumptions:
                # Vague query, no claims made
                pass
            elif has_assumptions and not has_evidence:
                # All assumptions, no evidence
                if any(a.risk_level == "high" for a in draft.meaning.assumptions):
                    issues.append("High-risk assumptions with no supporting evidence")
                    unsupported_claims.extend(
                        a.statement for a in draft.meaning.assumptions if a.risk_level == "high"
                    )

            if has_contradictions:
                issues.append("Internal contradictions detected in reasoning")

        # If science question, check for measurement
        if draft.meaning and draft.meaning.requires_science:
            has_measurement = any(
                e.evidence_class == EvidenceClass.MEASUREMENT
                for e in (draft.meaning.evidence_items or [])
            )
            if not has_measurement:
                issues.append("Science question without measurement evidence")

        passed = len(issues) == 0

        return TruthVerdict(
            passed=passed,
            issues=issues,
            unsupported_claims=unsupported_claims,
            certainty_rating=draft.uncertainty,
        )
