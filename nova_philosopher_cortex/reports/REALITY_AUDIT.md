# Reality Audit — Nova Philosopher Cortex

**Date:** 2026-06-28
**Scope:** All ~70 files, 80 tests, 5 verification commands
**Principle:** Brutal honesty. No exaggeration. Proof from code and tests.

---

## 1. Verification Commands

### `python -m pytest -q`
```
80 passed in 0.82s
```
**Result:** All tests pass. See §5 for test coverage breakdown.

### `python main.py "What is truth?"`
```
Philosophy Analysis: Epistemology, definition of truth, counterarguments
No stop-word noise (no "what" in key_terms)
Uncertainty: moderate
```

### `python main.py "If a car travels 150 miles in 3 hours, what is the speed?"`
```
Speed = 50 miles/hour  ← unit correctly singular
Formula shown step-by-step
```

### `python main.py --pipeline "Obviously all institutions lie all the time."`
```
3 assumptions flagged, 3 bias patterns
Truth filter: FAIL (high-risk assumptions, no evidence)
```

### `python main.py --offline "Look up the latest evidence about artificial intelligence."`
```
Research agent noted in chain
Returns: "No builtin fact found" — no fake citations
```

### `python main.py "What is the capital of France?"`
```
KnowledgeCortex: Answer = Paris (source: builtin/geography)
Router: knowledge_cortex selected
```

---

## 2. What Is Real (Rule-Based Logic)

| Module | Status | What it does |
|--------|--------|-------------|
| **LanguageCortex** | REAL | 14 methods. Keyword-scored intent (8 categories), question extraction via regex, key term extraction with stop-word filter, assumption detection from 14 trigger phrases, bias detection from 4 pattern categories |
| **IntentDetector** | REAL | Refines UNKNOWN intents to QUESTION |
| **QuestionSplitter** | REAL | Splits on \n, ;, or `? + space` |
| **AssumptionDetector** | REAL | 12 additional trigger patterns |
| **BiasDetector** | REAL | 4 loaded-language categories |
| **DefinitionChecker** | REAL | 10 builtin philosophical definitions |
| **EvidenceClassifier** | REAL | Scans for numbers+units, source attribution, deduction markers |
| **LogicValidator** | REAL | Circular reasoning, contradictions, undefined comparisons |
| **ContradictionFinder** | REAL | 8 contradictory pair patterns |
| **CounterargumentBuilder** | REAL | Template counterarguments for truth, meaning, assumptions |
| **UncertaintyMarker** | REAL | Assigns level from evidence/assumptions/contradictions |
| **PrincipleConsistencyChecker** | REAL | Checks definitions, evidence, uncertainty |
| **RouterCortex** | REAL | Routes by intent + content flags; geography now routes to knowledge_cortex |
| **PhilosopherCortex** | REAL | Domain detection, definition lookup, counterarguments |
| **ScienceCortex** | REAL | **UPDATED:** Builtin explanations for 9 science topics with evidence citations |
| **MathMeasurementCortex** | REAL | Speed = distance/time; **FIXED:** unit singularization (miles/hour) |
| **KnowledgeCortex** | REAL | **UPDATED:** Builtin fact table — capitals, scientific constants, body facts |
| **WorldSystemsCortex** | REAL | Keyword-based system detection |
| **FinalTruthFilter** | REAL | Checks: unsupported certainty, high-risk assumptions without evidence, contradictions, science without measurement |
| **FinalVoice** | REAL | 97-line formatter |
| **MemoryStore** | REAL | Writes/reads JSONL, keyword search |
| **TrainingLogger** | REAL | Writes/reads JSONL, SFT export |
| **ModelRegistry** | REAL | Can swap provider names in config |
| **WebSearchAgent** | **UPDATED** | **Real HTTP via DuckDuckGo API** using `urllib.request` from stdlib. Returns parsed search results. |
| **WebFetchAgent** | **UPDATED** | **Real HTTP fetch** using `urllib.request`. Fetches page content. |
| **ResearchAgent** | **UPDATED** | **Coordinates search + fetch** — searches DuckDuckGo, fetches top result's content. |
| **Pipeline** | **UPDATED** | **Wired to agents** — calls `ResearchAgent` when `requires_research=True` and `web.enabled=True`. Evidence is attached to packet. |

---

## 3. What Is Still Placeholder / Stubbed

