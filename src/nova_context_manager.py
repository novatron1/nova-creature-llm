"""Token-budgeted prompt context management for Nova."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Callable, Iterable


CONTEXT_MANAGER_VERSION = "1.0"
DEFAULT_ALLOCATIONS = {
    "identity_system": 0.10,
    "current_request": 0.10,
    "recent_conversation": 0.15,
    "memory": 0.15,
    "rag_evidence": 0.25,
    "tools_observations": 0.15,
    "response_reserve": 0.10,
}


def estimate_tokens(text: Any) -> int:
    """Conservative tokenizer-independent estimate."""

    value = str(text or "")
    if not value:
        return 0
    words = len(re.findall(r"\S+", value))
    utf8_estimate = (len(value.encode("utf-8")) + 3) // 4
    return max(words, utf8_estimate)


@dataclass
class ContextDiagnostics:
    context_window: int
    compaction_threshold: int
    estimated_before: int = 0
    estimated_after: int = 0
    compacted: bool = False
    current_request_truncated: bool = False
    removed_duplicate_system_lines: int = 0
    summarized_conversation_turns: int = 0
    removed_tool_outputs: int = 0
    section_tokens: dict[str, int] = field(default_factory=dict)
    allocations: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    version: str = CONTEXT_MANAGER_VERSION

    def safe_trace(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ManagedContext:
    system: str
    current_request: str
    conversation: list[dict[str, str]]
    conversation_summary: str
    memory: str
    rag_evidence: str
    tools_observations: str
    response_reserve: int
    diagnostics: ContextDiagnostics

    def prompt_sections(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system,
            "user_question": self.current_request,
            "conversation_context": self.conversation_summary
            or "\n".join(
                f"{item['role'].upper()}: {item['content']}"
                for item in self.conversation
            ),
            "memory_context": self.memory,
            "rag_context": self.rag_evidence,
            "tool_context": self.tools_observations,
        }


def _allocation_tokens(window: int) -> dict[str, int]:
    return {
        key: max(1, int(window * fraction))
        for key, fraction in DEFAULT_ALLOCATIONS.items()
    }


def _truncate(text: str, budget: int, counter: Callable[[Any], int]) -> str:
    value = str(text or "").strip()
    if counter(value) <= budget:
        return value
    maximum_chars = max(16, budget * 4)
    shortened = value[:maximum_chars].rsplit(" ", 1)[0].rstrip()
    return shortened + "\n[Context compacted at a recorded token boundary.]"


def _deduplicate_system(text: str) -> tuple[str, int]:
    seen: set[str] = set()
    output: list[str] = []
    removed = 0
    for line in str(text or "").splitlines():
        canonical = re.sub(r"\s+", " ", line.strip().lower())
        if canonical and canonical in seen:
            removed += 1
            continue
        if canonical:
            seen.add(canonical)
        output.append(line)
    return "\n".join(output).strip(), removed


def _normalize_messages(messages: Iterable[dict[str, Any]] | None) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for item in messages or ():
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
        if role in {"system", "developer", "user", "assistant", "tool"} and content:
            output.append({"role": role, "content": content})
    return output


def _factual_conversation_summary(messages: list[dict[str, str]]) -> str:
    facts: list[str] = []
    commitments: list[str] = []
    for item in messages:
        content = item["content"]
        role = item["role"]
        if role == "user" and re.search(
            r"\b(?:remember|my .+ is|i prefer|i need|do not|don't|must|should)\b",
            content,
            flags=re.I,
        ):
            facts.append("User: " + content[:240])
        if role == "assistant" and re.search(
            r"\b(?:i will|i'll|next|remaining|blocked|need to)\b",
            content,
            flags=re.I,
        ):
            commitments.append("Nova: " + content[:240])
    selected = (facts[-5:] + commitments[-4:])[:9]
    return (
        "FACTUAL SESSION SUMMARY:\n- " + "\n- ".join(selected)
        if selected
        else f"FACTUAL SESSION SUMMARY: {len(messages)} older message(s) were compacted; no stable fact or unresolved commitment was extracted."
    )


def manage_context(
    *,
    system: str,
    current_request: str,
    conversation: Iterable[dict[str, Any]] | None = None,
    memory: str = "",
    rag_evidence: str = "",
    tools_observations: str = "",
    context_window: int = 8192,
    counter: Callable[[Any], int] = estimate_tokens,
    compaction_ratio: float = 0.80,
) -> ManagedContext:
    """Allocate and compact context without silently dropping the request."""

    window = max(1024, int(context_window))
    threshold = max(512, int(window * min(max(compaction_ratio, 0.5), 0.95)))
    allocations = _allocation_tokens(window)
    diagnostics = ContextDiagnostics(
        context_window=window,
        compaction_threshold=threshold,
        allocations=allocations,
    )
    clean_system, removed = _deduplicate_system(system)
    diagnostics.removed_duplicate_system_lines = removed
    normalized_conversation = _normalize_messages(conversation)
    tool_text = str(tools_observations or "").strip()
    before_sections = (
        clean_system,
        current_request,
        "\n".join(item["content"] for item in normalized_conversation),
        memory,
        rag_evidence,
        tool_text,
    )
    diagnostics.estimated_before = sum(counter(item) for item in before_sections)

    conversation_summary = ""
    if diagnostics.estimated_before > threshold:
        diagnostics.compacted = True
        older = normalized_conversation[:-6]
        normalized_conversation = normalized_conversation[-6:]
        if older:
            conversation_summary = _factual_conversation_summary(older)
            diagnostics.summarized_conversation_turns = len(older)
        # Tool observations are ephemeral. Keep only the most recent bounded
        # lines; persistent results belong in project/procedural memory.
        tool_lines = [line for line in tool_text.splitlines() if line.strip()]
        if len(tool_lines) > 12:
            diagnostics.removed_tool_outputs = len(tool_lines) - 12
            tool_text = "\n".join(tool_lines[-12:])

    clean_system = _truncate(
        clean_system,
        allocations["identity_system"],
        counter,
    )
    memory_text = _truncate(str(memory or ""), allocations["memory"], counter)
    rag_text = _truncate(str(rag_evidence or ""), allocations["rag_evidence"], counter)
    tool_text = _truncate(tool_text, allocations["tools_observations"], counter)

    recent_budget = allocations["recent_conversation"]
    kept: list[dict[str, str]] = []
    used = counter(conversation_summary)
    for item in reversed(normalized_conversation):
        cost = counter(item["content"]) + 2
        if kept and used + cost > recent_budget:
            diagnostics.summarized_conversation_turns += 1
            continue
        kept.append(item)
        used += cost
    kept.reverse()

    request_text = str(current_request or "").strip()
    fixed_without_request = sum(
        counter(item)
        for item in (clean_system, conversation_summary, memory_text, rag_text, tool_text)
    )
    request_hard_limit = max(
        allocations["current_request"],
        window - allocations["response_reserve"] - fixed_without_request,
    )
    if counter(request_text) > request_hard_limit:
        diagnostics.current_request_truncated = True
        diagnostics.notes.append(
            "The current request exceeded the physical context limit; truncation was recorded."
        )
        request_text = _truncate(request_text, request_hard_limit, counter)

    diagnostics.section_tokens = {
        "identity_system": counter(clean_system),
        "current_request": counter(request_text),
        "recent_conversation": used,
        "memory": counter(memory_text),
        "rag_evidence": counter(rag_text),
        "tools_observations": counter(tool_text),
        "response_reserve": allocations["response_reserve"],
    }
    diagnostics.estimated_after = sum(diagnostics.section_tokens.values())
    return ManagedContext(
        system=clean_system,
        current_request=request_text,
        conversation=kept,
        conversation_summary=conversation_summary,
        memory=memory_text,
        rag_evidence=rag_text,
        tools_observations=tool_text,
        response_reserve=allocations["response_reserve"],
        diagnostics=diagnostics,
    )


def manage_context_packet(
    packet: dict[str, Any],
    *,
    context_window: int = 8192,
    debug: bool = False,
) -> ManagedContext:
    conversation_messages = packet.get("conversation_messages") or ()
    if not conversation_messages and str(packet.get("conversation_context") or "").strip():
        conversation_messages = [
            {
                "role": "assistant",
                "content": str(packet.get("conversation_context") or "").strip(),
            }
        ]
    managed = manage_context(
        system=str(packet.get("system_prompt") or ""),
        current_request=str(packet.get("user_question") or packet.get("user_message") or ""),
        conversation=conversation_messages,
        memory=str(packet.get("memory_v2_context") or packet.get("memory_context") or ""),
        rag_evidence=str(packet.get("rag_context") or packet.get("web_context") or ""),
        tools_observations=str(packet.get("tool_context") or packet.get("tool_result") or ""),
        context_window=context_window,
    )
    packet.update(managed.prompt_sections())
    packet["_context_compaction"] = {
        "compacted": managed.diagnostics.compacted,
        "estimated_before": managed.diagnostics.estimated_before,
        "estimated_after": managed.diagnostics.estimated_after,
        "current_request_truncated": managed.diagnostics.current_request_truncated,
        "version": CONTEXT_MANAGER_VERSION,
    }
    if debug:
        packet["_context_diagnostics"] = managed.diagnostics.safe_trace()
    return managed
