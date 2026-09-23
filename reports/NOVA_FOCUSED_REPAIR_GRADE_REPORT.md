# Nova Focused-Repair Adapter — Live Grade-Band Report

Date: July 24, 2026  
Adapter: `nova-qwen2-5-1-5b-focused-repair-20260723`  
Base model: `Qwen/Qwen2.5-1.5B-Instruct`

## Result

The raw focused-repair adapter scored **76.1% overall (C)** across 15 local
curriculum and practical-reasoning questions.

| Test band | Score | Demonstrated at 75% threshold |
|---|---:|---:|
| Elementary, grades 3–5 | 100.0% | Yes |
| Middle school, grades 6–8 | 83.3% | Yes |
| High school, grades 9–12 | 88.9% | Yes |
| Introductory college | 83.3% | Yes |
| Advanced practical reasoning | 25.0% | No |

On this small probe, the highest demonstrated band was **introductory college**.
This is not an IQ score, standardized exam, or claim of complete college-level
mastery.

## Strong results

- Basic arithmetic, reading inference, and the water cycle
- Fractions and controlled-experiment concepts
- Algebraic equation solving
- Correlation-versus-causation reasoning
- Basic calculus differentiation
- Introductory Python list filtering

## Partial results

- The notebook-ratio answer was numerically correct, but its written
  calculation was wrong.
- The dice-probability answer identified all 5 favorable outcomes and 36 total
  outcomes, but stopped before printing the final `5/36` fraction.
- The kinetic-energy answer correctly returned `9 J`, but did not show the
  requested substitution.

## Weak results

- It failed a valid existential syllogism and answered the formal-logic
  question incorrectly.
- Its production-incident plan did not inspect logs/traces or propose a safe
  rollback/canary response.
- Its conflicting-source answer acknowledged uncertainty but did not recommend
  primary sources, date checks, or independent corroboration.

## Test integrity

- Raw adapter generation: yes
- Nova memory: disabled
- Nova RAG: disabled
- Nova tools: disabled
- Internet: disabled
- Nova answer replacement: disabled
- Provider fallback: 0
- Generation errors: 0
- Runtime: 307.625 seconds

The initial deterministic rubric was manually audited against every generated
answer. Three rules were corrected where they were stricter than the prompts.
The saved model outputs were not changed or regenerated during rescoring.

## Interpretation

The adapter is solid on school-style factual, mathematical, and introductory
coding tasks. It should not be trusted alone for formal logic, production
operations, or evidence verification. Nova's verifier, tools, RAG, and larger
model escalation should remain active for those tasks.

The most useful next training set would target:

1. Formal logic and quantifier reasoning.
2. Step-complete probability and physics solutions.
3. Evidence-based debugging and rollback planning.
4. Source ranking, freshness checks, and explicit uncertainty.
