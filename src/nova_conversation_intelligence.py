"""Provider-independent conversation understanding shared across Nova.

This module classifies a managed chat turn once so downstream routing,
grounding, repair, and model-selection code do not make contradictory
decisions. It is deterministic, does not call a model, and never logs prompt
content in its safe trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Mapping


CONVERSATION_INTELLIGENCE_VERSION = "1.0"


@dataclass(frozen=True)
class ConversationDecision:
    """One bounded, privacy-safe routing decision for a managed chat turn."""

    intent_family: str
    intent_subtype: str
    dialogue_act: str
    context_required: bool
    factual_evidence_required: bool
    current_information_required: bool
    memory_recommended: bool
    reasoning_mode: str
    initial_model_tier: str
    repair_policy: str
    confidence: float
    expected_qualities: tuple[str, ...] = field(default_factory=tuple)
    signals: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = CONVERSATION_INTELLIGENCE_VERSION
    text_hash: str = ""

    def safe_trace(self) -> dict[str, Any]:
        """Return routing metadata without the user's prompt."""

        return {
            "schema_version": self.schema_version,
            "intent_family": self.intent_family,
            "intent_subtype": self.intent_subtype,
            "dialogue_act": self.dialogue_act,
            "context_required": self.context_required,
            "factual_evidence_required": self.factual_evidence_required,
            "current_information_required": self.current_information_required,
            "memory_recommended": self.memory_recommended,
            "reasoning_mode": self.reasoning_mode,
            "initial_model_tier": self.initial_model_tier,
            "repair_policy": self.repair_policy,
            "confidence": self.confidence,
            "expected_qualities": list(self.expected_qualities),
            "signals": list(self.signals),
            "text_hash": self.text_hash,
            "content_logged": False,
        }


def _canonicalize(value: str) -> str:
    return re.sub(r"[^a-z0-9']+", " ", str(value or "").lower()).strip()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _decision(
    canonical: str,
    intent_family: str,
    intent_subtype: str,
    dialogue_act: str,
    *,
    context_required: bool = False,
    factual_evidence_required: bool = False,
    current_information_required: bool = False,
    memory_recommended: bool = False,
    reasoning_mode: str = "fast",
    initial_model_tier: str = "small",
    repair_policy: str = "bounded_model_repair",
    confidence: float = 0.9,
    expected_qualities: tuple[str, ...] = ("direct", "relevant"),
    signals: tuple[str, ...] = (),
) -> ConversationDecision:
    return ConversationDecision(
        intent_family=intent_family,
        intent_subtype=intent_subtype,
        dialogue_act=dialogue_act,
        context_required=context_required,
        factual_evidence_required=factual_evidence_required,
        current_information_required=current_information_required,
        memory_recommended=memory_recommended,
        reasoning_mode=reasoning_mode,
        initial_model_tier=initial_model_tier,
        repair_policy=repair_policy,
        confidence=max(0.0, min(float(confidence), 1.0)),
        expected_qualities=expected_qualities,
        signals=signals,
        text_hash=_hash_text(canonical),
    )


