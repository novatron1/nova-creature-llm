# Nova Companion 768d Unknown-Token Rescue

## Goal

Reduce `<unk>` exposure during dictionary/concept continuation without
changing the 768d model's vocabulary size or invalidating the original
checkpoint.

## Design

The continuation runner uses two compatible layers. First, it performs a
tokenizer-boundary rescue using exact known character or subword pieces. The
live checkpoint audit showed that the current tokenizer has only a narrow set
of character pieces, so that layer cannot cover arbitrary words.

For missing words found in the approved concept corpus, the runner therefore
performs a controlled vocabulary migration. It appends deterministic missing
token strings to the restored tokenizer, increases the model configuration's
vocabulary size, creates a new model, copies every old parameter exactly, and
leaves only the new embedding/output rows at their normal initialization. The
new rows are then trained by the concept continuation. No old token ID is
renumbered.

The same helper is used for coverage auditing and sequence construction so the
reported unknown rate matches the actual training input. A strict mode fails
the run when unresolved unknowns remain; a fallback mode keeps the rows but
reports the unresolved examples. The base and canonical checkpoints remain
untouched.

## Compatibility and limits

- The original checkpoint vocabulary and weights remain exactly unchanged.
- The migrated candidate records its expanded vocabulary size and source
  checkpoint in its manifest.
- Tokenizer state is restored from the checkpoint before rescue-map discovery.
- Only concept-corpus tokens are added in this experiment; arbitrary user words
  outside that set may still be unknown.
- The migration fails closed if any non-vocabulary-shaped model parameter would
  need a shape change.

## Verification

Tests will cover greedy rescue, unresolved reporting, tokenizer extension,
exact old-row preservation, and runner wiring. The Kaggle run will report
before/after unknown counts, expanded vocabulary size, and the canonical
concept suite.
