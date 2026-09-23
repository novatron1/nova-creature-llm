# Nova Cognitive Upgrade Baseline

Recorded before the cognitive operating-layer implementation on 2026-07-23.

## Repository snapshot

- Git HEAD: `2e5dfb4`
- The worktree already contained extensive user-owned application, training,
  checkpoint, model, configuration, report, and UI changes.
- Those existing dirty-worktree changes were preserved. No reset, checkout,
  deletion, checkpoint rewrite, model-weight change, or training change was
  used for this upgrade.

## Discovered request path

```text
POST /api/chat
  -> nova_enhanced_server._run_nova_chat_turn(...)
  -> nova_enhanced_server.brain_route(...)
  -> nova_cognitive_os.route(...)
  -> nova_llm_synthesizer._build_prompt(...) / generate(...)
  -> nova_local_llm_connector.LocalLLMConnector
  -> local Ollama model
  -> nova_natural_chat shaping
  -> existing /api/chat response contract
```

Nova already had a compatibility gateway under `src/nova_gateway`, an existing
agent wrapper, memory implementations, deterministic checks, source retrieval,
OpenAI-compatible routes, and Ollama integration. The upgrade wraps and extends
those components instead of replacing them.

## Baseline tests

- Command: `py -3.11 -m pytest -q`
- Result: **1,055 passed, 10 skipped**
- Runtime: **80.42 seconds**
- Existing failures: **0**

## Baseline model/config findings

- Regular chat model: `qwen2.5:1.5b`
- Existing configured context value: `16384`
- Installed Qwen3 model: `qwen3:14b-q4_K_M`
- Existing natural conversation layer: enabled
- Existing Ollama path: enabled
- Existing raw Qwen and Dolphin adapter modes: present and protected

The user-specified original 2,048-token constraint was not the value in the
working configuration at inspection time. A separate, explicit 8K Qwen3 alias
was still created so its context contract is stable and does not overwrite the
source model.
