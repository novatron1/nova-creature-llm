# Nova Companion 768d Concept Upgrade

## Goal

Add a dictionary-and-concept continuation stage for the Nova Companion 768d
model trained by `nova-companion-768d-resumable-training.py`.

## Scope

The upgrade keeps the current 768d hierarchical model and its 5,000-token
tokenizer compatible with the base checkpoint. It builds a deterministic text
corpus from the approved local dictionary plus a small curated relationship
set, mixes concept lessons with replay from the existing companion corpus, and
runs as a separate resumable continuation job.

The first pass will not expand the vocabulary. Every concept token that is not
representable by the frozen tokenizer is reported; it must not be silently
treated as useful knowledge. A later tokenizer migration is a separate
experiment.

## Data views

Each concept can produce several text views: definition, category, properties,
related concepts, example, cause/effect, part/whole, contrast, and a direct
question/answer view. Relationship and reasoning rows are curated and
deterministic rather than inferred from a definition by the builder.

## Training

The continuation runner loads the base model weights and tokenizer state from a
checkpoint, resets the optimizer and learning-rate schedule, and writes to a
new run directory. It uses a low learning rate, a bounded step count, and a
replay mix so dictionary learning does not erase the existing companion
behavior. The focused pass masks prompt/header tokens from the loss and trains
primarily on answer, definition, relation, and reasoning spans. It preserves
atomic checkpoints and stop-signal handling. Each document is terminated with
the tokenizer's actual EOT vocabulary ID, and inference output is truncated at
the first EOT marker.

## Verification

Local tests cover corpus generation, deterministic splits, replay mixing,
unknown-token reporting, answer-mask alignment, checkpoint/tokenizer
compatibility guards, and the Kaggle command manifest. The generated artifact
includes a concept evaluation set and a regression set; sealed/base evaluation
data remains evaluation-only.
