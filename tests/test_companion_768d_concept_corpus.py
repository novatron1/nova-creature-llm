import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.build_companion_768d_concept_corpus import (
    build_concept_records,
    build_weighted_focus_records,
    mix_replay_records,
    split_records_by_concept,
    token_coverage,
)


def test_dictionary_entry_gets_multiple_concept_views(tmp_path: Path):
    dictionary_path = tmp_path / "dictionary.json"
    relations_path = tmp_path / "relations.json"
    dictionary_path.write_text(
        json.dumps({"gravity": "Gravity pulls masses toward one another."}),
        encoding="utf-8",
    )
    relations_path.write_text(
        json.dumps(
            [
                {
                    "source": "gravity",
                    "relation": "depends_on",
                    "target": "mass",
                    "statement": "More mass produces stronger gravitational attraction.",
                }
            ]
        ),
        encoding="utf-8",
    )

    rows = build_concept_records(dictionary_path, relations_path)

    kinds = {row["kind"] for row in rows}
    assert {"definition", "question_answer", "relation"} <= kinds
    assert all(row["text"].strip() for row in rows)
    assert all(row["concept"] == "gravity" for row in rows)


def test_split_keeps_one_concept_out_of_both_splits():
    rows = [
        {"id": "a1", "concept": "alpha", "text": "alpha one"},
        {"id": "a2", "concept": "alpha", "text": "alpha two"},
        {"id": "b1", "concept": "beta", "text": "beta one"},
        {"id": "b2", "concept": "beta", "text": "beta two"},
    ]

    train, validation = split_records_by_concept(rows, validation_fraction=0.5, seed=7)

    assert {row["concept"] for row in train}.isdisjoint(
        {row["concept"] for row in validation}
    )
    assert len(train) + len(validation) == len(rows)


def test_replay_mixing_is_deterministic_and_contains_both_sources():
    concepts = [{"id": f"c{i}", "concept": f"c{i}", "text": f"concept {i}"} for i in range(8)]
    replay = [{"id": f"r{i}", "concept": "replay", "text": f"replay {i}"} for i in range(8)]

    first = mix_replay_records(concepts, replay, concept_ratio=0.75, seed=11)
    second = mix_replay_records(concepts, replay, concept_ratio=0.75, seed=11)

    assert first == second
    assert any(row["id"].startswith("c") for row in first)
    assert any(row["id"].startswith("r") for row in first)


def test_token_coverage_reports_unknown_types_without_silently_dropping_them():
    report = token_coverage(
        ["gravity mass orbit", "gravity unknownword"],
        {"gravity", "mass", "orbit"},
    )

    assert report["unknown_token_types"] == ["unknownword"]
    assert report["unknown_token_count"] == 1
    assert report["unknown_rate"] > 0


def test_focus_records_repeat_answers_more_than_relationships_deterministically():
    rows = [
        {"id": "qa", "concept": "density", "kind": "question_answer", "text": "Question: What is density? Answer: mass per volume."},
        {"id": "reason", "concept": "density", "kind": "reasoning", "text": "Question: If mass doubles, density doubles."},
        {"id": "relation", "concept": "density", "kind": "relation", "text": "Concept relation: density depends on mass."},
    ]

    first = build_weighted_focus_records(rows, question_answer_repeats=4, reasoning_repeats=2)
    second = build_weighted_focus_records(rows, question_answer_repeats=4, reasoning_repeats=2)

    assert first == second
    assert [row["id"] for row in first].count("qa:focus0") == 1
    assert sum(row["id"].startswith("qa:focus") for row in first) == 4
    assert sum(row["id"].startswith("reason:focus") for row in first) == 2
    assert sum(row["id"].startswith("relation:focus") for row in first) == 1
