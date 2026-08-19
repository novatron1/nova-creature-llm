"""Deterministic social-mode classification layered over Nova's route decision."""

from __future__ import annotations

import re
from typing import Any

from .models import SocialIntent


def _canonical(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _intent(mode: str, *, confidence: float, seriousness: float, signals: tuple[str, ...], secondary: tuple[str, ...] = ()) -> SocialIntent:
    return SocialIntent(
        primary_mode=mode,
        secondary_modes=secondary,
        confidence=max(0.0, min(1.0, confidence)),
        seriousness=max(0.0, min(1.0, seriousness)),
        signals=signals,
    )


def classify_social_intent(text: str, conversation_decision: Any = None) -> SocialIntent:
    value = _canonical(text)

    if re.search(r"\b(?:just\s+)?listen\b|\blet\s+me\s+vent\b|\bneed\s+to\s+vent\b|\bdon'?t\s+fix\s+it\b", value):
        return _intent("venting", confidence=0.98, seriousness=0.85, signals=("explicit_listening_request",), secondary=("emotional_support",))
    if re.search(
        r"\b(?:need|want)\s+(?:your\s+)?advice\b|\bwhat\s+should\s+i\s+do\b|\badvise\s+me\b|"
        r"\b(?:give|suggest)\s+me\s+(?:one\s+)?(?:practical\s+)?(?:next\s+)?(?:step|advice|tip)\b",
        value,
    ):
        return _intent("advice", confidence=0.96, seriousness=0.72, signals=("explicit_advice_request",), secondary=("companionship",))
    if re.search(
        r"\b(?:lol|lmao|jk|just\s+kidding|roast|make\s+me\s+a?\s* laugh|"
        r"tell\s+me\s+a\s+joke|give\s+me\s+(?:a\s+)?(?:gentle\s+)?joke)\b",
        value,
    ):
        return _intent("joking", confidence=0.95, seriousness=0.18, signals=("humor_marker",), secondary=("casual_chat",))
    if re.search(r"\b(?:brainstorm|ideas?\s+for|think\s+of\s+some)\b", value):
        return _intent("brainstorming", confidence=0.93, seriousness=0.52, signals=("brainstorm_marker",))
    if re.search(r"\b(?:debate|argue\s+the\s+other\s+side|challenge\s+me|push\s+back|disagree)\b", value):
        return _intent("debate", confidence=0.93, seriousness=0.68, signals=("debate_marker",))
    if re.search(r"\b(?:tell\s+me\s+a\s+story|storytime|make\s+up\s+a\s+tale)\b", value):
        return _intent("storytelling", confidence=0.95, seriousness=0.35, signals=("story_marker",))
    if re.search(r"\b(?:congratulations|congrats|good\s+news|i'?m\s+proud|celebrate|we\s+did\s+it)\b", value):
        return _intent("celebration", confidence=0.94, seriousness=0.25, signals=("celebration_marker",), secondary=("companionship",))
    if re.search(r"\b(?:frustrated|frustrating|annoyed|pissed|not\s+working|keeps?\s+failing|stuck)\b", value):
        return _intent("frustration", confidence=0.90, seriousness=0.78, signals=("frustration_marker",), secondary=("technical_help",))
    if re.search(r"\b(?:sad|lonely|anxious|overwhelmed|worried|scared|rough\s+day|hurt)\b", value):
        return _intent("emotional_support", confidence=0.92, seriousness=0.86, signals=("emotional_marker",), secondary=("companionship",))

    family = str(getattr(conversation_decision, "intent_family", "") or "")
    if family == "permission_action":
        return _intent("task_execution", confidence=0.92, seriousness=0.78, signals=("existing_task_route",))
    if family == "project_tool":
        # A project noun is not itself an instruction. Keep reflective
        # follow-ups conversational; only an explicit action should enter the
        # task route (which may require tools or verification).
        if re.search(r"\b(?:run|execute|open|create|edit|fix|build|test|deploy|send|delete|install)\b", value):
            return _intent("task_execution", confidence=0.92, seriousness=0.78, signals=("existing_task_route",))
        if re.search(r"\b(?:code|python|javascript|api|server|gpu|model|debug|error)\b", value):
            return _intent("technical_help", confidence=0.84, seriousness=0.76, signals=("existing_project_technical_context",))
        return _intent("casual_chat", confidence=0.76, seriousness=0.45, signals=("existing_project_context",), secondary=("companionship",))
    if family in {"current_fact", "high_stakes_finance", "stable_reasoning"}:
        return _intent("technical_help", confidence=0.88, seriousness=0.82, signals=("existing_reasoning_route",))
    if family == "relationship":
        return _intent("companionship", confidence=0.92, seriousness=0.58, signals=("existing_relationship_route",), secondary=("casual_chat",))
    if family == "emotional":
        return _intent("emotional_support", confidence=0.90, seriousness=0.78, signals=("existing_emotional_route",), secondary=("companionship",))
    if re.search(r"\b(?:run|execute|open|create|edit|fix|build|test|deploy)\b", value):
        return _intent("task_execution", confidence=0.86, seriousness=0.8, signals=("action_marker",))
    if re.search(r"\b(?:code|python|javascript|api|server|gpu|model|debug|error)\b", value):
        return _intent("technical_help", confidence=0.84, seriousness=0.76, signals=("technical_marker",))
    if re.search(r"\b(?:talk|stay\s+with\s+me|what'?s\s+on\s+your\s+mind|miss\s+you|care\s+about)\b", value):
        return _intent("companionship", confidence=0.84, seriousness=0.5, signals=("companionship_marker",))
    return _intent("casual_chat", confidence=0.62, seriousness=0.45, signals=("default_casual",))
