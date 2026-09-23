# Nova Companion 768D concept upgrade — 2026-08-22

## Result

The Nova Companion 768D Kaggle run was upgraded with an append-only concept vocabulary migration and a dictionary/concept consolidation pass.

- Base vocabulary: 5,000 tokens.
- Expanded vocabulary: 5,750 tokens.
- Original concept-corpus unknown IDs: 2,177.
- Unknown IDs after migration: 0.
- Unknown examples after migration: 0.
- Base checkpoint: preserved; migration copies the original embedding and output rows into the expanded model.

## Kaggle artifacts

The first expanded-vocabulary run completed at:

`/kaggle/working/companion_768d_vocab_expand_2000/final.pt`

The canonical consolidation run completed at:

`/kaggle/working/companion_768d_canonical_expanded_900/final.pt`

The focused planet-relation repair reached step 500. Its verified best checkpoint is:

`/kaggle/working/companion_768d_planet_repair_500/best.pt`

That checkpoint is step 250 because Kaggle failed while writing the final step-500 archive. The best checkpoint itself is intact and was validated from a clean kernel.

## Clean validation

The verified best checkpoint answered these prompts correctly, with zero original unknown tokens in each prompt:

- Gravity is a force that pulls objects with mass.
- A planet is related to an orbit because it follows an orbit around a star.
- Density is mass divided by volume.
- If mass doubles while radius stays fixed, surface gravity doubles.
- If a planet has twice the mass and the same radius, surface gravity is approximately twice as strong.

## Local implementation

The reproducible bundle is:

`artifacts/companion_768d_unk_rescue_bundle.zip`

The targeted regression suite passes: **20 tests passed**.

The remaining limitation is that a 5,750-token vocabulary removes unknowns for the covered concept corpus and tested prompts; it cannot guarantee that every arbitrary future word is represented. Generated text should also be truncated at the model's end-of-text token so post-answer continuation does not get mistaken for the answer.
