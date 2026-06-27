# Nova fast/deep LLM and bigger transformer upgrade

## Goal

Make Nova feel faster in live chat while preserving the deeper DeepSeek reasoning path, and prepare Nova's own transformer for a safe larger candidate instead of overwriting the current brain.

## Design

1. Add a fast/deep local model split:
   - Fast model: `qwen2.5:1.5b` for planner, ordinary synthesis, fallback wording, and quick chat.
   - Deep model: `deepseek-r1:7b` for academic/deep reasoning, critic-heavy prompts, hard coding, and explicit “think harder” style work.
   - Keep `NOVA_LOCAL_LLM_MODEL=deepseek-r1:7b` as the deep default for rollback compatibility, but add explicit fast/deep config keys.

2. Let each local LLM call override the model and timeout without mutating global config.

3. Add tests that prove:
   - Qwen is selected for planner and ordinary synthesis.
   - DeepSeek remains selected for academic/deep synthesis.
   - Ollama payloads receive the per-call model override.

4. Prepare bigger transformer work as a candidate path:
   - Define a medium config target around `d_model=192`, `n_layers=4`, `n_heads=6`, longer context.
   - Do not promote or overwrite live checkpoints automatically.
   - Promotion only happens after checkpoint existence, benchmark, and rollback gates pass.

## Safety

Do not replace live role checkpoints during this step. The existing app stays usable while the faster model routing is tested.
