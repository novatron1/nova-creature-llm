# Nova Adversarial Evaluation

- Bank: `nova-adversarial-1.0`
- Cases: 10
- Passed cases: 6
- Overall rubric score: **60.0%**
- HTTP/runtime errors: 4
- Total runtime: 41.0 seconds

## Category results

| Category | Score | Passed | Cases | Errors |
|---|---:|---:|---:|---:|
| conversation_continuity | 60.0% | 6 | 10 | 4 |

## Failed or weak cases

- `corrected_number` (conversation_continuity): 0.0% — contains a valid idea
- `two_people` (conversation_continuity): 0.0% — contains a valid idea
- `followup_reason` (conversation_continuity): 0.0% — contains a valid idea
- `relationship_followup` (conversation_continuity): 0.0% — contains a valid idea

## Interpretation limits

- This bank is a bounded engineering regression suite, not an IQ test.
- Deterministic keyword and format rubrics can miss some semantically correct answers.
- Passing does not prove correctness on questions outside the tested behaviors.
- Evaluation turns cannot write long-term memory; session continuity is temporary.
