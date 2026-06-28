"""Nova Pipeline - orchestrates the full processing flow."""
from typing import Optional
from nova.config import get_config
from nova.schema import (
    MeaningPacket, NovaResponse, SpecialistResult,
    TruthVerdict, UncertaintyLevel, EvidenceItem, EvidenceClass,
)
from nova.language_cortex import LanguageCortex
from nova.router_cortex import RouterCortex
from nova.final_voice import FinalVoice
from nova.memory import MemoryStore, TrainingLogger
from nova.model_provider import get_cached_provider

from nova.tiny_modules import (
    IntentDetector,
    QuestionSplitter,
    AssumptionDetector,
    BiasDetector,
    DefinitionChecker,
    EvidenceClassifier,
    LogicValidator,
    ContradictionFinder,
    CounterargumentBuilder,
    UncertaintyMarker,
    PrincipleConsistencyChecker,
    FinalTruthFilter,
)

from nova.specialist_cortex import (
    PhilosopherCortex,
    ScienceCortex,
    MathMeasurementCortex,
    KnowledgeCortex,
    CodeSkillCortex,
    WorldSystemsCortex,
)

from nova.agents.research_agent import ResearchAgent


class NovaPipeline:
    """Full Nova processing pipeline."""

    def __init__(self, offline: bool = False):
        self.config = get_config()
        self.offline = offline
        if offline:
            self.config.web["enabled"] = False

        # Build pipeline stages
        self.language_cortex = LanguageCortex()
        self.router = RouterCortex()
        self.final_voice = FinalVoice()

        # Tiny modules
        self.tiny_modules = [
            IntentDetector(),
            QuestionSplitter(),
            AssumptionDetector(),
            BiasDetector(),
            DefinitionChecker(),
            EvidenceClassifier(),
            LogicValidator(),
            ContradictionFinder(),
            CounterargumentBuilder(),
            UncertaintyMarker(),
            PrincipleConsistencyChecker(),
        ]
        self.truth_filter = FinalTruthFilter()

        # Specialist modules
        self.specialists = {
            "philosopher_cortex": PhilosopherCortex(),
            "science_cortex": ScienceCortex(),
            "math_cortex": MathMeasurementCortex(),
            "knowledge_cortex": KnowledgeCortex(),
            "code_skill_cortex": CodeSkillCortex(),
            "world_systems_cortex": WorldSystemsCortex(),
        }

        # Research agent
        self.research_agent = ResearchAgent()

        # Memory
        self.memory = MemoryStore()
        self.training_logger = TrainingLogger()

    def run(self, text: str, offline: Optional[bool] = None) -> NovaResponse:
        """Run the full pipeline on input text."""
        if offline is not None:
            self.offline = offline
            if offline:
                self.config.web["enabled"] = False

        # Stage 1: Language Cortex
        packet = self.language_cortex.process(text)
        packet.module_chain.append("language_cortex")

        # Stage 2: Tiny Modules
        packet = self._run_tiny_modules(packet)

        # Stage 2.5: Research Agents (if needed and web enabled)
        research_evidence = self._run_research_if_needed(packet)

        # Attach research evidence to packet
        if research_evidence:
            packet.evidence_items.extend(research_evidence)

        # Stage 3: Router
        route = self.router.route(packet)
        packet.module_chain.append("router_cortex(%s)" % ",".join(route))

        # Stage 4: Specialists
        specialist_results = []
        for module_name in route:
            specialist = self.specialists.get(module_name)
            if specialist:
                result = specialist.analyze(packet)
                specialist_results.append(result)
                packet.module_chain.append(module_name)

        # Build response
        response = NovaResponse(
            raw_question=text,
            meaning=packet,
            specialist_results=specialist_results,
            uncertainty=packet.uncertainty,
            module_chain=packet.module_chain,
        )

        # Stage 5: Truth Filter
        truth_verdict = self.truth_filter.validate(response)
        response.truth_verdict = truth_verdict

        # Stage 6: Final Voice
        self.final_voice.speak(response)

        # Log to memory
        self._log_to_memory(response, packet)

        return response

    def _run_tiny_modules(self, packet: MeaningPacket) -> MeaningPacket:
        """Run all tiny modules in sequence."""
        for module in self.tiny_modules:
            try:
                packet = module.process(packet)
            except Exception as e:
                packet.module_chain.append("%s(ERROR: %s)" % (module.name, str(e)))
        return packet

    def _run_research_if_needed(self, packet: MeaningPacket) -> list[EvidenceItem]:
        """If the packet requires research and web is enabled, run research agents.

        Returns a list of EvidenceItem objects from web search results.
        Returns empty list if research is not needed or web is disabled.
        """
        if not packet.requires_research:
            return []
        packet.module_chain.append("research_agent")
        if not self.config.web.get("enabled", False):
            return []

        query = packet.cleaned_text
        result = self.research_agent.execute(query)

        if not result["success"]:
            return []

        evidence = []
        data = result["data"] or {}
        results = data.get("results", [])
        fetched = data.get("fetched_content")

        for r in results[:5]:
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            source = r.get("source_name", "") or r.get("source", "")
            if snippet:
                evidence.append(EvidenceItem(
                    claim=snippet[:200],
                    evidence_class=EvidenceClass.VERIFIED_SOURCE,
                    source=url or source,
                    is_verifiable=True,
                    confidence=UncertaintyLevel.MODERATE,
                ))

        if fetched:
            evidence.append(EvidenceItem(
                claim="Fetched content from top search result",
                evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                source="web_fetch",
                is_verifiable=True,
                confidence=UncertaintyLevel.HIGH_CONFIDENCE,
            ))

        return evidence

    def _log_to_memory(self, response: NovaResponse, packet: MeaningPacket) -> None:
        """Log interaction to memory and training logger."""
        if self.config.memory.get("enabled", True):
            record = {
                "raw_input": response.raw_question,
                "meaning_packet": {
                    "intent": packet.primary_intent.value if packet.primary_intent else None,
                    "assumptions": [a.statement for a in packet.assumptions],
                    "bias_flags": packet.bias_flags,
                },
                "final_answer": response.final_text,
                "module_chain": response.module_chain,
                "confidence": 1.0 if response.truth_verdict and response.truth_verdict.passed else 0.5,
                "truth_filter_passed": response.truth_verdict.passed if response.truth_verdict else False,
            }
            self.memory.add(record)
            self.training_logger.save(record)
