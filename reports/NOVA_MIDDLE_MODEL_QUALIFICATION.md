# Nova Middle Model Qualification

- Status: **NOT QUALIFIED**
- Model: `qwen2.5:3b`
- Provider: `ollama`
- Pack: `nova-private-local-2.0`
- Repeated runs: 3
- Cases per run: 20
- Overall score: 70.0%
- Required score: 85.0%
- Critical capability floor: 25.0%
- Average case latency: 3100.3 ms
- Primary model changed: False

## Capability scores

| Capability | Score |
|---|---:|
| coding | 75.0% |
| conversation_continuity | 25.0% |
| instruction_following | 100.0% |
| reasoning | 66.7% |
| structured_output | 100.0% |

## Repeated runs

| Run | Score | Passed | Cases | Average latency |
|---:|---:|---:|---:|---:|
| 1 | 70.0% | 14 | 20 | 2261.8 ms |
| 2 | 70.0% | 14 | 20 | 3880.4 ms |
| 3 | 70.0% | 14 | 20 | 3158.6 ms |

## Guardrails

- This test never changes Nova's 1.5B primary chat model.
- A pass qualifies the model only as a replaceable local escalation tier.
- Raw adapters are excluded and are never intercepted by this evaluator.
- Prompts and generated model text are not written to the quality registry.
- This bounded test is not an IQ or general-intelligence measurement.
