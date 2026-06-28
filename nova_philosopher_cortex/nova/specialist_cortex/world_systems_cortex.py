"""World Systems Cortex - analysis of societal, political, and economic systems."""
from nova.specialist_cortex.base import SpecialistCortex
from nova.schema import MeaningPacket, SpecialistResult, UncertaintyLevel


class WorldSystemsCortex(SpecialistCortex):
    name = "world_systems_cortex"

    def analyze(self, packet: MeaningPacket) -> SpecialistResult:
        result = SpecialistResult(
            module_name=self.name,
            uncertainty=UncertaintyLevel.MODERATE,
        )
        text = packet.cleaned_text.lower()

        systems = []
        for kw, system in [
            ("economy", "Economics"), ("economic", "Economics"),
            ("money", "Economics"), ("market", "Economics"),
            ("politics", "Political Science"), ("government", "Political Science"),
            ("democracy", "Political Science"), ("law", "Legal Systems"),
            ("legal", "Legal Systems"), ("education", "Education Systems"),
            ("school", "Education Systems"), ("healthcare", "Healthcare"),
            ("medicine", "Healthcare"), ("military", "Military/Defense"),
            ("war", "Military/Defense"), ("media", "Media Systems"),
            ("journalism", "Media Systems"), ("religion", "Religious Systems"),
            ("church", "Religious Systems"), ("technology", "Technology Systems"),
            ("internet", "Technology Systems"),
        ]:
            if kw in text:
                systems.append(system)

        if systems:
            unique_systems = list(set(systems))
            result.findings.append("World systems: %s" % ", ".join(unique_systems))
        else:
            result.findings.append("General world systems analysis")

        result.analysis = "\n".join([
            "=== World Systems Analysis ===",
            "",
            "Systems identified: " + (", ".join(set(systems)) if systems else "General"),
            "",
            "Note: Analysis of human systems requires careful separation of:",
            "- Observed facts about how systems operate",
            "- Inferred patterns and trends",
            "- Theoretical frameworks used to interpret data",
            "- Value judgments about outcomes",
        ])
        result.confidence = 0.5
        return result