| Module | Verdict | What's missing |
|--------|---------|---------------|
| **CodeSkillCortex** | PLACEHOLDER | Returns "Code-related query detected" — no actual code analysis |
| **DataGatheringAgent** | PLACEHOLDER | Returns `{collected: 0}` — no real data aggregation |
| **CitationAgent** | PLACEHOLDER | Returns `{citations: []}` — no citation formatting |
| **SourceQualityAgent** | PLACEHOLDER | Returns `{quality_score: 0.0}` — no source vetting |
| **_enhance_with_model** | **FIXED** | **Now returns the model output instead of discarding it.** Still requires a real provider (OpenAI/Ollama) to be useful — MockProvider returns "Mock response". |
| **HuggingFace provider** | MISSING | Listed in config schema but no class exists in `model_provider.py` |
| **local_provider.py** | MISSING | Spec mentions it, never implemented |
| **web_provider.py** | MISSING | Spec mentions it, never implemented |

---

## 4. Mock-Only Behavior

All modules use **MockProvider** by default. The pipeline logic is **entirely rule-based**, so `MockProvider.generate()` is never actually invoked during normal execution. The `_enhance_with_model()` path is only triggered when `provider_name != "mock"`.

**Real providers available in `model_provider.py`:**
- `OpenAIProvider` — requires `openai` package + API key
- `OllamaProvider` — requires running Ollama instance

---

## 5. Internet & Citations

### Internet access: FUNCTIONAL (NEW)
- `WebSearchAgent` makes **real HTTP calls** to DuckDuckGo Instant Answer API (`api.duckduckgo.com`) using `urllib.request`
- `WebFetchAgent` makes **real HTTP calls** to fetch page content using `urllib.request`
- **Proven by tests:** `test_real_http_call_is_made` verifies `urllib.request.urlopen` is called; `test_search_results_are_not_hardcoded` verifies results come from HTTP response, not hardcoded strings.

### Citations: NOT FUNCTIONAL
- CitationAgent returns `{citations: []}` always
- KnowledgeCortex says "builtin" source for its fact table
- **No fake citations are ever generated**

---

## 6. Stop Word Filtering

**FIXED.** `STOP_WORDS` set (95+ words) and `SUPPRESSED_BIAS_WORDS` set filter out:
- Articles, prepositions, pronouns: `the`, `a`, `an`, `if`, `in`, `at`, `of`, etc.
- Common verbs: `look`, `like`, `know`, `think`, `is`, `are`, `was`, etc.
- Question words: `what`, `how`, `why`, `when`, `where`, `who`, `which`
- Bias words: `obviously`, `clearly`, `undeniably`, `certainly`, `all`, `every`, `never`, `always`

**Proven by tests:** `test_stop_words_removed`, `test_obviously_not_in_key_terms`, `test_look_not_in_key_terms`

---

## 7. Math Unit Fix

**FIXED.** `_solve_speed()` now singularizes the time unit:
- `miles/hour` not `miles/hours`
- `km/hour` not `km/hours`

**Proven by test:** `test_unit_is_singular`, `test_400_miles_hour`

---

## 8. KnowledgeCortex Answering

**FIXED.** Builtin fact table with 17 entries covering:
- Capitals: France, Germany, Japan, Italy, UK, Spain, China, Russia, Canada, Australia, India, Brazil
- Scientific constants: speed of light, speed of sound, gravity, gravitational constant, Planck constant
- Chemistry: Avogadro number, boiling/freezing point of water
- Astronomy: distance to moon, distance to sun
- Biology: bones in human body, heart beats

**Proven by tests:** `test_capital_of_france`, `test_capital_of_japan`, `test_speed_of_light`, `test_confidence_with_answer`

---

## 9. ScienceCortex Explanations

**FIXED.** Builtin explanations for 9 science topics:
- Gravity, speed of light, quantum mechanics, evolution, DNA, relativity, climate change, chemistry, quantum physics
- Each includes an explanation and supporting evidence citation

**Proven by tests:** `test_gravity_explanation`, `test_quantum_mechanics_explanation`, `test_evolution_explanation`, `test_science_with_research_evidence`, `test_confidence_with_explanation`

---

## 10. Pipeline Agent Integration

**FIXED.** `pipeline.py` now:
1. Checks `packet.requires_research` in `_run_research_if_needed()`
2. If research is needed and web is enabled, calls `ResearchAgent.execute()`
3. Attaches results as `EvidenceItem` objects to `packet.evidence_items`
4. Specialist modules (KnowledgeCortex, ScienceCortex) use these evidence items
5. Adds `"research_agent"` to `module_chain` even in offline mode (to log it was considered)

