"""
Nova Quality Gate v1 — Transformer Output Quality Assurance
=============================================================
Separates these states clearly:

- transformer_ran: forward pass executed without crash
- transformer_output_raw: the generated raw text
- transformer_output_accepted: passed quality checks
- transformer_output_quality: "good" | specific rejection reason
- final_answer_source: where the final answer came from

Quality checks:
1. Min length
2. Unique word count  
3. <unk> ratio
4. Immediate word repetition (word[i] == word[i+1])
5. Common English word ratio (too low → garbage)
6. Word fragmentation check (starts with mid-word like "ing", "ust")
7. Fused text check (CamelCase, no-vowel long words)
8. Debug label check
"""

import re
import math

# ─── Configurable thresholds ──────────────────────────────────
MIN_OUTPUT_CHARS = 5
MIN_UNIQUE_WORDS = 2
MAX_UNK_RATIO = 0.3
MAX_COMMON_WORD_THRESHOLD = 0.05  # below this → fail
MAX_IMMEDIATE_REPEATS = 0  # zero tolerance for word[i]==word[i+1]
MAX_FRAGMENT_RATIO = 0.3  # words starting mid-word
MAX_FUSED_RATIO = 0.5
MAX_CAPS_RATIO = 0.8  # if 80%+ characters are uppercase → suspicious

# Common English function words
COMMON_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "has", "have", "had",
    "in", "on", "at", "to", "for", "of", "and", "or", "but", "not",
    "it", "its", "you", "your", "my", "i", "me", "we", "they", "he", "she",
    "this", "that", "these", "those", "can", "will", "would", "could",
    "should", "do", "does", "did", "been", "being", "more", "most",
    "some", "any", "all", "each", "every", "both", "no", "nor", "not",
    "with", "without", "from", "about", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "what", "which", "who", "whom", "whose", "yes", "no",
}

# Known word fragments that indicate garbage output
# Coherence checks (detect word salad like "wants asks awesome prefers")
PROPER_NOUN_PATTERN = re.compile(r'^[A-Z][a-z]+$')
CONSECUTIVE_CONTENT_WORDS_MAX = 5  # max content words without a stop word = garbage

WORD_FRAGMENTS = {
    "ing", "ust", "tant", "es", "ist", "ent", "ion", "ous", "ght",
    "ble", "tly", "ful", "ness", "ment", "tion", "sion", "able",
    "half", "asks", "bibbay", "tycoon",
}

# Debug labels that should never appear in output
DEBUG_LABELS = [
    "memory_search", "saved knowledge", "raw json",
    "transformer_ran", "logits", "hidden_state",
    "checkpoint_path", "route_path",
    "memory_event", "dictionary_hit", "dictionary_miss",
    "fast_path", "meaning_pipeline",
]

# Common verbs for coherence checking
COMMON_VERBS = {'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
               'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
               'can', 'shall', 'get', 'got', 'make', 'made', 'take', 'took', 'say', 'said',
               'go', 'went', 'come', 'came', 'know', 'knew', 'see', 'saw', 'think', 'thought',
               'want', 'wanted', 'use', 'used', 'find', 'found', 'tell', 'told', 'ask', 'asked',
               'try', 'tried', 'leave', 'left', 'call', 'called', 'give', 'gave', 'work', 'worked',
               'need', 'needed', 'mean', 'meant', 'help', 'helped', 'show', 'showed', 'try', 'tried'}

FRAGMENT_START_PATTERN = re.compile(r'^(ing|ust|tant|es|ist|ent|ght|ble|tly|ness|ment|tion|sion|able)$', re.IGNORECASE)


def strip_format_prefix(text: str) -> str:
    """Strip format prefixes like [MATH], [DEFINITION], etc."""
    return re.sub(r'^\[\w+\]\s*', '', text).strip()


def check_unks(text: str) -> tuple[bool, float]:
    if not text:
        return False, 1.0
    unk_count = text.count("<unk>")
    total = len(text.strip())
    if total == 0:
        return False, 1.0
    ratio = (unk_count * 5) / total
    return ratio <= MAX_UNK_RATIO, ratio


def check_immediate_repetition(text: str) -> tuple[bool, int]:
    """Check for immediate word repetition (word[i] == word[i+1])."""
    if not text:
        return False, 0
    words = text.lower().split()
    repeats = sum(1 for i in range(len(words)-1) if words[i] == words[i+1])
    return repeats <= MAX_IMMEDIATE_REPEATS, repeats


