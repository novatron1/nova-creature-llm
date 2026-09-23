# Raw + Memory Truth Guard

## Goal

Keep Raw + Memory fast and adapter-only for ordinary prompts while preventing unsupported personal-memory claims, repeated filler, and identity confusion.

## Behavior

1. Memory-shaped prompts receive a bounded, verified-memory block before raw generation.
2. If no verified memory matches, the prompt explicitly requires an honest “not saved” answer.
3. Raw answers are checked for repetition and unsupported personal-memory claims.
4. One strict raw retry is allowed after a rejected answer.
5. If the strict retry is rejected, the configured Nova LLM is used as the final fallback; no canned generic recovery answer is emitted.
6. Ordinary Raw + Memory prompts keep their current no-tools/no-provider-fallback semantics.

## Acceptance Criteria

- Open-ended recall cannot return a confident personal fact when no verified memory was supplied.
- Repeated filler such as “I get you” is rejected and retried.
- Verified memory values can be used by the raw answer.
- Traces identify the memory guard, retry, and LLM fallback when used.
- Existing raw adapter, memory, and normal-chat tests remain green.
