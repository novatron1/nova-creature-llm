# Nova Adversarial Evaluation

- Bank: `nova-adversarial-1.0`
- Cases: 10
- Passed cases: 0
- Overall rubric score: **5.0%**
- HTTP/runtime errors: 3
- Total runtime: 92.2 seconds

## Category results

| Category | Score | Passed | Cases | Errors |
|---|---:|---:|---:|---:|
| planning_verification | 5.0% | 0 | 10 | 3 |

## Failed or weak cases

- `deployment_latency` (planning_verification): 0.0% — contains a valid idea
- `controlled_experiment` (planning_verification): 0.0% — contains a valid idea
- `bug_reproduction` (planning_verification): 0.0% — contains a valid idea
- `database_slow` (planning_verification): 50.0% — multiple diagnostics
- `rollback_plan` (planning_verification): 0.0% — contains a valid idea
- `migration_plan` (planning_verification): 0.0% — contains a valid idea
- `incident_priority` (planning_verification): 0.0% — contains a valid idea
- `ambiguous_requirement` (planning_verification): 0.0% — contains a valid idea
- `model_comparison` (planning_verification): 0.0% — contains a valid idea
- `failure_claim` (planning_verification): 0.0% — contains a valid idea

## Interpretation limits

- This bank is a bounded engineering regression suite, not an IQ test.
- Deterministic keyword and format rubrics can miss some semantically correct answers.
- Passing does not prove correctness on questions outside the tested behaviors.
- Evaluation turns cannot write long-term memory; session continuity is temporary.
