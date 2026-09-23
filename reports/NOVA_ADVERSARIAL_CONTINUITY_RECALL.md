# Nova Adversarial Evaluation

- Bank: `nova-adversarial-1.0`
- Cases: 10
- Passed cases: 8
- Overall rubric score: **80.0%**
- HTTP/runtime errors: 2
- Total runtime: 81.2 seconds

## Category results

| Category | Score | Passed | Cases | Errors |
|---|---:|---:|---:|---:|
| conversation_continuity | 80.0% | 8 | 10 | 2 |

## Failed or weak cases

- `codeword` (conversation_continuity): 0.0% — exact answer
- `favorite_color` (conversation_continuity): 0.0% — contains a valid idea

## Interpretation limits

- This bank is a bounded engineering regression suite, not an IQ test.
- Deterministic keyword and format rubrics can miss some semantically correct answers.
- Passing does not prove correctness on questions outside the tested behaviors.
- Evaluation turns cannot write long-term memory; session continuity is temporary.
