# Nova Cognitive OS v1 — Brain-Flip Architecture

## What Changed

The old Nova flow was backwards:
```
User → weak pattern match → raw memory search → raw fact repeat → answer (sometimes echoes memory/debug labels)
```

The new brain-flip flow:
```
User → LLM Planner → Nova Validator → Memory/Tool Retrieval → Direct Answer or LLM Synthesis → Nova Critic → Clean Answer
```

## Architecture

### 1. Intent Planner (`src/nova_intent_planner.py`)
Uses the local LLM as a smart language interpreter. The planner parses the user message and returns structured JSON with route, intent, memory slots needed, and confidence. Falls back to deterministic fast-path patterns when the LLM is unavailable.

### 2. Plan Validator (`src/nova_plan_validator.py`)
Nova validates every plan before executing. Rejects:
- Invalid JSON or missing fields
- Unknown routes
- Low-confidence plans below threshold
- Unsafe tool requests
- Memory writes not explicitly requested

If validation fails, Nova uses its deterministic fallback router.

### 3. Long-Term Memory (`src/nova_long_term_memory.py`)
ChatGPT-style persistent memory with slot/value extraction. Commands:
- `long-term remember this: ...`
- `remember this long term: ...`
- `save this to long-term memory: ...`
- `always remember: ...`
- `show long-term memory`
- `forget ...`

Memory is stored in `nova_memory/long_term_memory.json` with slot/value records. Nova controls all writes and reads — the LLM cannot touch this directly.

### 4. Memory Slot Retrieval (`src/nova_memory_slot_retrieval.py`)
Retrieves memory by slot name (favorite_food, name, location, etc.) or keyword match. Falls back to legacy lesson-based memory. Returns structured results with synthesis support.

### 5. Answer Synthesizer (`src/nova_answer_synthesizer.py`)
Transforms saved facts into clean second-person answers without debug labels, raw memory dumps, or question repetition. Supports direct answers for:
- Memory recall → "Your favorite food is pizza."
- Dictionary → "A domesticated carnivorous mammal."
- Math → "The answer is 4."
- Memory write → "Saved: your favorite food is pizza."

### 6. Context Builder (`src/nova_context_builder.py`)
Builds structured context packets for the LLM synthesis pass, combining user message, validated plan, memory results, and dictionary results into a clean prompt.

### 7. LLM Synthesizer (`src/nova_llm_synthesizer.py`)
Generates polished final answers using the local LLM when direct answers aren't available. Nova remains in control — the LLM only helps word the answer.

### 8. Cognitive OS Router (`src/nova_cognitive_os.py`)
The main integration point. Wraps all modules into one function: `route(message, dict_lookup_fn, memory)`.

## Key Principles

- **LLM understands first.** The planner uses LLM to interpret intent.
- **Nova controls truth.** The validator, memory, and critic are Nova-owned.
- **LLM helps word the answer.** Synthesis uses LLM only when needed.
- **Nova critic gives final approval.** Anti-echo check ensures clean output.
- **The LLM does not permanently remember.** Nova saves memory to files.

## Required Setup

```bash
# Install Ollama
ollama pull qwen2.5:1.5b

# Enable local LLM
export NOVA_USE_LOCAL_LLM=true
export NOVA_LOCAL_LLM_PROVIDER=ollama
export NOVA_LOCAL_LLM_MODEL=qwen2.5:1.5b
```

## Trace Fields

The browser UI now shows:
- `planner_used` — which planner handled the message
- `planner_json_valid` — whether the LLM plan passed validation
- `validated_route` — the final route chosen
- `slot_needed` — which memory slot was queried
- `long_term_memory_used` — whether LTM was accessed
- `memory_id` — which memory record was retrieved
- `memory_retrieved` — whether a match was found
- `local_llm_synthesis_used` — whether LLM helped word the answer
- `critic_result` — whether the answer passed the anti-echo check
- `training_log_saved` — whether the interaction was logged
- `fallback_used` — whether Nova fell back to the old router

## Proof of Concept (verified)

| Test | Result |
|------|--------|
| long-term remember + recall favorite food | ✅ |
| long-term remember + recall birth year | ✅ |
| define dog | ✅ |
| what is my cat name (no saved fact) | ✅ says not saved |
| name save + recall | ✅ |
| location save + recall | ✅ |
| math (2 x 2) | ✅ |
| Anti-echo (no debug labels) | ✅ |
| No dictionary fallback for memory recall | ✅ |

