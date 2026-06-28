"""Language Cortex -- Nova's first processing stage.
Transforms raw user text into a structured MeaningPacket.
"""
from __future__ import annotations
import re
from typing import Optional

from nova.schema import (
    MeaningPacket, IntentType, Assumption,
    LogicCheck,
    UncertaintyLevel,
)
from nova.config import get_config
from nova.model_provider import get_cached_provider


# Stop words that should never appear in key_terms
STOP_WORDS = {
    "a", "an", "the", "is", "it", "in", "at", "of", "to", "for", "on",
    "with", "as", "by", "from", "or", "and", "but", "not", "if", "this",
    "that", "these", "those", "are", "was", "were", "be", "been", "has",
    "have", "had", "do", "does", "did", "will", "would", "can", "could",
    "shall", "should", "may", "might", "am", "being", "been", "having",
    "doing", "what", "how", "why", "when", "where", "who", "which",
    "isnt", "arent", "wasnt", "werent", "dont", "doesnt", "didnt",
    "wont", "wouldnt", "cant", "couldnt", "shouldnt",
    "i", "you", "he", "she", "we", "they", "me", "him", "her", "us",
    "them", "my", "your", "his", "its", "our", "their",
    "about", "into", "over", "after", "before", "between", "under",
    "above", "below", "out", "up", "down", "off", "than",
    "no", "yes", "so", "just", "very", "too", "really", "also",
    "look", "like", "know", "think", "see", "go", "get", "make",
}

# Suppress "all", "every", "no one" etc from keyword extraction if they
# appear alone (they're handled by bias/assumption detection instead)
SUPPRESSED_BIAS_WORDS = {"all", "every", "no", "never", "always", "everyone", "nobody", "no one", "obviously", "clearly", "undeniably", "certainly"}


