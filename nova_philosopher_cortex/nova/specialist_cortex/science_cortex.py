"""Science Cortex - scientific analysis and reasoning with builtin explanations."""
from nova.specialist_cortex.base import SpecialistCortex
from nova.schema import MeaningPacket, SpecialistResult, UncertaintyLevel, EvidenceClass


# ── Builtin science explanations ─────────────────────────────────────────
SCIENCE_EXPLANATIONS: dict[str, dict] = {
    "gravity": {
        "field": "Physics",
        "explanation": (
            "Gravity is a fundamental interaction that causes mutual attraction between all objects "
            "with mass or energy. On Earth, it gives a downward acceleration of 9.81 m/s². "
            "In general relativity, gravity is described as curvature of spacetime caused by mass."
        ),
        "evidence": "Measured by Cavendish experiment (1798); confirmed by gravitational lensing, "
                    "GPS relativity corrections, and LIGO gravitational wave detection.",
    },
    "speed of light": {
        "field": "Physics",
        "explanation": (
            "The speed of light in vacuum is 299,792,458 m/s — a universal physical constant. "
            "It is the maximum speed at which information or matter can travel, as established "
            "by Einstein's special relativity."
        ),
        "evidence": "First measured by Ole Rømer (1676); modern value defined by the meter's definition.",
    },
    "quantum mechanics": {
        "field": "Physics",
        "explanation": (
            "Quantum mechanics describes nature at the smallest scales — atoms, molecules, and "
            "subatomic particles. Key principles include wave-particle duality, quantization of energy, "
            "the uncertainty principle, and quantum entanglement."
        ),
        "evidence": "Confirmed by double-slit experiment, photoelectric effect, Stern-Gerlach experiment, "
                    "and countless modern applications (transistors, lasers, MRI).",
    },
    "evolution": {
        "field": "Biology",
        "explanation": (
            "Evolution by natural selection is the process by which species change over generations. "
            "Individuals with traits better suited to their environment survive and reproduce more, "
            "passing those traits on. Over long periods, this drives adaptation and speciation."
        ),
        "evidence": "Fossil records, comparative DNA analysis, observed antibiotic resistance, "
                    "and direct observation of finch beak evolution in the Galápagos.",
    },
    "dna": {
        "field": "Biology",
        "explanation": (
            "DNA (deoxyribonucleic acid) is a molecule that carries genetic instructions for "
            "the development, functioning, growth, and reproduction of all known organisms. "
            "Its structure is a double helix of nucleotides: A, T, C, and G."
        ),
        "evidence": "Structure discovered by Watson and Crick (1953) using X-ray crystallography "
                    "data from Rosalind Franklin.",
    },
    "relativity": {
        "field": "Physics",
        "explanation": (
            "Einstein's theory of relativity has two parts: special relativity (1905) describes how "
            "time and space are relative to the observer's motion, establishing E=mc². General "
            "relativity (1915) describes gravity as the curvature of spacetime."
        ),
        "evidence": "Confirmed by Eddington's solar eclipse observation (1919), GPS relativity corrections, "
                    "gravitational waves (LIGO 2015), and black hole imaging (EHT 2019).",
    },
    "climate change": {
        "field": "Earth Science",
        "explanation": (
            "Climate change refers to long-term shifts in global temperatures and weather patterns, "
            "primarily driven by human activities since the Industrial Revolution. The burning of "
            "fossil fuels releases CO₂ and other greenhouse gases that trap heat in the atmosphere."
        ),
        "evidence": "Direct CO₂ measurements (Keeling Curve since 1958), global temperature records, "
                    "ice core data, sea level rise measurements, and shrinking ice sheets.",
    },
    "chemistry": {
        "field": "Chemistry",
        "explanation": (
            "Chemistry is the scientific study of matter — its composition, structure, properties, "
            "and how it changes during chemical reactions. It bridges physics and biology, explaining "
            "everything from the bonding of atoms to the behavior of complex molecules."
        ),
        "evidence": "Experimental verification through spectroscopy, calorimetry, chromatography, "
                    "and countless reproducible reactions.",
    },
    "quantum physics": {
        "field": "Physics",
        "explanation": (
            "Quantum physics is the branch of physics that deals with phenomena at atomic and "
            "subatomic scales. It introduces concepts like quantized energy levels, wave-particle "
            "duality, the uncertainty principle, superposition, and quantum entanglement. "
            "It forms the foundation for modern electronics, chemistry, and nuclear physics."
        ),
        "evidence": "Experimental confirmation via the photoelectric effect (Einstein 1905), "
                    "double-slit interference, quantum tunneling in semiconductors, and Bell test experiments.",
    },
}


class ScienceCortex(SpecialistCortex):
    name = "science_cortex"

    def analyze(self, packet: MeaningPacket) -> SpecialistResult:
        result = SpecialistResult(
            module_name=self.name,
            uncertainty=UncertaintyLevel.MODERATE,
        )

        text = packet.cleaned_text.lower()
        fields = []
        matched_explanations = []

        # Detect fields and find matching explanations
        for kw, field in [
            ("physics", "Physics"), ("gravity", "Physics"),
            ("energy", "Physics"), ("force", "Physics"),
            ("quantum", "Physics"), ("relativity", "Physics"),
            ("speed of light", "Physics"),
            ("chemistry", "Chemistry"), ("atom", "Chemistry"),
            ("molecule", "Chemistry"), ("biology", "Biology"),
            ("dna", "Biology"), ("evolution", "Biology"),
            ("cell", "Biology"), ("climate", "Earth Science"),
            ("geology", "Earth Science"), ("astronomy", "Astronomy"),
            ("cosmos", "Astronomy"), ("universe", "Astronomy"),
        ]:
            if kw in text:
                fields.append(field)

        # Match explanations from builtin knowledge base
        for key, info in SCIENCE_EXPLANATIONS.items():
            if key in text:
                matched_explanations.append(info)

        if fields:
            unique_fields = list(set(fields))
            result.findings.append("Scientific fields: %s" % ", ".join(unique_fields))

        # Also use any evidence from research agents
        has_research_evidence = any(
            e.evidence_class in (EvidenceClass.VERIFIED_SOURCE, EvidenceClass.MEASUREMENT)
            for e in packet.evidence_items
        )

        if has_research_evidence:
            result.findings.append("Research evidence available from web search.")

        result.analysis = self._build_analysis(packet, matched_explanations, fields)
        result.evidence_assessed = packet.evidence_items

        if matched_explanations:
            result.confidence = 0.85
        elif has_research_evidence:
            result.confidence = 0.7
        else:
            result.confidence = 0.5

        return result

    def _build_analysis(self, packet: MeaningPacket,
                        explanations: list[dict],
                        fields: list) -> str:
        lines = []
        lines.append("=== Scientific Analysis ===")

        if fields:
            lines.append("Fields: %s" % ", ".join(set(fields)))
            lines.append("")

        if explanations:
            for exp in explanations:
                lines.append(exp["explanation"])
                lines.append("")
                lines.append("Supporting evidence: %s" % exp["evidence"])
                lines.append("")
        elif packet.evidence_items:
            lines.append("Evidence from research:")
            for e in packet.evidence_items:
                lines.append("  - %s [%s]" % (e.claim, e.evidence_class.value))
        else:
            lines.append("No specific scientific explanation found in builtin knowledge base.")
            lines.append("I can provide the general scientific method framework:")
            lines.append("")
            lines.append("Scientific method: observation → hypothesis → experiment → analysis → conclusion")
            lines.append("")
            lines.append("For a detailed answer, I would need to look up the specific topic via web research.")

        return "\n".join(lines)