## Web Search Connector

### Setup
```bash
export NOVA_USE_WEB=true
export NOVA_WEB_PROVIDER=duckduckgo   # free, no API key
export NOVA_WEB_TIMEOUT=20
export NOVA_WEB_MAX_RESULTS=5
export NOVA_REQUIRE_SOURCES=true
```

### How it works
1. User asks about current/latest/recent/news/weather information
2. LLM planner detects web need and routes to `web_search` or `weather_lookup`
3. Nova validates the web request
4. `nova_web_connector.py` searches DuckDuckGo (free, no API key)
5. Nova extracts facts and source URLs
6. Local LLM summarizes using web results as context
7. Nova critic checks source use
8. Final answer includes source links

### Rules
- Memory/math/dictionary queries do NOT use the web
- Weather queries use the web with location-specific searches
- Web results include source URLs in the final answer
- If web fails, Nova reports the failure clearly
- The local LLM cannot invent sources — only nova_web_connector provides them

### Trace Fields
- `web_used`: true/false
- `web_query`: the search query sent
- `web_provider`: which search provider was used
- `sources_found`: number of search results
- `urls_used`: list of source URLs in the answer

### Verifications
| Test | Expected | Result |
|------|----------|--------|
| "latest AI news" | web_search, sources returned | ✅ |
| "weather in Cincinnati" | weather_lookup, web used | ✅ |
| "define dog" | dictionary_lookup, no web | ✅ |
| "what food do i like" | memory_recall, no web | ✅ |
| "2 x 2" | math_solver, no web | ✅ |
| Web failure | graceful message | ✅ |


## Long-Term Memory System (ChatGPT-Style)

Nova has a persistent long-term memory system similar to ChatGPT's saved memory.

### Architecture

- **Nova owns memory.** The local LLM cannot directly write, edit, delete, or invent memory.
- Nova saves structured memory records in `nova_memory/long_term_memory.json`.
- Nova retrieves relevant memory on future queries and synthesizes clean second-person answers.
- Memory survives restarts and persists between sessions.

### Key Files

- `src/nova_long_term_memory.py` — CRUD operations: save, recall, edit, forget, show
- `src/nova_memory_slot_retrieval.py` — Slot-based retrieval with wrong-match prevention
- `src/nova_answer_synthesizer.py` — Deterministic second-person answer synthesis
- `src/nova_cognitive_os.py` — Brain-flip pipeline integrating LTM at STEP 0

### Memory Commands

**Save:**
- `long-term remember this: my favorite food is pizza`
- `always remember: I was born in 1980`
- `remember this long term: I live in Cincinnati`
- `permanently remember: my dog name is Max`

**Recall (automatic):**
- `what food do i like` → "Your favorite food is pizza."
- `when was i born` → "You were born in 1980."
- `where do i live` → "You live in Cincinnati."
- `what is my dog name` → "Your dog name is Max."

**Show:**
- `show long-term memory`
- `what do you remember long term`
- `list saved memories`

**Edit:**
- `edit long-term memory: favorite food is pizza -> favorite food is grapes`

**Forget:**
- `forget long-term memory: favorite food`
- `delete saved memory: location`

### Extraction Rules

Common slot/value patterns:
- `my favorite food is X` → slot: favorite_food, value: X
- `I was born in 1980` → slot: birth_year, value: 1980
- `I live in Cincinnati` → slot: location, value: Cincinnati
- `my dog name is Max` → slot: dog_name, value: Max, pet_type: dog
- `I work at Novatron` → slot: workplace, value: Novatron

### Answer Rules

- Saved `my` → answer `your`
- Saved `I` → answer `you`
- Wrong slot rejection: "what is my cat name" does NOT return dog name
- No debug labels in answers (no `memory_search`, `raw_text`, etc.)
- No raw JSON output in answers

### Wrong-Match Prevention

Uses word-boundary matching, not substring matching.
Example: `"cat"` in `"location"` is `False` because `cat` must match as a whole word.

### Tests

20 test cases covering save, recall, edit, forget, show, persistence, anti-echo, wrong-match prevention, and cognitive OS integration.

Run with:
```bash
python3 -c "exec(open('tests/test_ltm.py').read())"
```