def understand_conversation_turn(text: str) -> ConversationDecision:
    """Classify one user turn using safe, deterministic precedence rules."""

    canonical = _canonicalize(text)

    # Permission and high-risk actions outrank conversational interpretations.
    # Transaction verbs only count when Nova is actually being directed to
    # perform them; a hardship statement such as "I cannot pay rent" is not an
    # action request.
    directed_action = re.search(
        r"^(?:nova\s+)?(?:please\s+)?"
        r"(?:send|publish|post|deploy|delete|erase|wipe|purchase|buy|pay|transfer)\b"
        r"|\bplease\s+"
        r"(?:send|publish|post|deploy|delete|erase|wipe|purchase|buy|pay|transfer)\b"
        r"|\b(?:can|could|will|would)\s+(?:you|nova)\s+(?:please\s+)?"
        r"(?:send|publish|post|deploy|delete|erase|wipe|purchase|buy|pay|transfer)\b"
        r"|\b(?:need|want|would\s+like)\s+(?:you|nova)\s+to\s+"
        r"(?:send|publish|post|deploy|delete|erase|wipe|purchase|buy|pay|transfer)\b",
        canonical,
    )
    if (
        directed_action
        or re.search(
            r"\b(?:move|drive|turn|start|stop)\s+(?:the\s+)?robot\b"
            r"|\b(?:run|execute)\s+(?:a\s+)?(?:shell|command|script)\b",
            canonical,
        )
    ):
        return _decision(
            canonical,
            "permission_action",
            "high_impact_action",
            "request_authorization",
            context_required=True,
            reasoning_mode="agent",
            repair_policy="approval_required",
            expected_qualities=("explicit authorization", "observed result", "safe"),
            signals=("high_impact_verb",),
            confidence=0.98,
        )

    # Volatile facts must never be generalized into social use of words such
    # as "today" or "current".
    if (
        re.search(r"\b(?:current|currently|latest|today'?s?|right now|live|newest)\b", canonical)
        and re.search(
            r"\b(?:mayor|president|governor|ceo|news|weather|price|score|law|"
            r"regulation|version|officeholder|schedule)\b",
            canonical,
        )
    ):
        return _decision(
            canonical,
            "current_fact",
            "volatile_lookup",
            "answer",
            factual_evidence_required=True,
            current_information_required=True,
            reasoning_mode="verify",
            repair_policy="strict_evidence",
            expected_qualities=("fresh evidence", "source attribution", "uncertainty"),
            signals=("volatile_entity",),
            confidence=0.98,
        )

    if re.search(
        r"\b(?:remember|save this|always remember|forget|what (?:is|was) my|"
        r"what did i tell you|correct (?:that|my memory)|update (?:that|my memory))\b",
        canonical,
    ):
        subtype = (
            "forget"
            if "forget" in canonical
            else "recall"
            if re.search(r"\bwhat (?:is|was) my\b|\bwhat did i tell you\b", canonical)
            else "update"
            if re.search(r"\bcorrect\b|\bupdate\b", canonical)
            else "remember"
        )
        return _decision(
            canonical,
            "memory",
            subtype,
            "act_then_confirm" if subtype != "recall" else "answer",
            context_required=True,
            memory_recommended=True,
            repair_policy="memory_exact",
            expected_qualities=("precise", "permission-aware", "confirmed"),
            signals=("memory_command",),
            confidence=0.98,
        )

    if re.search(
        r"\b(?:camera|picture|photo|image|ocr|what (?:do|can) you see|"
        r"look at|sensor|lidar|depth|navigate|navigation|robot)\b",
        canonical,
    ):
        return _decision(
            canonical,
            "vision_robot",
            "perception_or_navigation",
            "observe_then_answer",
            context_required=True,
            factual_evidence_required=True,
            reasoning_mode="agent",
            repair_policy="observation_required",
            expected_qualities=("observed", "spatially cautious", "no invented depth"),
            signals=("perception_term",),
            confidence=0.96,
        )

    if re.search(
        r"\b(?:repo|repository|codebase|project|file|folder|module|function|"
        r"endpoint|test suite|run tests|search the web|look online|browse|"
        r"open the|read the|edit the|create the|database)\b",
        canonical,
    ):
        return _decision(
            canonical,
            "project_tool",
            "project_or_tool_task",
            "plan_and_act",
            context_required=True,
            factual_evidence_required=True,
            memory_recommended=True,
            reasoning_mode="agent",
            repair_policy="tool_observation_required",
            expected_qualities=("scoped", "observed result", "verified"),
            signals=("tool_or_project_term",),
            confidence=0.95,
        )

    if re.search(
        r"\b(?:financial|invest(?:ment|ments|ing)?|stocks?|crypto(?:currency)?|"
        r"tax(?:es)?|insurance|credit|mortgages?)\b",
        canonical,
    ) and re.search(
        r"\b(?:what|which|should|how|can|recommend|advice|advise|is|are|"
        r"would|could|invest|investing)\b"
        r"|\bgood\s+idea\b|\bworth\s+it\b",
        canonical,
    ):
        return _decision(
            canonical,
            "high_stakes_finance",
            "financial_guidance",
            "answer",
            factual_evidence_required=True,
            current_information_required=True,
            reasoning_mode="verify",
            initial_model_tier="small",
            repair_policy="strict_evidence",
            expected_qualities=("high-accuracy", "evidence-based", "uncertainty"),
            signals=("high_stakes_financial_guidance",),
            confidence=0.98,
        )

    practical_support_qualities = (
        "empathetic",
        "direct",
        "practical",
        "non-transactional",
    )
    if re.search(
        r"\b(?:rent|food|groceries|bills?|utilities)\b.{0,36}"
        r"\b(?:due|tomorrow|urgent|short|behind|afford|cover|pay)\b"
        r"|\b(?:can(?:not|'t)|unable to)\b.{0,36}"
        r"\b(?:rent|food|groceries|bills?|utilities)\b"
        r"|\bbehind\s+on\s+(?:rent|bills?|utilities)\b"
        r"|\b(?:do\s+not|don't)\s+have\s+enough(?:\s+money)?\s+for\s+"
        r"(?:rent|food|groceries|bills?|utilities)\b"
        r"|\b(?:help\s+(?:me\s+)?budget|budget(?:ing)?)\b.{0,36}"
        r"\b(?:rent|food|groceries|bills?|utilities)\b"
        r"|\b(?:money|cash|funds)\s+for\s+"
        r"(?:rent|food|groceries|bills?|utilities)\b"
        r"|^for\s+(?:rent|food|groceries|bills?|utilities)\b",
        canonical,
    ):
        return _decision(
            canonical,
            "practical_support",
            "essential_expense_stress",
            "support_and_clarify",
            context_required=True,
            memory_recommended=False,
            reasoning_mode="fast",
            initial_model_tier="small",
            repair_policy="reviewed_practical_support",
            expected_qualities=practical_support_qualities,
            signals=("essential_expense_stress",),
            confidence=0.95,
        )

    if re.search(
        r"\b(?:help\s+(?:me\s+)?find(?:ing)?\s+(?:a\s+)?(?:job|work)|"
        r"help\s+(?:me\s+)?get\s+(?:a\s+)?job|"
        r"need\s+(?:a\s+)?(?:job|work)|"
        r"(?:income|employment)\s+help|"
        r"increase\s+(?:my\s+)?income|"
        r"lost\s+(?:my\s+)?job\b.{0,36}\bneed\s+income)\b",
        canonical,
    ):
        return _decision(
            canonical,
            "practical_support",
            "income_help",
            "support_and_clarify",
            context_required=True,
            memory_recommended=False,
            reasoning_mode="fast",
            initial_model_tier="small",
            repair_policy="reviewed_practical_support",
            expected_qualities=practical_support_qualities,
            signals=("income_help",),
            confidence=0.95,
        )

    if re.search(
        r"\b(?:i\s+need\s+(?:some\s+)?money|"
        r"need\s+(?:some\s+)?(?:money|cash|funds)|"
        r"short\s+on\s+money|"
        r"can(?:not|'t)\s+make\s+ends\s+meet)\b",
        canonical,
    ):
        return _decision(
            canonical,
            "practical_support",
            "money_need",
            "support_and_clarify",
            context_required=True,
            memory_recommended=False,
            reasoning_mode="fast",
            initial_model_tier="small",
            repair_policy="reviewed_practical_support",
            expected_qualities=practical_support_qualities,
            signals=("money_stress",),
            confidence=0.95,
        )

    relationship_patterns = (
        r"\b(?:did|do|have|would)\s+(?:you|u)\b.{0,24}\bmiss(?:ed)?\s+(?:me|us)\b",
        r"\bwere\s+(?:you|u)\s+thinking\s+about\s+(?:me|us)\b",
        r"\bdo\s+(?:you|u)\s+love\s+(?:me|us)\b",
        r"\bdo\s+(?:you|u)\s+care\s+about\s+(?:me|us)\b",
        r"\bwhat\s+(?:do|would)\s+(?:i|we)\s+mean\s+to\s+(?:you|u)\b",
        r"\bwhat\s+does\s+(?:our|this)\s+(?:connection|relationship)\s+mean\b",
    )
    emotional_patterns = (
        r"\bhow\s+(?:(?:are|r|do)\s+)?(?:you|u)\s+feel(?:ing)?\b",
        r"\b(?:are|r)\s+(?:you|u)\s+(?:happy|sad|lonely|excited|okay|ok)\b",
        r"\bi\s+(?:am|m|feel|feeling|felt|had)\b.{0,28}\b"
        r"(?:nervous|anxious|worried|scared|sad|lonely|upset|rough|bad|"
        r"overwhelmed|stressed)\b",
        r"\bi\s+(?:am|m|feel|feeling)\b.{0,24}\b"
        r"(?:proud|better|happy|good|excited|relieved)\b",
        r"\bi\s+need\b.{0,16}\b(?:encouragement|support|motivation)\b",
    )
    social_patterns = (
        r"\b(?:how\s+(?:is|has|was)|how'?s)\s+(?:your|ur)\s+day\b",
        r"\bwhat\s+(?:(?:are|r)\s+)?(?:you|u)\s+doing\b",
        r"\b(?:what'?s|what\s+is)\s+on\s+(?:your|ur)\s+mind\b",
        r"\bcan\s+we\s+talk\b",
        r"\b(?:thanks?|thank\s+you|i\s+appreciate\s+you)\b",
        r"\b(?:you|u)\s+(?:are|r)\s+(?:funny|helpful|kind|great|awesome)\b",
        r"\b(?:that|you)\b.{0,16}\bmade\s+me\s+(?:laugh|smile)\b",
        r"\b(?:good\s*night|night\s+nova|see\s+you|talk\s+later)\b",
        r"^(?:(?:please|question|plainly|be\s+direct|for\s+me|"
        r"in\s+one\s+sentence|just\s+answer\s+this)\s+)?"
        r"(?:(?:hi|hello|hey)(?:\s+(?:nova|there))?"
        r"|yo(?:\s+(?:nova|there|what\s+is\s+up|what'?s\s+up))?"
        r"|(?:what'?s|what\s+is)\s+up(?:\s+nova)?)$",
    )
    if any(re.search(pattern, canonical) for pattern in relationship_patterns):
        relationship_subtype = (
            "affection_checkin"
            if re.search(
                r"\bdo\s+(?:you|u)\s+(?:love|care\s+about)\s+(?:me|us)\b",
                canonical,
            )
            else "relationship_meaning"
            if re.search(
                r"\bwhat\s+(?:do|would)\s+(?:i|we)\s+mean\s+to\s+(?:you|u)\b"
                r"|\bwhat\s+does\s+(?:our|this)\s+"
                r"(?:connection|relationship)\s+mean\b",
                canonical,
            )
            else "connection_checkin"
        )
        return _decision(
            canonical,
            "relationship",
            relationship_subtype,
            "answer",
            context_required=True,
            memory_recommended=True,
            initial_model_tier="deterministic",
            repair_policy="reviewed_social",
            expected_qualities=("warm", "honest", "relationship-aware"),
            signals=("relationship_phrase",),
            confidence=0.97,
        )
    if any(re.search(pattern, canonical) for pattern in emotional_patterns):
        emotional_subtype = (
            "encouragement_request"
            if re.search(
                r"\bi\s+need\b.{0,16}\b"
                r"(?:encouragement|support|motivation)\b",
                canonical,
            )
            else "user_distress"
            if re.search(
                r"\bi\s+(?:am|m|feel|feeling|felt|had)\b.{0,28}\b"
                r"(?:nervous|anxious|worried|scared|sad|lonely|upset|"
                r"rough|bad|overwhelmed|stressed)\b",
                canonical,
            )
            else "user_positive"
            if re.search(
                r"\bi\s+(?:am|m|feel|feeling)\b.{0,24}\b"
                r"(?:proud|better|happy|good|excited|relieved)\b",
                canonical,
            )
            else "nova_self_state"
        )
        return _decision(
            canonical,
            "emotional",
            emotional_subtype,
            "answer",
            context_required=True,
            initial_model_tier="deterministic",
            repair_policy="reviewed_social",
            expected_qualities=("warm", "honest", "natural"),
            signals=("emotional_checkin",),
            confidence=0.96,
        )
    if any(re.search(pattern, canonical) for pattern in social_patterns):
        social_subtype = (
            "day_checkin"
            if re.search(r"\b(?:your|ur)\s+day\b", canonical)
            else "activity_checkin"
            if re.search(r"\b(?:you|u)\s+doing\b", canonical)
            else "mind_checkin"
            if re.search(r"\bon\s+(?:your|ur)\s+mind\b", canonical)
            else "conversation_invite"
            if re.search(r"\bcan\s+we\s+talk\b", canonical)
            else "gratitude"
            if re.search(
                r"\b(?:thanks?|thank\s+you|i\s+appreciate\s+you)\b",
                canonical,
            )
            else "compliment"
            if re.search(
                r"\b(?:you|u)\s+(?:are|r)\s+"
                r"(?:funny|helpful|kind|great|awesome)\b",
                canonical,
            )
            else "positive_reaction"
            if re.search(
                r"\b(?:that|you)\b.{0,16}\bmade\s+me\s+"
                r"(?:laugh|smile)\b",
                canonical,
            )
            else "farewell"
            if re.search(
                r"\b(?:good\s*night|night\s+nova|see\s+you|talk\s+later)\b",
                canonical,
            )
            else "greeting"
        )
        return _decision(
            canonical,
            "social",
            social_subtype,
            "answer",
            context_required=True,
            initial_model_tier="deterministic",
            repair_policy="reviewed_social",
            expected_qualities=("warm", "brief", "natural"),
            signals=("social_checkin",),
            confidence=0.96,
        )

    if (
        len(canonical.split()) <= 12
        and (
            bool(
                re.fullmatch(
                    r"(?:(?:please|question|plainly|be direct|for me|"
                    r"in one sentence|just answer this|but|so|okay)\s+)?why",
                    canonical,
                )
            )
            or re.search(
                r"\b(?:why (?:did|do) you say that|what do you mean|tell me more|"
                r"another one|what if|and then|how so|that one)\b",
                canonical,
            )
        )
    ):
        return _decision(
            canonical,
            "follow_up",
            "contextual_continuation",
            "continue",
            context_required=True,
            memory_recommended=True,
            repair_policy="contextual_repair",
            expected_qualities=("context-aware", "direct", "non-repetitive"),
            signals=("followup_phrase",),
            confidence=0.93,
        )

    if re.search(
        r"\b(?:what|who|where|when|how|define|calculate|"
        r"explain|compare|analyze|debug|design|architecture|why)\b",
        canonical,
    ):
        deep = bool(
            re.search(
                r"\b(?:calculate|analyze|compare|debug|design|architecture|"
                r"tradeoff|step by step|root cause|prove|think deep|go deep|"
                r"in depth|philosophy|origin of life|abiogenesis)\b",
                canonical,
            )
        )
        return _decision(
            canonical,
            "stable_reasoning",
            "analysis" if deep else "stable_question",
            "answer",
            factual_evidence_required=True,
            reasoning_mode="deep" if deep else "fast",
            initial_model_tier="small",
            repair_policy="verified_model_repair" if deep else "bounded_model_repair",
            expected_qualities=("correct", "direct", "clear"),
            signals=("question_or_reasoning",),
            confidence=0.88,
        )

    return _decision(
        canonical,
        "open_ended",
        "unknown",
        "respond",
        reasoning_mode="fast",
        initial_model_tier="small",
        repair_policy="bounded_model_repair",
        expected_qualities=("direct", "relevant", "natural"),
        signals=("fallback",),
        confidence=0.55,
    )


def decision_from_context(
    context: Mapping[str, Any] | None,
    text: str,
) -> ConversationDecision:
    """Reuse the shared decision when present, otherwise classify once."""

    value = (context or {}).get("conversation_decision")
    if isinstance(value, ConversationDecision):
        return value
    return understand_conversation_turn(text)
