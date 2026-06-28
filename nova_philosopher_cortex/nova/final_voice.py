"""Final Voice - transforms analysis into Nova's voice."""
from nova.schema import NovaResponse, MeaningPacket, TruthVerdict, UncertaintyLevel


class FinalVoice:
    """Produces the final Nova output from pipeline results."""

    def speak(self, response: NovaResponse) -> str:
        """Generate final text from pipeline results."""
        lines = []
        meaning = response.meaning
        truth = response.truth_verdict

        lines.append("NOVA")
        lines.append("=" * 60)

        # Opening
        if meaning and meaning.primary_intent.name != "UNKNOWN":
            lines.append("")
            lines.append("I have analyzed your question through my structured reasoning pipeline.")
            lines.append("")

        # Logic check summary
        if meaning and meaning.logic_check:
            if meaning.logic_check.contradictions:
                lines.append("[LOGIC WARNING] Internal contradictions detected:")
                for c in meaning.logic_check.contradictions:
                    lines.append("  - %s" % c)
                lines.append("")

        # Assumptions flagged
        if meaning and meaning.assumptions:
            lines.append("[ASSUMPTIONS EXAMINED]")
            lines.append("I detected potential unsupported assumptions in your question:")
            for a in meaning.assumptions[:3]:
                lines.append("  - %s" % a.statement)
            if len(meaning.assumptions) > 3:
                lines.append("  ... and %d more" % (len(meaning.assumptions) - 3))
            lines.append("")

        # Bias flags
        if meaning and meaning.bias_flags:
            lines.append("[BIAS AWARENESS]")
            lines.append("The following potential bias patterns were identified:")
            for b in meaning.bias_flags[:3]:
                lines.append("  - %s" % b)
            lines.append("")

        # Specialist results
        if response.specialist_results:
            for sr in response.specialist_results:
                if sr.analysis:
                    lines.append(sr.analysis)
                    lines.append("")

        # Missing variables
        if meaning and meaning.missing_variables:
            lines.append("[MISSING VARIABLES]")
            for mv in meaning.missing_variables[:3]:
                lines.append("  - %s" % mv)
            lines.append("")

        # Truth filter result
        if truth:
            if not truth.passed:
                lines.append("[TRUTH FILTER]")
                lines.append("The following issues were identified:")
                for issue in truth.issues:
                    lines.append("  - %s" % issue)
                if truth.unsupported_claims:
                    lines.append("Unsupported claims:")
                    for uc in truth.unsupported_claims:
                        lines.append("  - %s" % uc)
                lines.append("")

        # Uncertainty
        uncertainty_text = {
            UncertaintyLevel.CERTAIN: "high degree of certainty",
            UncertaintyLevel.HIGH_CONFIDENCE: "good confidence",
            UncertaintyLevel.MODERATE: "moderate confidence",
            UncertaintyLevel.LOW_CONFIDENCE: "low confidence",
            UncertaintyLevel.SPECULATIVE: "speculative - treat with caution",
            UncertaintyLevel.UNKNOWN: "cannot determine confidence level",
        }
        level = response.uncertainty or UncertaintyLevel.UNKNOWN
        lines.append("---")
        lines.append("[UNCERTAINTY LEVEL] %s" % uncertainty_text.get(level, "unknown"))
        lines.append("")

        # Final message
        lines.append("I aim to separate fact from inference, identify assumptions,")
        lines.append("and maintain intellectual honesty. Please question my analysis")
        lines.append("and help me refine my understanding.")
        lines.append("=" * 60)

        response.final_text = "\n".join(lines)
        return response.final_text