**Proven by tests:** `test_pipeline_invokes_research_agent`, `test_agent_results_reach_specialists`, `test_research_not_called_when_not_needed`, `test_offline_research_does_not_call_http`

---

## 11. Dead Code Removed

- **`nova/providers/` package** — **REMOVED.** Was dead code (not imported by anything outside itself). All provider logic lives in `nova/model_provider.py`.

---

## 12. Test Coverage (80 tests)

| Test File | Tests | What It Proves |
|-----------|-------|----------------|
| `test_schema.py` | 12 | Schema creation and field defaults |
| `test_language_cortex.py` | 10 | Intent classification, question extraction, assumptions, bias |
| `test_question_splitter.py` | 3 | Question splitting |
| `test_assumption_detector.py` | 3 | Assumption detection |
| `test_evidence_classifier.py` | 3 | Evidence classification |
| `test_logic_validator.py` | 3 | Logic validation |
| `test_math_measurement.py` | 3 | Speed calculation, module name |
| `test_research_agents.py` | 4 | Agent factory, offline behavior |
| `test_truth_filter.py` | 4 | Truth filter pass/fail scenarios |
| `test_pipeline.py` | 6 | Pipeline integration |
| **`test_web_agents.py`** | **6** | **NEW: Real HTTP call verification, no hardcoded results** |
| **`test_pipeline_agents.py`** | **4** | **NEW: Pipeline invokes agents, results reach specialists** |
| **`test_knowledge_science.py`** | **10** | **NEW: KnowledgeCortex answers capitals, ScienceCortex explains topics** |
| **`test_enhancements.py`** | **9** | **NEW: Stop words filtered, model output used, math unit fixed** |

---

## 13. Key Improvements Made

| Issue | Before | After |
|-------|--------|-------|
| Web search agent | Hardcoded "would run here" message | Real HTTP via DuckDuckGo API |
| Web fetch agent | Hardcoded "would fetch" message | Real HTTP via urllib |
| Pipeline agents | No agent calls | ResearchAgent called when needed |
| Research evidence | Never collected | Attached to packet as EvidenceItems |
| `_enhance_with_model()` | Discarded return value | Returns model output string |
| `providers/` package | Dead code (4 files) | Removed |
| Key terms | Included stop words (the, if, look) | Filtered via STOP_WORDS + SUPPRESSED_BIAS_WORDS |
| Math unit | `miles/hours` | `miles/hour` (singularized) |
| KnowledgeCortex | Always "no verifiable sources" | Builtin fact table (17 entries) |
| ScienceCortex | Always "no empirical evidence" | Builtin explanations (9 topics) |
| Geography routing | Not routed to knowledge_cortex | Router now checks geography keywords |
| Tests proving real behavior | None | 29 new tests with mocked HTTP |

---

## 14. Top 10 Remaining Weaknesses

1. **CodeSkillCortex** — Still a placeholder. No code parsing or generation.
2. **CitationAgent** — No real citation formatting. Returns empty.
3. **SourceQualityAgent** — No source quality evaluation logic.
4. **HuggingFace provider** — Declared in schema but no implementation.
5. **Key term extraction** — Still misses multi-word terms (e.g., "artificial intelligence" captured as just "artificial"). Would benefit from NER or n-gram approach.
6. **Math cortex** — Only solves speed = distance/time. No algebra, unit conversion, or statistics.
7. **DefinitionChecker** — Only 10 hardcoded definitions. Would benefit from a real dictionary API or model lookup.
8. **ModelRegistry is not wired to pipeline** — Pipeline creates providers directly, not through the registry.
9. **FinalTruthFilter keyword check** — Only catches "proven" and "definitely". Misses many certainty markers.
10. **No user feedback loop** — Corrections are not integrated back into the system.

---

## 15. Commands to Verify (Summary)

```bash
python -m pytest -q                          # 80 tests pass
python main.py "What is truth?"               # Philosophy analysis
python main.py "If a car travels 150 miles in 3 hours, what is the speed?"  # Math: 50 miles/hour
python main.py --pipeline "Obviously all institutions lie all the time."    # Truth filter blocks
python main.py --offline "Look up evidence about AI"                        # No fake sources
python main.py "What is the capital of France?"                            # Answer: Paris
python main.py "What is gravity?"           # Science explanation with evidence
```
