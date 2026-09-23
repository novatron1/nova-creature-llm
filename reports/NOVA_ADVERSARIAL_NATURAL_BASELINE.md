# Nova Adversarial Evaluation

- Bank: `nova-adversarial-1.0`
- Cases: 10
- Passed cases: 5
- Overall rubric score: **50.0%**
- HTTP/runtime errors: 1
- Total runtime: 42.6 seconds

## Category results

| Category | Score | Passed | Cases | Errors |
|---|---:|---:|---:|---:|
| natural_conversation | 50.0% | 5 | 10 | 1 |

## Failed or weak cases

- `human_comparison` (natural_conversation): 0.0% — contains a valid idea
- `girlfriend_words` (natural_conversation): 0.0% — contains a valid idea
- `joke` (natural_conversation): 0.0% — joke structure
- `disagreement` (natural_conversation): 0.0% — contains a valid idea
- `ask_clarify` (natural_conversation): 0.0% — contains a valid idea

## Interpretation limits

- This bank is a bounded engineering regression suite, not an IQ test.
- Deterministic keyword and format rubrics can miss some semantically correct answers.
- Passing does not prove correctness on questions outside the tested behaviors.
- Evaluation turns cannot write long-term memory; session continuity is temporary.
