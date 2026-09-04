"""Conservative response-quality firewall for Nova-managed chat answers.

The firewall is intentionally deterministic and high precision.  It catches
known canned fallbacks, unrelated personal-memory replies, empty output, and
obvious provider error text.  It never runs in raw adapter mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, Mapping


GENERIC_FALLBACK_MARKERS = (
    "i'm here with you. i can talk, remember saved facts, use tools, code, and build inside the app",
    "i am here with you. i can talk, remember saved facts, use tools, code, and build inside the app",
    "i'm here with you. tell me what you want to do next",
    "i am here with you. tell me what you want to do next",
    "yeah, i'm here with you. tell me what's on your mind",
    "yeah, i am here with you. tell me what's on your mind",
    "okay, so you know that but",
    "say it like you mean it; be clear, warm, and specific",
    "i'm nova creature with 7 brain roles",
    "i understand your message, but i'm not sure how to respond",
    "i can help with creative tasks! i have a creative preview builder",
    "because your statement is confusing or off-topic",
    "let's have a more focused conversation if that would help clarify things",
    "i hear you. tell me more",
    "i get you. tell me more",
    "that's something we can explore",
    "that is something we can explore",
)
GENERIC_RECOVERY_MARKERS = (
    "i caught an off-topic draft before sending it",
    "the active nova route did not produce a reliable answer",
)
# Backward-compatible private name for older local extensions. New consumers
# should import the public constant or predicate above.
_GENERIC_FALLBACKS = GENERIC_FALLBACK_MARKERS
_PROVIDER_ERROR_MARKERS = (
    "couldn't connect to",
    "could not connect to",
    "the selected adapter could not run",
    "the trained adapter did not return a final answer",
    "llm_unavailable",
    "provider unavailable",
)
_INCOMPLETE_OUTPUT_MARKERS = (
    "nova's local model reached its response limit before finishing",
    "nova's local model connection ended before it could finish",
    "nova stopped the incomplete draft safely",
)


def contains_generic_fallback(value: str, *, include_recovery: bool = True) -> bool:
    """Return whether visible answer text contains Nova's canonical generic fallback.

    The predicate is intentionally independent of prompt routing so evaluation
    tools and the answer firewall share one drift-free marker source.
    """

    canonical = _canonical(value)
    markers = (
        GENERIC_FALLBACK_MARKERS + GENERIC_RECOVERY_MARKERS
        if include_recovery
        else GENERIC_FALLBACK_MARKERS
    )
    return bool(canonical and any(marker in canonical for marker in markers))


def _canonical(text: str) -> str:
    value = str(text or "").lower().replace("’", "'")
    return re.sub(r"\s+", " ", value).strip()


def _number_tokens(text: str) -> set[str]:
    return {
        value.replace(",", "")
        for value in re.findall(r"(?<![a-z])\d[\d,]*(?:\.\d+)?", str(text or "").lower())
    }


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _canonical(text))


def _asks_for_repetition(prompt: str) -> bool:
    q = _canonical(prompt)
    return any(marker in q for marker in ("repeat after me", "repeat exactly", "say exactly", "quote this"))


def _asks_about_capabilities(prompt: str) -> bool:
    q = _canonical(prompt)
    return any(marker in q for marker in ("what can you do", "capabilities", "abilities", "help with"))


def _asks_about_coding(prompt: str) -> bool:
    q = _canonical(prompt)
    return bool(re.search(r"\b(code|coding|program|python|javascript|software|app|website)\b", q))


def _asks_nova_identity(prompt: str) -> bool:
    q = _canonical(prompt).strip(" .!?")
    return any(
        q == marker
        or q.endswith(marker)
        or q.endswith(marker + " again")
        for marker in (
            "what is your name",
            "what's your name",
            "whats your name",
            "tell me your name",
            "what are you called",
            "who are you",
            "who r you",
        )
    )


def _asks_for_personal_memory(prompt: str) -> bool:
    q = _canonical(prompt)
    return any(
        marker in q
        for marker in (
            "my name",
            "what name did i",
            "what name is saved",
            "what name is stored",
            "what name do you have for me",
            "who am i",
            "where do i live",
            "where i live",
            "my girlfriend",
            "my boyfriend",
            "my wife",
            "my husband",
            "remember about me",
            "what do you remember",
        )
    )


def _is_followup_prompt(prompt: str) -> bool:
    q = _canonical(prompt).strip(" .!?")
    if q in {
        "another",
        "another one",
        "again",
        "one more",
        "more",
        "tell me more",
        "go on",
        "keep going",
        "why",
        "how",
        "but why",
        "how so",
        "then what",
        "what next",
        "are you sure",
    }:
        return True
    return bool(
        len(q.split()) <= 20
        and q.startswith(
            (
                "what if ",
                "but what if ",
                "why do you ",
                "why do u ",
                "what makes you ",
                "what makes u ",
                "does that mean ",
                "can you explain that",
                "can u explain that",
                "what about ",
                "and what about ",
            )
        )
    )


def _looks_unfinished(answer: str) -> bool:
    """Catch high-confidence cutoffs without rejecting ordinary short replies."""

    raw = str(answer or "").strip().lower().replace("’", "'")
    canonical = _canonical(raw).strip(" .!?")
    if not canonical:
        return False
    if any(marker in raw for marker in _INCOMPLETE_OUTPUT_MARKERS):
        return True
    dangling_phrases = (
        "and then",
        "but then",
        "because of",
        "if he doesn't",
        "if she doesn't",
        "if it doesn't",
        "if they don't",
        "if you don't",
        "that came",
        "that would",
        "what if",
    )
    if any(raw.rstrip(" .!?").endswith(phrase) for phrase in dangling_phrases):
        return True
    words = canonical.split()
    if len(words) > 18:
        return False
    return words[-1] in {
        "a",
        "an",
        "and",
        "although",
        "as",
        "because",
        "but",
        "for",
        "from",
        "if",
        "of",
        "or",
        "the",
        "that",
        "to",
        "unless",
        "when",
        "while",
        "which",
        "with",
    }


def _near_duplicate(first: str, second: str) -> bool:
    left = _canonical(first).strip(" .!?")
    right = _canonical(second).strip(" .!?")
    if not left or not right:
        return False
    if left == right:
        return True
    if min(len(left), len(right)) < 24:
        return False
    return SequenceMatcher(None, left, right).ratio() >= 0.92


@dataclass(frozen=True)
class FirewallDecision:
    """Result of checking one completed Nova-managed answer."""

    accepted: bool
    score: float
    reasons: tuple[str, ...]
    status: str

    def as_trace(self) -> dict[str, Any]:
        return {
            "checked": True,
            "status": self.status,
            "accepted": self.accepted,
            "score": round(self.score, 3),
            "reasons": list(self.reasons),
            "intercepted": not self.accepted,
        }


def bypass_trace() -> dict[str, Any]:
    """Trace marker proving raw adapter text was not checked or rewritten."""

    return {
        "checked": False,
        "status": "bypassed_raw",
        "accepted": True,
        "score": None,
        "reasons": [],
        "intercepted": False,
    }


def evaluate_answer(
    prompt: str,
    answer: str,
    *,
    previous_answer: str = "",
    trace: Mapping[str, Any] | None = None,
) -> FirewallDecision:
    """Reject only high-confidence response failures; uncertain text passes."""

    q = _canonical(prompt)
    a = _canonical(answer)
    reasons: list[str] = []
    score = 1.0

    if not a:
        reasons.append("empty_answer")
        score = 0.0

    prompt_without_punctuation = q.strip(" .!?")
    answer_without_punctuation = a.strip(" .!?")
    if (
        prompt_without_punctuation
        and len(prompt_without_punctuation.split()) >= 4
        and answer_without_punctuation == prompt_without_punctuation
    ):
        reasons.append("echoed_prompt")
        score = min(score, 0.1)

    prompt_words = _word_tokens(prompt)
    answer_words = _word_tokens(answer)
    source = str((trace or {}).get("source") or "").lower()
    if (
        len(prompt_words) >= 5
        and 4 <= len(answer_words) <= len(prompt_words) + 2
        and not _asks_for_repetition(prompt)
        and len(set(answer_words) - set(prompt_words)) <= 1
    ):
        reasons.append("prompt_paraphrase")
        score = min(score, 0.15)

    if a and any(marker in a for marker in _PROVIDER_ERROR_MARKERS):
        reasons.append("provider_error_exposed")
        score = min(score, 0.1)

    if contains_generic_fallback(a, include_recovery=False) and not _asks_about_capabilities(q):
        reasons.append("generic_fallback_mismatch")
        score = min(score, 0.2)

    if a and _looks_unfinished(answer):
        reasons.append("unfinished_response")
        score = min(score, 0.1)

    if a.startswith(("you live in ", "your name is ", "your girlfriend", "your boyfriend")):
        if not _asks_for_personal_memory(q):
            reasons.append("unrelated_personal_memory")
            score = min(score, 0.05)

    if a.startswith(("i can help with coding", "yes, i can help with coding")) and not _asks_about_coding(q):
        reasons.append("canned_domain_mismatch")
        score = min(score, 0.15)

    if (
        source == "provider_candidate"
        and _asks_nova_identity(q)
        and "nova" not in set(answer_words)
    ):
        reasons.append("nova_identity_mismatch")
        score = min(score, 0.0)

    prior = _canonical(previous_answer)
    if _is_followup_prompt(prompt) and prior and _near_duplicate(a, prior):
        reasons.append("repeated_previous_answer")
        score = min(score, 0.1)

    if bool((trace or {}).get("_fact_grounding_blocking")):
        reasons.append("freshness_unverified")
        score = min(score, 0.05)
    if source == "provider_candidate" and bool((trace or {}).get("numeric_verification_required")):
        candidate_numbers = _number_tokens(answer)
        supported_numbers = _number_tokens(str(prompt or "") + " " + str(previous_answer or ""))
        if candidate_numbers - supported_numbers:
            reasons.append("unverified_numeric_claim")
            score = min(score, 0.25)
    if source in {"long_term_memory", "legacy_memory", "memory"} and not _asks_for_personal_memory(q):
        if a.startswith(("you ", "your ")):
            reasons.append("memory_route_mismatch")
            score = min(score, 0.1)

    accepted = not reasons
    return FirewallDecision(
        accepted=accepted,
        score=score,
        reasons=tuple(dict.fromkeys(reasons)),
        status="passed" if accepted else "blocked",
    )


def recovery_response(
    prompt: str,
    decision: FirewallDecision,
    *,
    contextual_fallback: str = "",
) -> str:
    """Return an honest visible response after a bad managed answer is blocked."""

    if contextual_fallback:
        candidate = str(contextual_fallback).strip()
        if not contains_generic_fallback(candidate, include_recovery=True):
            return candidate
        return (
            "I could not produce a reliable answer for that turn yet. I kept the "
            "failed draft out of your conversation context; please ask me to try it again."
        )
    if "unrelated_personal_memory" in decision.reasons or "memory_route_mismatch" in decision.reasons:
        return (
            "I caught an unrelated memory result before sending it. It did not answer your question, "
            "so I kept it out of the reply. Ask me once more and I'll stay on the exact topic."
        )
    if "provider_error_exposed" in decision.reasons:
        return "Nova's active model did not return a usable answer. I stopped the error text instead of presenting it as an answer."
    if "nova_identity_mismatch" in decision.reasons:
        return "I'm Nova Creature."
    return (
        "I caught an off-topic draft before sending it. The active Nova route did not produce a reliable "
        "answer, so I stopped it instead of pretending it was correct."
    )
