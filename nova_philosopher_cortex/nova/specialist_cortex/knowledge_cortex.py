"""Knowledge Cortex - general knowledge and structured recall.

Contains a builtin knowledge base for common facts, and uses evidence_items
from research agents when available.
"""
from nova.specialist_cortex.base import SpecialistCortex
from nova.schema import MeaningPacket, SpecialistResult, UncertaintyLevel, EvidenceClass


# ── Builtin knowledge base ──────────────────────────────────────────────
FACTS: dict[str, list[dict]] = {
    # Capitals
    "capital of france": [{"answer": "Paris", "source": "builtin", "type": "geography"}],
    "france capital": [{"answer": "Paris", "source": "builtin", "type": "geography"}],
    "capital of germany": [{"answer": "Berlin", "source": "builtin", "type": "geography"}],
    "capital of japan": [{"answer": "Tokyo", "source": "builtin", "type": "geography"}],
    "capital of italy": [{"answer": "Rome", "source": "builtin", "type": "geography"}],
    "capital of uk": [{"answer": "London", "source": "builtin", "type": "geography"}],
    "capital of england": [{"answer": "London", "source": "builtin", "type": "geography"}],
    "capital of spain": [{"answer": "Madrid", "source": "builtin", "type": "geography"}],
    "capital of china": [{"answer": "Beijing", "source": "builtin", "type": "geography"}],
    "capital of russia": [{"answer": "Moscow", "source": "builtin", "type": "geography"}],
    "capital of canada": [{"answer": "Ottawa", "source": "builtin", "type": "geography"}],
    "capital of australia": [{"answer": "Canberra", "source": "builtin", "type": "geography"}],
    "capital of india": [{"answer": "New Delhi", "source": "builtin", "type": "geography"}],
    "capital of brazil": [{"answer": "Brasília", "source": "builtin", "type": "geography"}],

    # Scientific constants
    "speed of light": [{"answer": "299,792,458 meters per second (about 300,000 km/s)",
                        "source": "builtin", "type": "physics"}],
    "speed of sound": [{"answer": "343 meters per second (at sea level, 20°C)",
                        "source": "builtin", "type": "physics"}],
    "gravity": [{"answer": "9.81 m/s² on Earth's surface (acceleration due to gravity)",
                 "source": "builtin", "type": "physics"}],
    "gravitational constant": [{"answer": "6.674 × 10⁻¹¹ N·m²/kg²",
                                "source": "builtin", "type": "physics"}],
    "planck constant": [{"answer": "6.626 × 10⁻³⁴ J·s", "source": "builtin", "type": "physics"}],
    "avogadro number": [{"answer": "6.022 × 10²³ per mole", "source": "builtin", "type": "chemistry"}],
    "boiling point of water": [{"answer": "100 °C (212 °F) at sea level",
                                "source": "builtin", "type": "chemistry"}],
    "freezing point of water": [{"answer": "0 °C (32 °F) at sea level",
                                 "source": "builtin", "type": "chemistry"}],
    "distance to the moon": [{"answer": "384,400 kilometers (about 239,000 miles)",
                              "source": "builtin", "type": "astronomy"}],
    "distance to the sun": [{"answer": "149.6 million kilometers (1 AU)",
                             "source": "builtin", "type": "astronomy"}],

    # Human body
    "bones in human body": [{"answer": "206 bones in an adult human",
                             "source": "builtin", "type": "biology"}],
    "human heart beats": [{"answer": "About 100,000 times per day (roughly 2.5 billion times in a lifetime)",
                           "source": "builtin", "type": "biology"}],
}


class KnowledgeCortex(SpecialistCortex):
    name = "knowledge_cortex"

    def analyze(self, packet: MeaningPacket) -> SpecialistResult:
        result = SpecialistResult(
            module_name=self.name,
            uncertainty=UncertaintyLevel.MODERATE,
        )

        # First: try to answer from builtin facts
        answers = self._lookup_facts(packet)

        # Second: incorporate evidence from research agents if available
        research_evidence = [
            e for e in packet.evidence_items
            if e.evidence_class in (EvidenceClass.VERIFIED_SOURCE, EvidenceClass.DIRECT_OBSERVATION)
        ]

        result.analysis = self._build_analysis(packet, answers, research_evidence)
        result.evidence_assessed = packet.evidence_items

        if answers:
            result.confidence = 0.85
            result.uncertainty = UncertaintyLevel.HIGH_CONFIDENCE
        elif research_evidence:
            result.confidence = 0.7
            result.uncertainty = UncertaintyLevel.MODERATE
        else:
            result.confidence = 0.5
            result.uncertainty = UncertaintyLevel.MODERATE

        if answers:
            result.findings.append("Found %d relevant fact(s)" % len(answers))

        return result

    def _lookup_facts(self, packet: MeaningPacket) -> list[dict]:
        """Search builtin facts using key terms and raw text."""
        results = []
        search_text = packet.cleaned_text.lower()

        for key, facts in FACTS.items():
            key_words = set(key.split())
            # Check if all key words appear in the query
            if all(kw in search_text for kw in key_words):
                results.extend(facts)

        # Also check key terms for partial matches
        if not results:
            for term in packet.key_terms:
                for key, facts in FACTS.items():
                    if term in key:
                        results.extend(facts)

        # De-duplicate
        seen = set()
        unique = []
        for r in results:
            key = r["answer"]
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    def _build_analysis(self, packet: MeaningPacket,
                        answers: list[dict],
                        research_evidence: list) -> str:
        lines = []
        lines.append("=== Knowledge Analysis ===")

        if answers:
            lines.append("")
            for a in answers:
                lines.append("Answer: %s" % a["answer"])
                lines.append("Source: %s (%s)" % (a["source"], a["type"]))
        else:
            lines.append("")
            lines.append("No builtin fact found for this query.")

        if research_evidence:
            lines.append("")
            lines.append("Additional research evidence:")
            for e in research_evidence:
                lines.append("  - %s" % e.claim)

        if packet.key_terms:
            lines.append("")
            lines.append("Queried topics: %s" % ", ".join(packet.key_terms[:5]))

        if not answers and not research_evidence:
            lines.append("")
            lines.append("No verifiable sources available. This is knowledge recall without citation.")

        return "\n".join(lines)
