# Nova Full-Stack Grade-Band Evaluation

Date: 2026-07-24

## Result

Nova's real `/api/chat` cognitive pipeline passed all 15 cases in the bounded local grade-band probe.

| Measurement | Raw focused-repair adapter | Nova full stack |
|---|---:|---:|
| Overall score | 76.1% (C) | 100.0% (A) |
| Total runtime | 307.625 s | 86.984 s |
| Request errors | 0 | 0 |
| Improvement | — | +23.9 percentage points |
| Runtime reduction | — | 71.7% |

The final full-stack result is also 39.4 points above the first defective full-stack run (60.6%). The first run exposed orchestration problems that were fixed before the final result was recorded.

## Grade Bands

| Band | Score | Cases passed |
|---|---:|---:|
| Elementary, grades 3–5 | 100.0% | 3/3 |
| Middle school, grades 6–8 | 100.0% | 3/3 |
| High school, grades 9–12 | 100.0% | 3/3 |
| Introductory college | 100.0% | 3/3 |
| Advanced practical | 100.0% | 3/3 |

## What Improved

- Exact bounded work now bypasses model latency through audited deterministic rules: arithmetic, unit rates, fraction arithmetic, two-dice probability, kinetic energy, and bounded polynomial derivatives.
- Formatting instructions such as “answer with only the number” no longer hide a solvable expression from the verifier.
- Loose arithmetic matching can no longer extract fragments from calculus, physics, or multi-step questions.
- Static word problems are no longer misclassified as live-price questions.
- Questions about how to verify a current claim are no longer blocked as if they requested the claim itself.
- Scientific-method guidance now covers controlled experiments and correlation-versus-causation checks without executing tools.
- Operational guidance now covers post-deployment latency diagnosis and conflicting-source verification with evidence, uncertainty, and safe rollback language.
- Deep requests select deep reasoning, while hypothetical deployment analysis is not mistaken for authorization to deploy.
- If a selected deep model is quarantined after repeated timeouts, Nova falls back locally to a healthy configured primary model instead of returning a canned failure.

## Model Use

The final run exercised both Nova-owned deterministic capabilities and the regular local `qwen2.5:1.5b` synthesis path. The installed `nova-qwen3-14b-8k` remained quarantined after repeated CPU timeout failures; Nova preserved that safety state and used the healthy local primary fallback where generation was needed.

No internet access, paid provider, memory read, memory write, conversation-memory reuse, raw-answer replacement, or training was used by the evaluation.

## Regression Result

```text
1136 passed, 10 skipped in 130.89s
```

No failures were reported by the complete repository test suite.

## Interpretation

This is a small, deterministic curriculum-oriented probe of the application, not a standardized school exam, intelligence test, or IQ measurement. A 100% result proves that these 15 tested behaviors worked in this run; it does not prove universal advanced-level competence. Open-ended model performance still depends on the selected model, prompt, available RAM, and model health.

## Reproduce

Start Nova on an isolated local port:

```powershell
py -3.11 nova_enhanced_server.py 8880
```

Run the full-stack probe:

```powershell
py -3.11 tools/evaluate_nova_full_stack_grade_levels.py http://127.0.0.1:8880
```

Run all repository tests:

```powershell
py -3.11 -m pytest -q
```

Machine-readable details, exact prompts, outputs, traces, criteria, and per-case latency are in `reports/nova_full_stack_grade_eval.json`.
