# Nova Companion 768D dictionary upgrade

Status: verified candidate. The original base checkpoint remains unchanged.

## Recipe

- Focused dictionary/concept corpus with repeated question-answer and reasoning views.
- Full-sequence loss, actual end-of-text boundaries, concept-only continuation.
- 2,000-step base continuation followed by 900-step canonical consolidation.
- Consolidation learning rate: `1e-5`.

## Kaggle candidate

- Base: `/kaggle/input/datasets/novatron513/nova-companion-768d-base-output/companion_768d/final.pt`
- Candidate: `/kaggle/working/companion_768d_canonical_consolidation/final.pt`
- Manifest: `/kaggle/working/companion_768d_canonical_consolidation/promotion_manifest.json`

## Deterministic verification

The candidate returned the intended answer for density, gravity, planet-to-orbit, both surface-gravity doubling phrasings, and a density paraphrase. The original base was not overwritten.
