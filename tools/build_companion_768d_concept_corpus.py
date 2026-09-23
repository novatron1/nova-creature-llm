from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICTIONARY = ROOT / "data" / "builtin_word_dictionary.json"
DEFAULT_RELATIONS = ROOT / "data" / "companion_768d_concept_relations.json"
TOKEN_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?|[^\w\s]", re.UNICODE)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "concept"


def _record(concept: str, kind: str, text: str, *, source: str) -> dict[str, Any]:
    return {
        "id": f"{_slug(concept)}:{kind}:{abs(hash((concept, kind, text))) % 10_000_000}",
        "concept": concept,
        "kind": kind,
        "source": source,
        "text": _clean(text),
    }


def _stable_record_id(concept: str, kind: str, text: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{concept}\0{kind}\0{text}".encode("utf-8")).hexdigest()[:12]
    return f"{_slug(concept)}:{kind}:{digest}"


def _make_record(concept: str, kind: str, text: str, *, source: str) -> dict[str, Any]:
    row = _record(concept, kind, text, source=source)
    row["id"] = _stable_record_id(concept, kind, row["text"])
    return row


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_relations(path: Path) -> list[dict[str, Any]]:
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise ValueError("Relations file must contain a JSON list.")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"Relation {index} must be an object.")
        source = _clean(row.get("source"))
        relation = _clean(row.get("relation"))
        if not source or not relation:
            raise ValueError(f"Relation {index} needs source and relation.")
        rows.append(dict(row, source=source, relation=relation))
    return rows


def _relation_text(row: dict[str, Any]) -> tuple[str, str, str]:
    source = _clean(row["source"])
    relation = _clean(row["relation"])
    question = _clean(row.get("question"))
    answer = _clean(row.get("answer"))
    if question and answer:
        return "reasoning", f"Question: {question} Answer: {answer}", source

    target = _clean(row.get("target"))
    statement = _clean(row.get("statement"))
    if not target or not statement:
        raise ValueError(f"Relation {source}/{relation} needs target/statement or question/answer.")
    text = (
        f"Concept relation: {source} {relation.replace('_', ' ')} {target}. "
        f"Statement: {statement}"
    )
    return "relation", text, source


def build_concept_records(dictionary_path: Path, relations_path: Path) -> list[dict[str, Any]]:
    dictionary = _load_json(dictionary_path)
    if not isinstance(dictionary, dict):
        raise ValueError("Dictionary file must contain an object mapping concepts to definitions.")

    rows: list[dict[str, Any]] = []
    for concept, definition in sorted(dictionary.items(), key=lambda item: str(item[0]).lower()):
        concept_text = _clean(concept)
        definition_text = _clean(definition)
        if not concept_text or not definition_text:
            continue
        rows.extend(
            [
                _make_record(
                    concept_text,
                    "definition",
                    f"Concept: {concept_text}. Definition: {definition_text}",
                    source="builtin_word_dictionary",
                ),
                _make_record(
                    concept_text,
                    "question_answer",
                    f"Question: What is {concept_text}? Answer: {definition_text}",
                    source="builtin_word_dictionary",
                ),
                _make_record(
                    concept_text,
                    "explanation",
                    f"Explain {concept_text} simply. {definition_text}",
                    source="builtin_word_dictionary",
                ),
            ]
        )

    for relation in _load_relations(relations_path):
        kind, text, concept = _relation_text(relation)
        rows.append(_make_record(concept, kind, text, source="curated_concept_relations"))
    return rows


def build_weighted_focus_records(
    records: list[dict[str, Any]],
    *,
    question_answer_repeats: int = 4,
    reasoning_repeats: int = 2,
    definition_repeats: int = 1,
    explanation_repeats: int = 1,
    relation_repeats: int = 1,
) -> list[dict[str, Any]]:
    """Repeat answer-bearing views without changing their source text."""
    repeats = {
        "question_answer": question_answer_repeats,
        "reasoning": reasoning_repeats,
        "definition": definition_repeats,
        "explanation": explanation_repeats,
        "relation": relation_repeats,
    }
    if any(value <= 0 for value in repeats.values()):
        raise ValueError("All focus repeat counts must be positive")

    focused: list[dict[str, Any]] = []
    for row in records:
        repeat = repeats.get(str(row.get("kind")), 1)
        for copy_index in range(repeat):
            clone = dict(row)
            clone["id"] = f"{row['id']}:focus{copy_index}"
            clone["focus_copy"] = copy_index
            focused.append(clone)
    return focused


def _clone(row: dict[str, Any], *, source: str | None = None) -> dict[str, Any]:
    clone = dict(row)
    if source:
        clone["source"] = source
    return clone


def mix_replay_records(
    concept_records: list[dict[str, Any]],
    replay_records: list[dict[str, Any]],
    *,
    concept_ratio: float,
    seed: int,
) -> list[dict[str, Any]]:
    if not 0 < concept_ratio <= 1:
        raise ValueError("concept_ratio must be greater than 0 and at most 1")
    if not concept_records:
        raise ValueError("At least one concept record is required")

    rng = random.Random(seed)
    mixed = [_clone(row, source="concept_upgrade") for row in concept_records]
    if replay_records and concept_ratio < 1:
        replay_count = max(1, round(len(mixed) * (1 - concept_ratio) / concept_ratio))
        selected: list[dict[str, Any]] = []
        for index in range(replay_count):
            selected.append(_clone(replay_records[index % len(replay_records)], source="replay"))
        rng.shuffle(selected)
        mixed.extend(selected)
    rng.shuffle(mixed)
    return mixed


