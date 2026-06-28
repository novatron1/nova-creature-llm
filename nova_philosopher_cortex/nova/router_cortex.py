"""Router Cortex - routes meaning packets to the right specialist modules."""
from typing import Optional
from nova.schema import MeaningPacket, IntentType


class RouterCortex:
    """Routes structured MeaningPackets to appropriate specialist modules."""

    def __init__(self):
        self.routes = {
            IntentType.PHILOSOPHY: ["philosopher_cortex"],
            IntentType.SCIENCE: ["science_cortex"],
            IntentType.MATH: ["math_cortex"],
            IntentType.ANALYSIS: ["philosopher_cortex", "science_cortex"],
            IntentType.RESEARCH: ["knowledge_cortex"],
            IntentType.CODE: ["code_skill_cortex"],
            IntentType.QUESTION: [],  # Determined by content
            IntentType.OPINION: ["philosopher_cortex"],
            IntentType.COMMAND: [],
            IntentType.GREETING: [],
            IntentType.UNKNOWN: ["knowledge_cortex"],
        }

    def route(self, packet: MeaningPacket) -> list[str]:
        """Determine which specialist modules to invoke."""
        modules = []

        # Primary route based on intent
        primary_modules = self.routes.get(packet.primary_intent, [])
        modules.extend(primary_modules)

        # Add modules based on flags
        if packet.requires_philosophy and "philosopher_cortex" not in modules:
            modules.append("philosopher_cortex")
        if packet.requires_science and "science_cortex" not in modules:
            modules.append("science_cortex")
        if packet.requires_math and "math_cortex" not in modules:
            modules.append("math_cortex")
        if packet.requires_research and "knowledge_cortex" not in modules:
            modules.append("knowledge_cortex")
        if packet.requires_code and "code_skill_cortex" not in modules:
            modules.append("code_skill_cortex")

        # Geography / factual knowledge routing
        text = packet.cleaned_text.lower()
        geo_keywords = ["capital of", "capital city", "population of", "located in",
                         "country", "city", "continent", "river", "mountain"]
        if any(kw in text for kw in geo_keywords):
            modules.append("knowledge_cortex")

        # Check for world systems in content
        ws_keywords = ["economy", "politics", "government", "law", "society",
                        "culture", "institution", "system", "policy"]
        if any(kw in text for kw in ws_keywords):
            modules.append("world_systems_cortex")

        # Remove duplicates
        seen = set()
        unique_modules = []
        for m in modules:
            if m not in seen:
                seen.add(m)
                unique_modules.append(m)

        packet.route_hint = ",".join(unique_modules) if unique_modules else "general"
        return unique_modules
