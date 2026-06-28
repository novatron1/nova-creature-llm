# Stage 8 Report: Model Registry & Swap Plan

## Status: COMPLETE

### Files Created
- `nova/model_registry.py` - ModelRegistry with swap plan documentation

### What Works
- ModelRegistry maps any module name to a provider name
- register() and switch_all() methods for bulk reconfiguration
- list_registrations() shows current mapping
- get_provider_for() returns the configured provider instance
- describe_swap_plan() documents the full migration strategy

### Swap Plan (from describe_swap_plan)
1. Local models via Ollama (llama3)
2. HuggingFace small models (flan-t5-base for control modules)
3. OpenAI (gpt-4o for language cortex, philosopher, voice)
4. Hybrid: different providers for different modules

### Next Stage
- Grand roadmap and README