def split_records_by_concept(
    records: list[dict[str, Any]], *, validation_fraction: float, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[_clean(row.get("concept"))].append(row)
    concepts = sorted(grouped)
    if len(concepts) < 2:
        return list(records), []
    rng = random.Random(seed)
    rng.shuffle(concepts)
    validation_count = max(1, round(len(concepts) * validation_fraction))
    validation_concepts = set(concepts[:validation_count])
    train = [row for row in records if _clean(row.get("concept")) not in validation_concepts]
    validation = [row for row in records if _clean(row.get("concept")) in validation_concepts]
    return train, validation


def token_coverage(texts: Iterable[str], tokenizer_tokens: Iterable[str]) -> dict[str, Any]:
    vocabulary = {str(token) for token in tokenizer_tokens}
    total = 0
    unknown = 0
    unknown_types: set[str] = set()
    for text in texts:
        for token in TOKEN_PATTERN.findall(str(text)):
            total += 1
            if token not in vocabulary:
                unknown += 1
                unknown_types.add(token)
    return {
        "total_token_count": total,
        "unknown_token_count": unknown,
        "unknown_rate": unknown / total if total else 0.0,
        "unknown_token_types": sorted(unknown_types),
    }


def _read_replay(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        raw = json.loads(line)
        text = _clean(raw.get("text") or raw.get("output") or raw.get("nova"))
        if text:
            rows.append(
                {
                    "id": f"replay:{path.stem}:{index}",
                    "concept": "replay",
                    "kind": "replay",
                    "source": str(path),
                    "text": text,
                }
            )
    return rows


def build_artifact(
    *,
    dictionary_path: Path,
    relations_path: Path,
    output_dir: Path,
    replay_paths: list[Path],
    concept_ratio: float,
    validation_fraction: float,
    seed: int,
    question_answer_repeats: int = 1,
    reasoning_repeats: int = 1,
) -> dict[str, Any]:
    concept_records = build_concept_records(dictionary_path, relations_path)
    concept_train, concept_validation = split_records_by_concept(
        concept_records, validation_fraction=validation_fraction, seed=seed
    )
    replay_records = [row for path in replay_paths for row in _read_replay(path)]
    replay_train, replay_validation = split_records_by_concept(
        replay_records, validation_fraction=validation_fraction, seed=seed + 1
    ) if replay_records else ([], [])
    focused_concept_train = build_weighted_focus_records(
        concept_train,
        question_answer_repeats=question_answer_repeats,
        reasoning_repeats=reasoning_repeats,
    )
    train = mix_replay_records(
        focused_concept_train, replay_train, concept_ratio=concept_ratio, seed=seed
    )
    validation = mix_replay_records(
        concept_validation or concept_train[:1],
        replay_validation,
        concept_ratio=concept_ratio,
        seed=seed + 2,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train.jsonl", train), ("validation.jsonl", validation)):
        (output_dir / name).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    eval_rows = [row for row in validation if row.get("source") == "concept_upgrade"]
    (output_dir / "concept_eval.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in eval_rows),
        encoding="utf-8",
    )
    manifest = {
        "version": "companion_768d_concept_upgrade_v1",
        "dictionary_path": str(dictionary_path),
        "relations_path": str(relations_path),
        "concept_record_count": len(concept_records),
        "focused_concept_train_count": len(focused_concept_train),
        "replay_record_count": len(replay_records),
        "train_count": len(train),
        "validation_count": len(validation),
        "concept_eval_count": len(eval_rows),
        "concept_ratio": concept_ratio,
        "validation_fraction": validation_fraction,
        "seed": seed,
        "tokenizer_policy": "frozen_5000_tokenizer_with_explicit_coverage_audit",
        "focus_weights": {
            "question_answer_repeats": question_answer_repeats,
            "reasoning_repeats": reasoning_repeats,
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Nova Companion 768d concept corpus")
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    parser.add_argument("--relations", type=Path, default=DEFAULT_RELATIONS)
    parser.add_argument("--replay", type=Path, action="append", default=[])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "companion_768d_dictionary_upgrade",
    )
    parser.add_argument("--concept-ratio", type=float, default=0.75)
    parser.add_argument("--validation-fraction", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=7682026)
    parser.add_argument("--question-answer-repeats", type=int, default=1)
    parser.add_argument("--reasoning-repeats", type=int, default=1)
    args = parser.parse_args()
    manifest = build_artifact(
        dictionary_path=args.dictionary,
        relations_path=args.relations,
        output_dir=args.output_dir,
        replay_paths=args.replay,
        concept_ratio=args.concept_ratio,
        validation_fraction=args.validation_fraction,
        seed=args.seed,
        question_answer_repeats=args.question_answer_repeats,
        reasoning_repeats=args.reasoning_repeats,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
