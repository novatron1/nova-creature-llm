"""Code Skill Cortex - programming analysis."""
from nova.specialist_cortex.base import SpecialistCortex
from nova.schema import MeaningPacket, SpecialistResult, UncertaintyLevel


class CodeSkillCortex(SpecialistCortex):
    name = "code_skill_cortex"

    def analyze(self, packet: MeaningPacket) -> SpecialistResult:
        result = SpecialistResult(
            module_name=self.name,
            uncertainty=UncertaintyLevel.MODERATE,
        )
        result.findings.append("Code-related query detected")
        result.analysis = self._build_analysis(packet)
        result.confidence = 0.5
        return result

    def _build_analysis(self, packet: MeaningPacket) -> str:
        lines = []
        lines.append("=== Code/Skill Analysis ===")
        lines.append("This module handles programming and technical implementation questions.")
        if packet.requires_research:
            lines.append("Combined with research: may need to look up documentation or APIs.")
        return "\n".join(lines)
