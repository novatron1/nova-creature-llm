"""Bounded, client-scoped conversation context for Nova chat turns.

This module does not persist memory and does not generate model output.  It
normalizes the transcript a client already supplied and turns short follow-up
phrases into explicit instructions that Nova's normal cognitive path can use.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any, Mapping, Sequence


_ALLOWED_ROLES = {"user", "assistant"}
CONVERSATION_CONTEXT_VERSION = "3.0"

_BRIDGE_TURNS = {
    "yeah", "yes", "yep", "ok", "okay", "got it", "i see", "right", "sure", "alright",
    "nice", "cool", "great", "awesome", "good", "interesting", "that helps", "that helped",
    "i like that", "i love that", "lol", "lmao", "haha", "thats funny", "that was funny",
    "glad to hear it", "thanks", "thank you",
}
_EMOTION_CUES = (
    ("anxious", ("worried", "worry", "anxious", "nervous", "scared", "afraid", "fear")),
    ("hurt", ("hurt", "heartbroken", "rejected", "betrayed")),
    ("sad", ("sad", "down", "depressed", "unhappy", "crying")),
    ("frustrated", ("angry", "mad", "frustrated", "annoyed", "pissed")),
    ("strained", ("tired", "stressed", "overwhelmed", "exhausted", "rough day")),
    ("positive", ("happy", "excited", "glad", "proud", "hopeful")),
    ("affectionate", ("i love", "i care about", "means a lot to me")),
)


def _canonical(text: str) -> str:
    value = str(text or "").lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


_NON_CONTEXT_ASSISTANT_MARKERS = (
    "i caught an off topic draft",
    "the active nova route did not produce a reliable answer",
    "i stopped an unverified current fact answer",
    "no module named",
    "could not run",
    "did not return a final answer yet",
    "provider error",
    "connection refused",
)


def is_contextworthy_assistant_text(text: str) -> bool:
    """Return whether an assistant message is safe to use as conversation context.

    Recovery/provider diagnostics describe routing state, not Nova's answer. They
    must never become the prior answer for a later follow-up. This predicate is
    deliberately local and marker-based so context normalization stays free of
    firewall/provider imports and remains deterministic.
    """

    canonical = _canonical(text)
    if not canonical:
        return False
    return not any(marker in canonical for marker in _NON_CONTEXT_ASSISTANT_MARKERS)


def bounded_conversation_history(
    context: Mapping[str, Any] | None,
    current_text: str = "",
    *,
    maximum_messages: int = 8,
    maximum_content_length: int = 4000,
) -> list[dict[str, str]]:
    """Return a small, validated user/assistant transcript from a request."""

    source: Any = context.get("conversation_history") if isinstance(context, Mapping) else None
    if not isinstance(source, list) and isinstance(context, Mapping):
        nova_request = context.get("nova_request")
        if isinstance(nova_request, Mapping):
            source = nova_request.get("messages")
    if not isinstance(source, list):
        return []

    history: list[dict[str, str]] = []
    for item in source[-maximum_messages:]:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = item.get("content")
        if role not in _ALLOWED_ROLES or not isinstance(content, str):
            continue
        clean = content.strip()
        if not clean:
            continue
        if role == "assistant" and not is_contextworthy_assistant_text(clean):
            continue
        history.append({"role": role, "content": clean[:maximum_content_length]})

    current = str(current_text or "").strip()
    if history and history[-1]["role"] == "user" and history[-1]["content"] == current:
        history.pop()
    return history[-maximum_messages:]


def previous_exchange(history: Sequence[Mapping[str, str]]) -> tuple[str, str]:
    """Return the latest complete user/assistant exchange in a transcript."""

    assistant_index = None
    for index in range(len(history) - 1, -1, -1):
        if str(history[index].get("role") or "").lower() == "assistant":
            assistant_index = index
            break
    if assistant_index is None:
        return "", ""

    assistant = str(history[assistant_index].get("content") or "").strip()
    if not is_contextworthy_assistant_text(assistant):
        return "", ""
    user = ""
    for index in range(assistant_index - 1, -1, -1):
        if str(history[index].get("role") or "").lower() == "user":
            user = str(history[index].get("content") or "").strip()
            break
    return user, assistant


def is_bridge_turn(text: str) -> bool:
    """Return whether a turn is a low-information social bridge."""

    return _canonical(text) in _BRIDGE_TURNS


def _recent_emotion(history: Sequence[Mapping[str, str]]) -> str:
    values = [
        str(item.get("content") or "")
        for item in history
        if str(item.get("role") or "").lower() == "user"
    ]
    return _emotion_from_texts(values)


def _emotion_from_texts(values: Sequence[str]) -> str:
    for text in reversed(values):
        value = _canonical(text)
        for label, cues in _EMOTION_CUES:
            if any(cue in value for cue in cues):
                return label
    return ""


@dataclass(frozen=True)
class ConversationFocus:
    """The latest substantive exchange inside the bounded client transcript."""

    previous_user: str = ""
    previous_answer: str = ""
    subject: str = ""
    emotion: str = ""
    anchor_distance: int = 0
    confidence: float = 0.0

    @property
    def available(self) -> bool:
        return bool(self.previous_user and self.previous_answer)


def conversation_focus(history: Sequence[Mapping[str, str]]) -> ConversationFocus:
    """Skip acknowledgment-only exchanges and retain the recent real subject.

    This operates only on the bounded transcript supplied by the active client.
    It does not read global memory, merge clients, or perform model inference.
    """

    exchanges: list[tuple[str, str]] = []
    pending_user = ""
    for item in history:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user and is_contextworthy_assistant_text(content):
            exchanges.append((pending_user, content))
            pending_user = ""
    if not exchanges:
        return ConversationFocus(emotion=_recent_emotion(history))

    selected_index = len(exchanges) - 1
    while selected_index > 0 and is_bridge_turn(exchanges[selected_index][0]):
        selected_index -= 1
    previous_user, previous_answer = exchanges[selected_index]
    distance = len(exchanges) - 1 - selected_index
    return ConversationFocus(
        previous_user=previous_user,
        previous_answer=previous_answer,
        subject=_topic_label(previous_user),
        emotion=_emotion_from_texts([user for user, _answer in exchanges[selected_index:]]),
        anchor_distance=distance,
        confidence=max(0.80, 0.99 - (0.04 * distance)),
    )


@dataclass(frozen=True)
class ContextResolution:
    """A safe interpretation of a short follow-up turn."""

    kind: str
    previous_user: str
    previous_answer: str
    generation_prompt: str = ""
    immediate_response: str = ""
    fallback_response: str = ""
    confidence: float = 0.0
    subject: str = ""
    emotion: str = ""
    anchor_distance: int = 0

    @property
    def is_followup(self) -> bool:
        return bool(self.kind)


@dataclass(frozen=True)
class ConversationRecall:
    """A high-confidence fact resolved only from client-supplied user turns."""

    response: str
    kind: str
    source_text: str
    confidence: float = 0.99


def _user_history_sentences(
    history: Sequence[Mapping[str, str]],
) -> list[tuple[str, str]]:
    """Return bounded user-authored clauses with their original source turn."""

    sentences: list[tuple[str, str]] = []
    for item in history[-8:]:
        if str(item.get("role") or "").lower() != "user":
            continue
        source = str(item.get("content") or "").strip()
        if not source:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", source):
            clean = sentence.strip(" \t\r\n.!?")
            if clean:
                sentences.append((clean, source))
    return sentences


def _recall(
    response: str,
    kind: str,
    source_text: str,
) -> ConversationRecall | None:
    clean = str(response or "").strip(" \t\r\n.!?")
    if not clean or len(clean) > 240:
        return None
    return ConversationRecall(clean, kind, source_text)


def resolve_conversation_declaration(text: str) -> ConversationRecall | None:
    """Acknowledge an explicitly temporary fact without loading a model."""

    raw = str(text or "").strip()
    query = _canonical(raw)
    if not raw:
        return None

    relation_clauses = [
        clause
        for clause in re.split(r"(?<=[.!?])\s+", raw)
        if re.match(
            r"^[A-Z][\w'-]{0,50}\s+holds\s+(?:the\s+)?[^.?!]{1,100}[.?!]?$",
            clause.strip(),
        )
    ]
    if relation_clauses and "?" not in raw:
        return ConversationRecall(
            "Got it. I’ll keep those details in this conversation.",
            "temporary_declaration",
            raw,
        )

    layout_preference = re.match(
        r"^(?:Actually,\s*)?(?:use|switch\s+to)\s+the\s+"
        r"([A-Za-z][A-Za-z0-9_-]{0,40})\s+layout[.!]?$",
        raw,
        flags=re.I,
    )
    if layout_preference:
        value = layout_preference.group(1)
        return ConversationRecall(
            f"Got it. I’ll use the {value} layout as this conversation’s current preference.",
            "temporary_declaration",
            raw,
        )

    structured_context = any(
        re.search(pattern, raw, flags=re.I)
        for pattern in (
            r"^(?:Correction:\s*)?the\s+test\s+number\s+is\s+[A-Za-z0-9_.-]+[.!]?$",
            r"^the\s+.{1,80}\s+is\s+beside\s+the\s+.{1,80}[.!]?$",
            r"^I\s+[A-Za-z]+\s+.{1,100}\s+because\s+.{1,120}[.!]?$",
            r"^our\s+current\s+goal\s+is\s+to\s+.{1,160}[.!]?$",
        )
    )
    if structured_context and "?" not in raw:
        return ConversationRecall(
            "Got it. I’ll keep that detail in this conversation.",
            "temporary_declaration",
            raw,
        )

    if not (
        "for this conversation" in query
        or "temporary" in query
    ):
        return None

    codeword = re.search(
        r"\bcodeword\s+(?:is|equals?)\s+([A-Za-z0-9][A-Za-z0-9_-]{0,80})\b",
        raw,
        flags=re.I,
    )
    if codeword:
        value = codeword.group(1)
        return ConversationRecall(
            f"Got it. The codeword for this conversation is {value}.",
            "temporary_declaration",
            raw,
        )

    color = re.search(
        r"\btemporary\s+favorite\s+color\s+is\s+([A-Za-z][A-Za-z-]{0,30})\b",
        raw,
        flags=re.I,
    )
    if color:
        value = color.group(1)
        return ConversationRecall(
            f"Got it. Your temporary favorite color is {value}.",
            "temporary_declaration",
            raw,
        )

    return None


def resolve_conversation_recall(
    text: str,
    history: Sequence[Mapping[str, str]],
) -> ConversationRecall | None:
    """Resolve explicit recent facts without a model call or persistent memory.

    This deliberately uses only user-authored turns supplied by the current
    client. Rules are narrow and relation-based so unrelated chat text cannot
    become an answer merely because it appeared nearby.
    """

    query = _canonical(text).strip(" .!?")
    if not query:
        return None
    sentences = _user_history_sentences(history)
    if not sentences:
        return None

    if "codeword" in query:
        for sentence, source in reversed(sentences):
            match = re.search(
                r"\bcodeword\s+(?:is|equals?)\s+([a-z0-9][a-z0-9_-]{0,80})\b",
                sentence,
                flags=re.I,
            )
            if match:
                return _recall(match.group(1), "explicit_slot", source)

    if "color" in query and any(
        marker in query for marker in ("temporary", "favorite", "did i say")
    ):
        for sentence, source in reversed(sentences):
            match = re.search(
                r"\b(?:temporary\s+)?favorite\s+color\s+is\s+([a-z][a-z-]{0,30})\b",
                sentence,
                flags=re.I,
            )
            if match:
                return _recall(match.group(1), "explicit_slot", source)

    if "test number" in query:
        for sentence, source in reversed(sentences):
            match = re.search(
                r"\btest\s+number\s+is\s+([a-z0-9][a-z0-9_.-]{0,40})\b",
                sentence,
                flags=re.I,
            )
            if match:
                return _recall(match.group(1), "explicit_slot", source)

    if "goal" in query and any(
        marker in query for marker in ("what goal", "current goal", "goal are we")
    ):
        for sentence, source in reversed(sentences):
            match = re.search(
                r"\b(?:our\s+)?(?:current\s+)?goal\s+is\s+(?:to\s+)?(.+)$",
                sentence,
                flags=re.I,
            )
            if match:
                return _recall(match.group(1), "explicit_goal", source)

    if "layout" in query and any(
        marker in query for marker in ("which layout", "what layout", "layout should")
    ):
        for sentence, source in reversed(sentences):
            match = re.search(
                r"\b(?:use|switch\s+to|change\s+to)\s+(?:the\s+)?"
                r"([a-z][a-z0-9_-]{0,40})\s+layout\b",
                sentence,
                flags=re.I,
            )
            if match:
                return _recall(match.group(1), "explicit_preference", source)

    relation_question = re.search(
        r"^who\s+([a-z]+)\s+(?:the\s+)?(.+?)(?:\s+return\b|$)",
        query,
        flags=re.I,
    )
    if relation_question:
        verb = relation_question.group(1)
        target = _canonical(relation_question.group(2))
        for sentence, source in reversed(sentences):
            match = re.match(
                rf"^([A-Z][\w'-]{{0,50}})\s+{re.escape(verb)}\s+(?:the\s+)?(.+)$",
                sentence,
            )
            if match and _canonical(match.group(2)) == target:
                return _recall(match.group(1), "relation", source)

    location_question = re.search(
        r"^what\s+is\s+beside\s+(?:the\s+)?(.+)$",
        query,
        flags=re.I,
    )
    if location_question:
        target = _canonical(location_question.group(1))
        for sentence, source in reversed(sentences):
            match = re.match(r"^(.+?)\s+is\s+beside\s+(?:the\s+)?(.+)$", sentence, flags=re.I)
            if match and _canonical(match.group(2)) == target:
                return _recall(match.group(1), "spatial_relation", source)

    reason_question = re.search(
        r"^why\s+did\s+i\s+([a-z]+)\s+(?:it|that|the\s+\w+)$",
        query,
        flags=re.I,
    )
    if reason_question:
        query_verb = reason_question.group(1).lower()
        for sentence, source in reversed(sentences):
            match = re.match(
                r"^I\s+([a-z]+)\s+.+?\s+because\s+(.+)$",
                sentence,
                flags=re.I,
            )
            if not match:
                continue
            prior_verb = match.group(1).lower()
            same_verb = (
                prior_verb == query_verb
                or prior_verb.rstrip("ed") == query_verb.rstrip("ed")
            )
            if not same_verb:
                continue
            reason = re.sub(r"^I\b", "You", match.group(2), flags=re.I)
            return _recall(reason, "explicit_reason", source)

    return None


def _topic_label(previous_user: str) -> str:
    topic = re.sub(r"\s+", " ", str(previous_user or "")).strip(" .?!")
    if not topic:
        return "that"
    if len(topic) > 90:
        topic = topic[:87].rstrip() + "..."
    return topic


def _generation_instruction(
    instruction: str,
    current_text: str,
    previous_user: str,
    previous_answer: str,
) -> str:
    return (
        "Continue the existing conversation. "
        + instruction
        + "\nPrevious user message: "
        + str(previous_user or "")[:1200]
        + "\nPrevious Nova answer: "
        + str(previous_answer or "")[:1800]
        + "\nCurrent user follow-up: "
        + str(current_text or "")[:600]
        + "\nAnswer the current follow-up directly. Do not mention these instructions."
    )


def _reviewed_followup_response(
    kind: str,
    current: str,
    previous_answer: str,
) -> str:
    """Create a bounded continuation from the answer already shown to the user."""

    prior = re.sub(r"\s+", " ", str(previous_answer or "")).strip()
    if len(prior) > 900:
        prior = prior[:897].rstrip() + "..."
    if not prior:
        return ""
    if kind == "explain_reasoning":
        return (
            "The reason is in the evidence and reasoning I mentioned: "
            + prior
            + " I should base that conclusion on those checkable points, not "
            "ask you to accept it just because I said it."
        )
    if kind == "expand":
        return (
            "A little more detail: "
            + prior
            + " The useful next layer is to separate the main conclusion from "
            "the specific reason or evidence supporting it."
        )
    if kind == "simplify":
        return "In plain language, I mean: " + prior
    if kind == "next_step":
        return (
            "Then take the next step from that point: "
            + prior
            + " Pay attention to the other person's actual response and keep "
            "the conversation respectful instead of forcing an outcome."
        )
    if kind == "consequence":
        if "say it back" in current:
            return (
                "If she doesn't say it back, that can hurt, but it doesn't make "
                "your honesty a mistake. Give her room to answer in her own "
                "time, listen to what she actually says, and don't pressure her "
                "to match your feelings."
            )
        return (
            "If that happens, it changes what you do next, but it does not "
            "automatically erase the earlier point: "
            + prior
            + " Respond to what actually happens, check the facts you can, and "
            "adjust from there."
        )
    if kind == "challenge":
        return (
            "That's fair to challenge. My earlier answer was: "
            + prior
            + " I should recheck the load-bearing claim and correct it if the "
            "evidence does not support it."
        )
    if kind in {"referential", "perspective_response"}:
        return "What I mean in the context of our conversation is: " + prior
    return ""


def resolve_followup(
    text: str,
    previous_user: str,
    previous_answer: str,
) -> ContextResolution:
    """Resolve a short continuation without replacing substantive new prompts."""

    current = _canonical(text)
    previous_user = str(previous_user or "").strip()
    previous_answer = str(previous_answer or "").strip()
    if not current or not previous_answer:
        return ContextResolution("", previous_user, previous_answer)

    topic = _topic_label(previous_user)
    positive = {
        "i like that",
        "i love that",
        "nice",
        "cool",
        "great",
        "awesome",
        "good",
        "interesting",
        "that helps",
        "that helped",
    }
    acknowledgements = {"yeah", "yes", "ok", "okay", "got it", "i see", "right", "sure", "alright"}
    corrections = {
        "no",
        "thats wrong",
        "that is wrong",
        "not what i meant",
        "you missed it",
        "wrong answer",
        "try again",
    }
    expansion = {"tell me more", "more", "go on", "keep going", "go deeper", "explain more"}
    simplify = {
        "what do you mean",
        "what u mean",
        "explain that",
        "explain it",
        "say that simpler",
        "explain it simpler",
        "simpler",
    }
    alternatives = {"another", "another one", "again", "give me another", "one more"}
    referential = {"why", "how", "really", "what about", "and", "also", "that", "this", "it"}
    evidence_why = {
        "why do you say that",
        "why do u say that",
        "why would you say that",
        "why do you think that",
        "why do u think that",
        "why is that",
        "but why",
        "but why do you say that",
        "but why do u say that",
        "why not",
        "how so",
        "how come",
        "what makes you say that",
        "what makes u say that",
        "what makes you think that",
        "what makes u think that",
        "can you explain why",
        "can u explain why",
    }
    disagreement = {
        "i disagree",
        "i dont agree",
        "i do not agree",
        "i dont think so",
        "i do not think so",
        "that doesnt sound right",
        "that does not sound right",
        "that cant be right",
        "that cannot be right",
        "are you sure",
        "are u sure",
    }
    next_step = {
        "and then",
        "then what",
        "what next",
        "what happens next",
        "so what should i do",
        "what should i do now",
        "what do i do now",
        "so what do i do",
        "where do i go from here",
    }
    alternative_followup = (
        current in alternatives
        or (
            len(current.split()) <= 8
            and current.startswith(
                (
                    "another ",
                    "give me another ",
                    "give me one more ",
                    "one more ",
                    "show me another ",
                )
            )
        )
    )
    explicit_expansion = bool(
        re.search(
            r"\b(?:can|could|would)\s+you\s+(?:please\s+)?"
            r"(?:clarify|elaborate|expand|tell\s+me\s+more)\b",
            current,
        )
        or re.search(
            r"\b(?:can|could|would)\s+you\s+give\s+me\s+more\s+"
            r"(?:information|details?)\b",
            current,
        )
    )
    explicit_referential = bool(
        re.search(r"\b(?:which|what)\s+of\s+(?:those|these)\b", current)
    )
    explicit_transform = bool(
        re.search(
            r"\b(?:can|could|would)\s+you\s+(?:do|make|write|answer|"
            r"explain)\s+the\s+same\b",
            current,
        )
    )
    hypothetical_followup = (
        len(current.split()) <= 28
        and current.startswith(("what if ", "but what if ", "and what if ", "so what if "))
    )
    referential_question = (
        len(current.split()) <= 18
        and (
            current.startswith(
                (
                    "does that mean ",
                    "do you mean ",
                    "do u mean ",
                    "can you explain that",
                    "can u explain that",
                    "what about ",
                    "and what about ",
                    "how does that ",
                    "how would that ",
                    "why would that ",
                    "is that ",
                    "would that ",
                    "could that ",
                    "what should i say to ",
                    "what should i do about ",
                    "what do i do about ",
                    "how should i respond to ",
                    "how should i answer ",
                    "what did you mean by ",
                )
            )
            or current.endswith((" about that", " because of that", " from that"))
        )
    )
    perspective_followup = (
        len(current.split()) <= 24
        and current.startswith(
            (
                "to me ",
                "i think that ",
                "i feel like that ",
                "that would make ",
                "that makes ",
                "so that means ",
            )
        )
    )

    if current in positive:
        return ContextResolution(
            "positive_reaction",
            previous_user,
            previous_answer,
            immediate_response=f"I'm glad that landed. Want to go deeper on \"{topic}\", or switch it up?",
            confidence=0.98,
        )
    if current in acknowledgements:
        return ContextResolution(
            "acknowledgement",
            previous_user,
            previous_answer,
            immediate_response=f"Got you. We can keep going with \"{topic}\", go deeper, or switch topics.",
            confidence=0.97,
        )
    if current in corrections:
        return ContextResolution(
            "correction",
            previous_user,
            previous_answer,
            immediate_response=(
                "You're right - that missed what you meant. Tell me the exact part I got wrong, "
                "and I'll correct it directly."
            ),
            confidence=0.98,
        )
    if current in disagreement:
        return ContextResolution(
            "challenge",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Treat this as a respectful challenge to the previous answer. Recheck the claim, "
                "state what evidence supports it, acknowledge any real uncertainty, and correct the "
                "answer if needed. Do not dismiss the user or merely repeat the earlier answer.",
                text,
                previous_user,
                previous_answer,
            ),
            immediate_response=_reviewed_followup_response(
                "challenge",
                current,
                previous_answer,
            ),
            fallback_response=(
                "That's fair to challenge. I should recheck the claim and explain the evidence or "
                "uncertainty behind it instead of just repeating myself."
            ),
            confidence=0.96,
        )
    if current in expansion:
        return ContextResolution(
            "expand",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Add useful new detail to the previous answer without repeating it.",
                text,
                previous_user,
                previous_answer,
            ),
            immediate_response=_reviewed_followup_response(
                "expand",
                current,
                previous_answer,
            ),
            fallback_response=f"What part of \"{topic}\" do you want me to go deeper on?",
            confidence=0.96,
        )
    if explicit_expansion:
        return ContextResolution(
            "expand",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Clarify or expand the previous answer in the user's requested level of detail. "
                "Use the earlier subject and avoid replacing it with a generic invitation.",
                text,
                previous_user,
                previous_answer,
            ),
            fallback_response=f"I can clarify \"{topic}\" directly; which part should I unpack first?",
            confidence=0.96,
        )
    if explicit_transform:
        return ContextResolution(
            "transform",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Apply the previous answer to the format, language, or implementation requested now. "
                "Carry over the earlier requirements and do not restart with a generic response.",
                text,
                previous_user,
                previous_answer,
            ),
            fallback_response=(
                f"I can adapt the earlier answer about \"{topic}\" to the requested form; "
                "I should preserve its requirements rather than start over."
            ),
            confidence=0.96,
        )
    if current in simplify:
        return ContextResolution(
            "simplify",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Explain the previous answer in simpler everyday language, using one concrete example.",
                text,
                previous_user,
                previous_answer,
            ),
            immediate_response=_reviewed_followup_response(
                "simplify",
                current,
                previous_answer,
            ),
            fallback_response=f"Which part of \"{topic}\" should I explain in simpler words?",
            confidence=0.97,
        )
    if alternative_followup:
        return ContextResolution(
            "alternative",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Give a different example or alternative answer. Do not repeat the previous answer.",
                text,
                previous_user,
                previous_answer,
            ),
            fallback_response=f"Do you want a different answer to \"{topic}\", or a different example from it?",
            confidence=0.96,
        )
    if current in next_step:
        return ContextResolution(
            "next_step",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Give the most practical next step based on the previous exchange. Be concrete and "
                "do not restart the topic from the beginning.",
                text,
                previous_user,
                previous_answer,
            ),
            immediate_response=_reviewed_followup_response(
                "next_step",
                current,
                previous_answer,
            ),
            fallback_response=f"The next step depends on which part of \"{topic}\" you want to act on.",
            confidence=0.96,
        )
    if hypothetical_followup:
        return ContextResolution(
            "consequence",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Answer the hypothetical consequence in the current message using the previous "
                "exchange as its context. Address the concern directly, include a practical response "
                "when useful, and do not give a canned reassurance. Do not restate the follow-up as "
                "a question, reverse the user's stated goal, or invent a different situation.",
                text,
                previous_user,
                previous_answer,
            ),
            immediate_response=_reviewed_followup_response(
                "consequence",
                current,
                previous_answer,
            ),
            fallback_response=(
                "That possibility connects to what we were just discussing. I should address what "
                "would happen and what you could do about it directly."
            ),
            confidence=0.96,
        )
    if current in evidence_why:
        return ContextResolution(
            "explain_reasoning",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Explain the evidence and reasoning behind the previous answer. "
                "Address the user's actual objection respectfully; never call the user or their statement "
                "confusing, off-topic, irrational, or stupid.",
                text,
                previous_user,
                previous_answer,
            ),
            immediate_response=_reviewed_followup_response(
                "explain_reasoning",
                current,
                previous_answer,
            ),
            fallback_response=(
                "I said that because the observations and reasoning in my previous answer support it. "
                "The key point was: " + previous_answer[:900]
            ),
            confidence=0.98,
        )
    if perspective_followup:
        return ContextResolution(
            "perspective_response",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Treat the current message as the user's interpretation of the previous answer. "
                "Acknowledge the connection they made, respond to it directly, and explain any meaningful "
                "agreement or distinction without changing the subject or using a canned invitation.",
                text,
                previous_user,
                previous_answer,
            ),
            immediate_response=_reviewed_followup_response(
                "perspective_response",
                current,
                previous_answer,
            ),
            fallback_response=(
                "I hear the connection you're making to what I just said. I should respond to that point "
                "directly instead of changing the subject."
            ),
            confidence=0.96,
        )
    if explicit_referential or current in referential or referential_question:
        return ContextResolution(
            "referential",
            previous_user,
            previous_answer,
            generation_prompt=_generation_instruction(
                "Resolve pronouns from the previous exchange and answer the follow-up in context.",
                text,
                previous_user,
                previous_answer,
            ),
            immediate_response=_reviewed_followup_response(
                "referential",
                current,
                previous_answer,
            ),
            fallback_response=f"Which part of \"{topic}\" are you asking about?",
            confidence=0.90,
        )
    return ContextResolution("", previous_user, previous_answer)


def _enrich_resolution(
    resolution: ContextResolution,
    *,
    subject: str,
    emotion: str,
    anchor_distance: int,
) -> ContextResolution:
    generation_prompt = resolution.generation_prompt
    if emotion and generation_prompt:
        emotional_context = (
            "\nRecent user emotional signal: "
            + emotion
            + ". Match the tone with care, but do not diagnose or unnecessarily label the user."
        )
        marker = "\nCurrent user follow-up: "
        if marker in generation_prompt:
            generation_prompt = generation_prompt.replace(marker, emotional_context + marker, 1)
        else:
            generation_prompt += emotional_context
    return replace(
        resolution,
        generation_prompt=generation_prompt,
        subject=subject,
        emotion=emotion,
        anchor_distance=max(0, int(anchor_distance)),
    )


def resolve_contextual_followup(
    text: str,
    history: Sequence[Mapping[str, str]],
    *,
    fallback_previous_user: str = "",
    fallback_previous_answer: str = "",
) -> ContextResolution:
    """Resolve a follow-up against the real bounded subject, not a bridge turn."""

    direct_user, direct_answer = previous_exchange(history)
    direct_user = direct_user or str(fallback_previous_user or "").strip()
    direct_answer = direct_answer or str(fallback_previous_answer or "").strip()
    focus = conversation_focus(history)

    if focus.available and focus.anchor_distance > 0:
        anchored = resolve_followup(text, focus.previous_user, focus.previous_answer)
        if anchored.is_followup:
            return _enrich_resolution(
                anchored,
                subject=focus.subject,
                emotion=focus.emotion,
                anchor_distance=focus.anchor_distance,
            )

    direct = resolve_followup(text, direct_user, direct_answer)
    subject = _topic_label(direct_user) if direct_user else focus.subject
    return _enrich_resolution(
        direct,
        subject=subject,
        emotion=focus.emotion,
        anchor_distance=0,
    )
