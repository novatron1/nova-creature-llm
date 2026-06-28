"""Philosopher Cortex - philosophical analysis and reasoning."""
from nova.specialist_cortex.base import SpecialistCortex
from nova.schema import MeaningPacket, SpecialistResult, UncertaintyLevel


class PhilosopherCortex(SpecialistCortex):
    name = "philosopher_cortex"

    def analyze(self, packet: MeaningPacket) -> SpecialistResult:
        result = SpecialistResult(
            module_name=self.name,
            uncertainty=UncertaintyLevel.MODERATE,
        )

        # Determine philosophical domain
        text = packet.cleaned_text.lower()
        domains = []
        for kw, domain in [
            ("truth", "Epistemology"), ("knowledge", "Epistemology"),
            ("belief", "Epistemology"), ("reality", "Metaphysics"),
            ("existence", "Metaphysics"), ("consciousness", "Philosophy of Mind"),
            ("mind", "Philosophy of Mind"), ("ethics", "Ethics"),
            ("morality", "Ethics"), ("justice", "Political Philosophy"),
            ("freedom", "Political Philosophy"), ("meaning", "Existentialism"),
            ("purpose", "Existentialism"), ("logic", "Logic"),
            ("reason", "Logic"), ("beauty", "Aesthetics"),
            ("art", "Aesthetics"),
        ]:
            if kw in text:
                domains.append(domain)

        if domains:
            unique_domains = list(set(domains))
            result.findings.append("Philosophical domains: %s" % ", ".join(unique_domains))

        # Generate analysis
        result.analysis = self._build_analysis(packet, domains)

        # Mark evidence
        result.evidence_assessed = packet.evidence_items
        if not packet.evidence_items:
            result.findings.append("Note: No empirical evidence provided - this is a conceptual analysis")

        result.confidence = 0.6 if packet.assumptions else 0.8
        return result

    def _build_analysis(self, packet: MeaningPacket, domains: list) -> str:
        lines = []
        lines.append("=== Philosophical Analysis ===")

        if domains:
            lines.append("Domain: %s" % ", ".join(set(domains)))

        # Key terms
        if packet.key_terms:
            lines.append("Key concepts: %s" % ", ".join(packet.key_terms[:5]))

        # Definitions
        if packet.definitions:
            lines.append("\nDefinitions:")
            for d in packet.definitions:
                lines.append("- %s: %s" % (d.term, d.definition))

        # Assumptions
        if packet.assumptions:
            lines.append("\nAssumptions to examine:")
            for a in packet.assumptions:
                lines.append("- [%s risk] %s" % (a.risk_level, a.statement))

        # Counterarguments
        if packet.counterarguments:
            lines.append("\nCounterarguments:")
            for c in packet.counterarguments:
                lines.append("- %s (%s)" % (c.opposing_claim, c.strength))

        return "\n".join(lines)
