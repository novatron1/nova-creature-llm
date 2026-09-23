# Nova Adversarial Evaluation

- Bank: `nova-adversarial-1.0`
- Cases: 10
- Passed cases: 2
- Overall rubric score: **20.0%**
- HTTP/runtime errors: 2
- Total runtime: 62.7 seconds

## Category results

| Category | Score | Passed | Cases | Errors |
|---|---:|---:|---:|---:|
| conversation_continuity | 20.0% | 2 | 10 | 2 |

## Failed or weak cases

- `codeword` (conversation_continuity): 0.0% — exact answer
- `favorite_color` (conversation_continuity): 0.0% — contains a valid idea
- `corrected_number` (conversation_continuity): 0.0% — contains a valid idea
- `two_people` (conversation_continuity): 0.0% — contains a valid idea
- `project_goal` (conversation_continuity): 0.0% — contains required ideas
- `pronoun_reference` (conversation_continuity): 0.0% — contains required ideas
- `followup_reason` (conversation_continuity): 0.0% — contains a valid idea
- `latest_preference` (conversation_continuity): 0.0% — contains a valid idea

## Interpretation limits

- This bank is a bounded engineering regression suite, not an IQ test.
- Deterministic keyword and format rubrics can miss some semantically correct answers.
- Passing does not prove correctness on questions outside the tested behaviors.
- Evaluation turns cannot write long-term memory; session continuity is temporary.
