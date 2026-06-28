"""Tests for Nova core schemas."""
import pytest
from nova.schema import (
    MeaningPacket, IntentType, NovaResponse, TruthVerdict,
    SpecialistResult, UncertaintyLevel, LogicCheck, LogicStatus,
    Assumption, EvidenceItem, EvidenceClass, Definition,
)


class TestMeaningPacket:
    def test_default_creation(self):
        packet = MeaningPacket(raw_text="What is truth?")
        assert packet.raw_text == "What is truth?"
        assert packet.primary_intent == IntentType.UNKNOWN
        assert packet.uncertainty == UncertaintyLevel.UNKNOWN
        assert packet.questions == []
        assert packet.assumptions == []
        assert packet.bias_flags == []

    def test_with_all_fields(self):
        packet = MeaningPacket(
            raw_text="Test",
            cleaned_text="test",
            primary_intent=IntentType.PHILOSOPHY,
            secondary_intents=[IntentType.ANALYSIS],
            questions=["What is truth?"],
            requires_research=True,
        )
        assert packet.primary_intent == IntentType.PHILOSOPHY
        assert IntentType.ANALYSIS in packet.secondary_intents
        assert packet.questions[0] == "What is truth?"
        assert packet.requires_research is True


class TestNovaResponse:
    def test_default_creation(self):
        resp = NovaResponse(raw_question="Hello")
        assert resp.final_text == ""
        assert resp.truth_verdict is None
        assert resp.module_chain == []

    def test_with_meaning(self):
        meaning = MeaningPacket(raw_text="What is justice?")
        resp = NovaResponse(raw_question="What is justice?", meaning=meaning)
        assert resp.meaning is not None
        assert resp.meaning.raw_text == "What is justice?"


class TestTruthVerdict:
    def test_passed_default(self):
        v = TruthVerdict()
        assert v.passed is True
        assert v.issues == []

    def test_failed(self):
        v = TruthVerdict(passed=False, issues=["No evidence"], unsupported_claims=["Claim A"])
        assert v.passed is False
        assert "No evidence" in v.issues


class TestSpecialistResult:
    def test_creation(self):
        r = SpecialistResult(module_name="philosopher")
        assert r.module_name == "philosopher"
        assert r.analysis == ""
        assert r.confidence == 0.0

    def test_with_data(self):
        r = SpecialistResult(
            module_name="science",
            analysis="Test analysis",
            findings=["Finding 1"],
            uncertainty=UncertaintyLevel.HIGH_CONFIDENCE,
            confidence=0.85,
        )
        assert r.analysis == "Test analysis"
        assert len(r.findings) == 1
        assert r.uncertainty == UncertaintyLevel.HIGH_CONFIDENCE
        assert r.confidence == 0.85


class TestAssumption:
    def test_creation(self):
        a = Assumption(statement="All X are Y")
        assert a.is_unsupported is True
        assert a.risk_level == "medium"


class TestEvidenceItem:
    def test_default(self):
        e = EvidenceItem(claim="Something is true")
        assert e.evidence_class == EvidenceClass.NOT_PROVIDED
        assert e.is_verifiable is False

    def test_direct(self):
        e = EvidenceItem(
            claim="Water boils at 100C",
            evidence_class=EvidenceClass.MEASUREMENT,
            source="Direct observation",
            is_verifiable=True,
        )
        assert e.evidence_class == EvidenceClass.MEASUREMENT
        assert e.is_verifiable is True


class TestDefinition:
    def test_creation(self):
        d = Definition(term="truth", definition="Conformity to fact")
        assert d.source == "inferred"
        assert d.confidence == UncertaintyLevel.MODERATE
