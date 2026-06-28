"""
Core data schemas for Nova.
Every pipeline stage operates on these structured types.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class IntentType(str, Enum):
    QUESTION = "question"
    ANALYSIS = "analysis"
    RESEARCH = "research"
    PHILOSOPHY = "philosophy"
    MATH = "math"
    SCIENCE = "science"
    CODE = "code"
    OPINION = "opinion"
    COMMAND = "command"
    GREETING = "greeting"
    UNKNOWN = "unknown"


class UncertaintyLevel(str, Enum):
    CERTAIN = "certain"
    HIGH_CONFIDENCE = "high_confidence"
    MODERATE = "moderate"
    LOW_CONFIDENCE = "low_confidence"
    SPECULATIVE = "speculative"
    UNKNOWN = "unknown"


class EvidenceClass(str, Enum):
    DIRECT_OBSERVATION = "direct_observation"
    MEASUREMENT = "measurement"
    VERIFIED_SOURCE = "verified_source"
    EXPERT_CONSENSUS = "expert_consensus"
    REPRODUCIBLE_EXPERIMENT = "reproducible_experiment"
    LOGICAL_DEDUCTION = "logical_deduction"
    ANECDOTAL = "anecdotal"
    INFERENCE = "inference"
    ASSUMPTION = "assumption"
    UNSUPPORTED = "unsupported"
    NOT_PROVIDED = "not_provided"


class LogicStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNVERIFIED = "unverified"
    CONTRADICTORY = "contradictory"
    INCOMPLETE = "incomplete"


@dataclass
class Definition:
    """A term definition extracted from context."""
    term: str
    definition: str
    source: str = "inferred"
    confidence: UncertaintyLevel = UncertaintyLevel.MODERATE


@dataclass
class Assumption:
    """An assumption detected in the input."""
    statement: str
    trigger_words: list[str] = field(default_factory=list)
    is_unsupported: bool = True
    risk_level: str = "medium"  # low, medium, high


@dataclass
class EvidenceItem:
    """A piece of evidence cited or detected."""
    claim: str
    evidence_class: EvidenceClass = EvidenceClass.NOT_PROVIDED
    source: Optional[str] = None
    is_verifiable: bool = False
    confidence: UncertaintyLevel = UncertaintyLevel.UNKNOWN


@dataclass
class Counterargument:
    """A counterargument to a stated position."""
    opposing_claim: str
    reasoning: str
    strength: str = "medium"  # weak, medium, strong


@dataclass
class LogicCheck:
    """Result of a logic validation step."""
    status: LogicStatus = LogicStatus.UNVERIFIED
    issues: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)


@dataclass
class MeaningPacket:
    """
    The structured output of the Language Cortex.
    This is the canonical representation of user intent and meaning
    that all downstream modules operate on.
    """
    raw_text: str
    cleaned_text: str = ""
    primary_intent: IntentType = IntentType.UNKNOWN
    secondary_intents: list[IntentType] = field(default_factory=list)
    definitions: list[Definition] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    key_terms: list[str] = field(default_factory=list)
    requires_research: bool = False
    requires_math: bool = False
    requires_science: bool = False
    requires_philosophy: bool = False
    requires_code: bool = False
    uncertainty: UncertaintyLevel = UncertaintyLevel.UNKNOWN
    logic_check: LogicCheck = field(default_factory=LogicCheck)
    bias_flags: list[str] = field(default_factory=list)
    missing_variables: list[str] = field(default_factory=list)
    counterarguments: list[Counterargument] = field(default_factory=list)
    route_hint: str = "general"  # hint for router cortex
    model_enhanced_text: str = ""
    module_chain: list[str] = field(default_factory=list)


@dataclass
class SpecialistResult:
    """Output from a specialist cortex module."""
    module_name: str
    analysis: str = ""
    findings: list[str] = field(default_factory=list)
    assumptions_identified: list[str] = field(default_factory=list)
    evidence_assessed: list[EvidenceItem] = field(default_factory=list)
    logic_checks: list[LogicCheck] = field(default_factory=list)
    uncertainty: UncertaintyLevel = UncertaintyLevel.UNKNOWN
    confidence: float = 0.0


@dataclass
class TruthVerdict:
    """The result of the final truth filter."""
    passed: bool = True
    issues: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    certainty_rating: UncertaintyLevel = UncertaintyLevel.UNKNOWN
    corrected_statements: list[str] = field(default_factory=list)


@dataclass
class NovaResponse:
    """The final structured output of the full pipeline."""
    raw_question: str
    meaning: Optional[MeaningPacket] = None
    specialist_results: list[SpecialistResult] = field(default_factory=list)
    truth_verdict: Optional[TruthVerdict] = None
    final_text: str = ""
    module_chain: list[str] = field(default_factory=list)
    uncertainty: UncertaintyLevel = UncertaintyLevel.UNKNOWN
    model_used: str = "mock"