class LanguageCortex:
    """The Language Cortex breaks raw human language into a structured MeaningPacket."""

    def __init__(self, provider_name: Optional[str] = None):
        self.config = get_config()
        self.provider_name = provider_name or self.config.models.get("language_cortex", "mock")
        provider_cfg = self.config.provider_settings.get(self.provider_name, {})
        self.provider = get_cached_provider(self.provider_name, provider_cfg)

    def process(self, raw_text: str) -> MeaningPacket:
        """Process raw text into a MeaningPacket."""
        cleaned = self._clean_text(raw_text)
        primary_intent, secondary_intents = self._classify_intent(cleaned)
        questions = self._extract_questions(cleaned)
        key_terms = self._extract_key_terms(cleaned)
        assumptions = self._detect_assumptions(cleaned)
        requires_research = self._needs_research(cleaned, primary_intent)
        requires_math = self._needs_math(cleaned, primary_intent)
        requires_science = self._needs_science(cleaned, primary_intent)
        requires_philosophy = self._needs_philosophy(cleaned, primary_intent)
        requires_code = self._needs_code(cleaned, primary_intent)
        bias_flags = self._detect_bias(cleaned)

        # Try to enhance with a real model if configured
        enhanced_text = None
        if self.provider_name != "mock" and self.provider.is_available():
            enhanced_text = self._enhance_with_model(raw_text)
            if enhanced_text:
                # If model returned structured analysis, use its text
                pass

        packet = MeaningPacket(
            raw_text=raw_text,
            cleaned_text=cleaned,
            primary_intent=primary_intent,
            secondary_intents=secondary_intents,
            assumptions=assumptions,
            questions=questions,
            key_terms=key_terms,
            requires_research=requires_research,
            requires_math=requires_math,
            requires_science=requires_science,
            requires_philosophy=requires_philosophy,
            requires_code=requires_code,
            uncertainty=UncertaintyLevel.UNKNOWN,
            logic_check=LogicCheck(),
            bias_flags=bias_flags,
            model_enhanced_text=enhanced_text or "",
        )

        return packet

    # ------------------------------------------------------------------ 
    # Text cleaning
    # ------------------------------------------------------------------ 

    def _clean_text(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        return text

    # ------------------------------------------------------------------ 
    # Intent classification (keyword-scored)
    # ------------------------------------------------------------------ 

    def _classify_intent(self, text: str):
        """Classify the primary and secondary intents."""
        text_lower = text.lower()
        scores = {t: 0 for t in IntentType}

        if text.endswith("?"):
            scores[IntentType.QUESTION] += 3
        for qw in ["what", "why", "how", "when", "where", "who", "which",
                     "explain", "define"]:
            if re.search(r'\b' + qw + r'\b', text_lower):
                scores[IntentType.QUESTION] += 1

        for pw in ["truth", "meaning", "existence", "reality", "consciousness",
                     "ethics", "morality", "knowledge", "belief", "reason",
                     "justice", "freedom", "mind", "soul",
                     "philosophy", "metaphysics", "epistemology"]:
            if pw in text_lower:
                scores[IntentType.PHILOSOPHY] += 1

        for mw in ["calculate", "compute", "speed", "distance", "time",
                     "formula", "equation", "sum", "total", "ratio",
                     "percentage", "measurement", "how many", "mile",
                     "kilometer", "gallon", "degree"]:
            if mw in text_lower:
                scores[IntentType.MATH] += 1
        if re.search(r'\d+\s*[\+\-\*/]\s*\d+', text):
            scores[IntentType.MATH] += 2

        for sw in ["science", "physics", "chemistry", "biology", "experiment",
                     "theory", "hypothesis", "evidence", "study",
                     "gravity", "energy", "force", "mass", "atom", "dna",
                     "evolution", "climate", "quantum", "relativity"]:
            if sw in text_lower:
                scores[IntentType.SCIENCE] += 1

        for rw in ["look up", "search", "find", "research", "investigate",
                     "latest evidence", "current", "news about", "source"]:
            if rw in text_lower:
                scores[IntentType.RESEARCH] += 2

        for cw in ["code", "function", "program", "script", "algorithm",
                     "implement", "debug", "python", "javascript", "api"]:
            if cw in text_lower:
                scores[IntentType.CODE] += 1

        if re.match(r'^(hi|hello|hey|greetings)\b', text_lower):
            scores[IntentType.GREETING] += 2

        if text_lower.startswith(("run ", "execute ", "do ", "tell me ")):
            scores[IntentType.COMMAND] += 1

        for ow in ["think", "believe", "opinion", "feel about", "view on"]:
            if ow in text_lower:
                scores[IntentType.OPINION] += 1

        sorted_intents = sorted(scores.items(), key=lambda x: -x[1])
        primary = sorted_intents[0][0] if sorted_intents[0][1] > 0 else IntentType.UNKNOWN
        secondary = [intent for intent, score in sorted_intents[1:] if score > 0]

        return primary, secondary

    # ------------------------------------------------------------------ 
    # Question / term extraction
    # ------------------------------------------------------------------ 

    def _extract_questions(self, text: str) -> list[str]:
        questions = []
        parts = re.split(r'[.!?]+', text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if re.search(
                r'\b(what|why|how|when|where|who|which|does|is|are|can|'
                r'will|would|should|do|did|have|has)\b',
                part.lower()
            ):
                questions.append(part + "?")
        return questions

    def _extract_key_terms(self, text: str) -> list[str]:
        """Extract meaningful key terms, filtering stop words and bias words."""
        terms = set()
        # Terms from "what is X", "define X", "meaning of X" patterns
        for pattern in [r'what\s+is\s+(\w+(?:\s+\w+)?)', r'define\s+(\w+(?:\s+\w+)?)',
                         r'meaning\s+of\s+(\w+(?:\s+\w+)?)']:
            for m in re.finditer(pattern, text.lower()):
                t = m.group(1).strip()
                if t and t not in STOP_WORDS and t not in SUPPRESSED_BIAS_WORDS:
                    terms.add(t)

        # Capitalized words are usually significant
        for m in re.finditer(r'\b[A-Z][a-z]{2,}\b', text):
            t = m.group(0).lower()
            if t not in STOP_WORDS and t not in SUPPRESSED_BIAS_WORDS:
                terms.add(t)

        # Multi-word quoted phrases
        for m in re.finditer(r'"([^"]+)"', text):
            t = m.group(1).strip().lower()
            if t and t not in STOP_WORDS:
                terms.add(t)

        # Words following prepositions in questions (e.g. "about X", "of X")
        for m in re.finditer(r'\b(about|of|in|on|regarding)\s+(\w+)', text.lower()):
            t = m.group(2)
            if t not in STOP_WORDS and t not in SUPPRESSED_BIAS_WORDS and len(t) > 2:
                terms.add(t)

        # Single important words from "what is X" - filter stop words
        result = [t for t in terms if len(t) > 2 or t.isupper()]
        return result

    # ------------------------------------------------------------------ 
    # Assumption / bias detection
    # ------------------------------------------------------------------ 

    def _detect_assumptions(self, text: str) -> list[Assumption]:
        assumptions = []
        trigger_phrases = [
            ("obviously", True), ("clearly", True), ("of course", True),
            ("everyone knows", True), ("it is known", True),
            ("always", False), ("never", False), ("all", False),
            ("every", False), ("no one", False), ("everyone", False),
            ("without a doubt", True), ("certainly", True),
            ("undeniably", True), ("all the time", True),
        ]
        text_lower = text.lower()
        for phrase, is_high in trigger_phrases:
            if phrase in text_lower:
                assumptions.append(Assumption(
                    statement="Contains potentially unsupported claim marker: '%s'" % phrase,
                    trigger_words=[phrase],
                    is_unsupported=True,
                    risk_level="high" if is_high else "medium",
                ))
        return assumptions

    # ------------------------------------------------------------------ 
    # Requirement detection
    # ------------------------------------------------------------------ 

    def _needs_research(self, text: str, intent: IntentType) -> bool:
        if intent == IntentType.RESEARCH:
            return True
        keywords = ["look up", "search", "find", "latest", "current evidence",
                     "research", "study", "source", "data about"]
        return any(kw in text.lower() for kw in keywords)

    def _needs_math(self, text: str, intent: IntentType) -> bool:
        if intent == IntentType.MATH:
            return True
        return bool(re.search(r'\b\d+\s*(miles|km|hours|minutes|speed|rate|total|per)\b', text.lower()))

    def _needs_science(self, text: str, intent: IntentType) -> bool:
        if intent == IntentType.SCIENCE:
            return True
        sw = ["physics", "chemistry", "biology", "experiment", "scientific",
              "theory of", "gravity", "quantum", "evolution"]
        return any(w in text.lower() for w in sw)

    def _needs_philosophy(self, text: str, intent: IntentType) -> bool:
        if intent == IntentType.PHILOSOPHY:
            return True
        pw = ["truth", "meaning", "existence", "reality", "consciousness",
              "ethics", "morality", "purpose", "why are we",
              "philosophy", "metaphysics", "ontology", "epistemology"]
        return any(w in text.lower() for w in pw)

    def _needs_code(self, text: str, intent: IntentType) -> bool:
        return intent == IntentType.CODE or any(
            w in text.lower() for w in ["code", "function", "program", "script"]
        )

    def _detect_bias(self, text: str) -> list[str]:
        flags = []
        bias_patterns = [
            (r'\b(all|every|no one|nobody|everyone)\b', "Absolute language (all/every/none)"),
            (r'\b(obviously|clearly|undeniably|without a doubt)\b', "False certainty marker"),
            (r'\b(always|never)\b', "Absolutes (always/never)"),
            (r'\b(they|them|those people)\b', "Vague group reference"),
        ]
        for pattern, label in bias_patterns:
            if re.search(pattern, text.lower()):
                flags.append(label)
        return flags

    # ------------------------------------------------------------------ 
    # Model enhancement (real provider path)
    # ------------------------------------------------------------------ 

    def _enhance_with_model(self, raw_text: str) -> Optional[str]:
        """Call a real model provider and return its analysis.

        Returns the model's text output, or None on failure.
        The calling code attaches it to the packet.
        """
        prompt = (
            "Analyze this text and extract structured meaning:\n"
            "Text: %s\n\n"
            "Provide:\n"
            "1. Cleaned version\n"
            "2. Primary intent (question/analysis/research/philosophy/math/science/code)\n"
            "3. Key terms\n"
            "4. Detected assumptions\n"
            "5. Missing variables for a complete answer"
        ) % raw_text
        try:
            result = self.provider.generate(prompt)
            return result
        except Exception:
            return None