def check_common_words(text: str) -> tuple[bool, float]:
    """Check ratio of common English function words."""
    if not text:
        return False, 0.0
    clean = strip_format_prefix(text)
    words = clean.lower().split()
    if len(words) < 2:
        return True, 0.0  # too short to judge
    common_count = sum(1 for w in words if w.strip(".,!?;:\"'()[]{}") in COMMON_WORDS)
    ratio = common_count / len(words)
    return ratio >= MAX_COMMON_WORD_THRESHOLD, ratio


def check_fragments(text: str) -> tuple[bool, float]:
    """Check for word fragments that indicate garbage."""
    if not text:
        return False, 1.0
    words = text.lower().split()
    if len(words) < 2:
        return True, 0.0
    fragment_count = sum(1 for w in words if FRAGMENT_START_PATTERN.match(w.strip(".,!?;:\"'()[]{}")))
    ratio = fragment_count / len(words)
    return ratio <= MAX_FRAGMENT_RATIO, ratio


def check_fused_text(text: str) -> tuple[bool, float]:
    if not text:
        return False, 1.0
    words = text.split()
    if not words:
        return False, 1.0
    fused_count = 0
    for w in words:
        stripped = w.strip(".,!?;:\"'()[]{}")
        if len(stripped) > 8:
            vowels = sum(1 for c in stripped.lower() if c in "aeiou")
            if vowels == 0 or vowels < len(stripped) * 0.2:
                fused_count += 1
            if re.search(r'[a-z][A-Z]', stripped):
                fused_count += 1
    ratio = fused_count / len(words)
    return ratio <= MAX_FUSED_RATIO, ratio


def check_caps_ratio(text: str) -> tuple[bool, float]:
    """Check for excessive uppercase."""
    if not text or len(text) < 5:
        return True, 0.0
    clean = strip_format_prefix(text)
    if not clean or len(clean) < 3:
        return True, 0.0
    alpha = [c for c in clean if c.isalpha()]
    if not alpha:
        return True, 0.0
    caps = sum(1 for c in alpha if c.isupper())
    ratio = caps / len(alpha)
    return ratio <= MAX_CAPS_RATIO, ratio


def check_debug_labels(text: str) -> tuple[bool, list[str]]:
    if not text:
        return False, []
    found = [label for label in DEBUG_LABELS if label.lower() in text.lower()]
    return len(found) == 0, found


def check_word_coherence(text: str) -> tuple[bool, str]:
    """Check if words form coherent phrases rather than random word salad.
    Detects patterns like 'wants asks awesome prefers when assistant about'.
    """
    if not text:
        return False, "empty"
    clean = strip_format_prefix(text)
    words = [w.strip(".,!?;:\"'()[]{}").lower() for w in clean.split() if w.strip()]
    if len(words) < 4:
        return True, "too_short_to_judge"
    
    # Count consecutive content words without stop words
    max_consecutive_content = 0
    current_run = 0
    for w in words:
        if w in COMMON_WORDS or w in COMMON_VERBS:
            current_run = 0
        else:
            current_run += 1
            if current_run > max_consecutive_content:
                max_consecutive_content = current_run
    
    # If too many consecutive content words, it's likely word salad
    if max_consecutive_content > CONSECUTIVE_CONTENT_WORDS_MAX:
        return False, f"excessive_content_run({max_consecutive_content})"
    
    # Check verb density - random word salad lacks verbs
    verb_count = sum(1 for w in words if w in COMMON_VERBS)
    verb_ratio = verb_count / len(words)
    if verb_ratio < 0.02 and len(words) >= 4:
        return False, f"low_verb_density({verb_ratio:.3f})"
    
    return True, "ok"


def check_min_length(text: str) -> tuple[bool, int]:
    if not text:
        return False, 0
    return len(text.strip()) >= MIN_OUTPUT_CHARS, len(text.strip())


def check_unique_words(text: str) -> tuple[bool, int]:
    if not text:
        return False, 0
    words = text.lower().split()
    unique = set(w.strip(".,!?;:\"'()[]{}") for w in words if len(w.strip(".,!?;:\"'()[]{}")) > 0)
    return len(unique) >= MIN_UNIQUE_WORDS, len(unique)


