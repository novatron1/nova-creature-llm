# Nova Creature — Training & Local LLM Cortex Report

## 1. All 7 Roles Training Complete (60 epochs each)

| Role | Original Hash | New Hash | Status |
|------|---------------|----------|--------|
| left_hemisphere | `77f5e4170883c15c` | `b8b666c728c99465` | ✅ |
| right_hemisphere | `f6b4bc74c99c6260` | `97b02c2db041e766` | ✅ |
| memory_transformer | `28b405a901e1ce30` | `52c8a5afe71f4c74` | ✅ |
| planner_transformer | `4dfa2b3e2580b8c8` | `3bcf133f5e780766` | ✅ |
| critic_conscience_transformer | `08c6382b2f6f3517` | `bf8a2fd4bc69ffce` | ✅ |
| dream_simulation_transformer | `d18eba5373f9ca7f` | `8f52357121821541` | ✅ |
| speech_output_transformer | `d91cfe0f464e6bd5` | `e178d97a8122894f` | ✅ |

**Training config:** 60 epochs/role, 300 seqs/epoch, lr=0.0003
**Data:** 629 safe sequences (tokens < 560) from 1311 deduplicated pairs
**Engine:** NumPy with gradient clipping, stable softmax

### Loss Progression

- **left_hemisphere:** 7.84 → **3.72** (1280s, improved from 3.84 on 2nd pass)
- **right_hemisphere:** 5.71 → **4.07** (1180s)
- **memory_transformer:** 5.32 → **4.03** (1850s)
- **planner_transformer:** 5.39 → **4.34** (1426s)
- **critic_conscience_transformer:** 5.41 → **4.35** (1316s)
- **dream_simulation_transformer:** 5.49 → **4.46** (interrupted, completed 60 epochs)
- **speech_output_transformer:** 5.68 → **4.43** (1631s)

**Total training time:** Approx 8.5 hours across all 7 roles.

## 2. Local LLM Cortex Connector

### New Files Created

| File | Purpose |
|------|---------|
| `src/nova_local_llm_connector.py` | Connector module — Ollama + LM Studio support |
| `src/nova_llm_router_integration.py` | Route decision, prompt builder, critic, feedback handler |
| `.nova_llm_config` | Configuration file (env vars also supported) |
| `nova_training_logs/local_llm_calls.jsonl` | Training log for all LLM calls |
| `nova_training_logs/feedback.jsonl` | User feedback log ("good answer", "bad answer", etc.) |

### Architecture

```
User message
  → Nova input normalizer
  → Nova dictionary / meaning expansion
  → Nova memory lookup
  → Nova 7-role transformer route voting
  → Nova route selector → decides if local LLM should be called
  → Nova builds task-specific prompt (with route, memory, dictionary context)
  → local LLM generates fluent answer
  → Nova critic checks answer
  → Nova final speech output
  → Nova saves training log
```

### Supported Providers

- **Ollama:** `http://127.0.0.1:11434/api/generate`
- **LM Studio:** `http://127.0.0.1:1234/v1/chat/completions`

### Config (`.nova_llm_config` or env vars)

```
NOVA_USE_LOCAL_LLM=true
NOVA_LOCAL_LLM_PROVIDER=ollama
NOVA_LOCAL_LLM_MODEL=qwen2.5:1.5b
NOVA_LOCAL_LLM_URL=http://127.0.0.1:11434/api/generate
NOVA_LOCAL_LLM_TIMEOUT=30
NOVA_LOCAL_LLM_FALLBACK=true
NOVA_LOG_LOCAL_LLM_PROMPTS=true
```

### Route Decision Logic

- **Memory recall**, **dictionary lookup**, **simple math** → handled locally by Nova
- **General conversation**, **coding**, **planning**, **explanation**, **creative** → sent to local LLM
- **Local LLM unavailable** → silent fallback to Nova's transformer/template system

### Trace Output

Route trace includes:
- `local_llm_used: true/false`
- `local_llm_provider: ollama`
- `local_llm_model: qwen2.5:1.5b`
- `selected_route: left_hemisphere -> planner_transformer`
- `critic_result: accepted`
- `fallback_reason: "Ollama error: Connection refused"` (if unavailable)

## 3. How to Use on Laptop

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. Pull a model
ollama pull qwen2.5:1.5b
# or: ollama pull llama3.2:3b

# 3. Enable local LLM in Nova
echo "NOVA_USE_LOCAL_LLM=true" >> .nova_llm_config
echo "NOVA_LOCAL_LLM_MODEL=qwen2.5:1.5b" >> .nova_llm_config

# 4. Start Nova server
python3 nova_enhanced_server.py
```

Without local LLM, Nova falls back to its internal transformer system.

## 4. GitHub

All changes pushed to `origin/master`:
```bash
git commit -m "feat: 60-epoch training all 7 roles + local LLM cortex connector"
git push origin master
```