def evaluate_quality(text: str) -> dict:
    """
    Evaluate transformer output quality.
    Returns dict with verdict, score, and details.
    """
    result = {
        "raw_text": text[:200],
        "checks": {},
        "verdict": "pass",
        "score": 1.0,
        "fail_reasons": [],
    }
    
    if not text or not text.strip():
        result["verdict"] = "fail"
        result["score"] = 0.0
        result["fail_reasons"].append("empty")
        return result
    
    check_functions = {
        "min_length": check_min_length,
        "unique_words": check_unique_words,
        "unks": check_unks,
        "immediate_repeats": check_immediate_repetition,
        "common_words": check_common_words,
        "fragments": check_fragments,
        "fused_text": check_fused_text,
        "caps_ratio": check_caps_ratio,
        "debug_labels": check_debug_labels,
        "word_coherence": check_word_coherence,
    }
    
    for name, func in check_functions.items():
        passed, detail = func(text)
        result["checks"][name] = {"pass": passed, "detail": str(detail)[:50]}
    
    # Score penalties
    score = 1.0
    fail_reasons = []
    penalties = {
        "word_coherence": (0.5, lambda d: f"incoherent({d})"),
        "min_length": (0.3, lambda d: f"too_short({d}chars)"),
        "unique_words": (0.2, lambda d: f"not_enough_words({d}unique)"),
        "unks": (0.3, lambda d: f"too_many_unks({d})"),
        "immediate_repeats": (0.4, lambda d: f"word_repetition({d}x)"),
        "common_words": (0.3, lambda d: f"low_common_words({d})"),
        "fragments": (0.3, lambda d: f"word_fragments({d})"),
        "fused_text": (0.3, lambda d: f"fused_text({d})"),
        "caps_ratio": (0.2, lambda d: f"excessive_caps({d})"),
        "debug_labels": (0.4, lambda d: f"debug_labels({d})"),
    }
    
    for name, check_data in result["checks"].items():
        if not check_data["pass"] and name in penalties:
            penalty, msg_fn = penalties[name]
            score -= penalty
            fail_reasons.append(msg_fn(check_data["detail"]))
    
    result["score"] = max(0.0, score)
    result["fail_reasons"] = fail_reasons
    
    if score >= 0.8 and not fail_reasons:
        result["verdict"] = "pass"
    elif score >= 0.4:
        result["verdict"] = "borderline"
    else:
        result["verdict"] = "fail"
    
    return result


def classify_quality(verdict: str, fail_reasons: list[str]) -> str:
    if verdict == "pass":
        return "good"
    if not fail_reasons:
        return "unknown"
    for reason in fail_reasons:
        if "incoherent" in reason:
            return "poor_incoherent"
        if "unks" in reason:
            return "poor_unks"
        if "repetition" in reason or "word_repetition" in reason:
            return "poor_repetition"
        if "fused" in reason:
            return "poor_fused"
        if "short" in reason:
            return "poor_short"
        if "fragments" in reason or "common_words" in reason or "words" in reason:
            return "poor_vague"
        if "debug" in reason:
            return "poor_debug"
        if "caps" in reason:
            return "poor_format"
    return "poor_unknown"


def get_answer_source(transformer_ran: bool, transformer_accepted: bool,
                      memory_used: bool, dict_used: bool,
                      local_llm_used: bool, fallback_used: bool) -> str:
    if transformer_accepted:
        return "accepted_transformer"
    if local_llm_used:
        return "local_llm_synthesis"
    if memory_used:
        return "deterministic_memory"
    if dict_used:
        return "deterministic_dictionary"
    if fallback_used:
        return "fallback_template"
    return "unknown"


def gate_transformer_output(text: str, domain: str = "",
                            memory_used: bool = False,
                            dict_used: bool = False) -> dict:
    quality = evaluate_quality(text)
    
    return {
        "transformer_ran": True,
        "transformer_output_raw": text[:500],
        "transformer_output_accepted": quality["verdict"] == "pass",
        "transformer_output_quality": classify_quality(quality["verdict"], quality["fail_reasons"]),
        "quality_score": quality["score"],
        "quality_checks": quality["checks"],
        "quality_fail_reasons": quality["fail_reasons"],
        "final_answer_source": "accepted_transformer" if quality["verdict"] == "pass" else "pending_review",
        "memory_used": memory_used,
        "dictionary_used": dict_used,
    }
