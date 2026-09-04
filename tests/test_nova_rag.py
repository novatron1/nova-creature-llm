from __future__ import annotations

import json
from pathlib import Path

from nova_rag import NovaRAG, ingest_ai_anatomy_record


class FakeEmbeddingProvider:
    provider_id = "fake"
    model_id = "fake-3d"

    def embed(self, inputs: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in inputs:
            lowered = text.lower()
            vectors.append(
                [
                    float(lowered.count("transformer")),
                    float(lowered.count("memory")),
                    float(lowered.count("video")),
                ]
            )
        return vectors


def test_ingest_search_and_citation_metadata(tmp_path: Path) -> None:
    rag = NovaRAG(tmp_path / "knowledge.db")
    result = rag.ingest_text(
        "# Architecture\n\nNova separates identity and memory from the replaceable model provider.",
        source_id="nova-architecture",
        title="Nova Architecture",
        author="Nova Project",
        publication_date="2026-07-23",
        source_location="docs/nova.md",
        trust_level="verified",
        freshness_status="current",
    )
    found = rag.search("replaceable model provider")

    assert result["chunks"] == 1
    assert found.status == "answered"
    assert found.passages[0].source_id == "nova-architecture"
    assert found.passages[0].document_title == "Nova Architecture"
    assert found.passages[0].author == "Nova Project"
    assert found.passages[0].source_location == "docs/nova.md"
    assert found.passages[0].citation.startswith("[nova-architecture:")
    assert "Source: docs/nova.md" in found.context()
    rag.close()


def test_document_versions_and_exact_duplicate_are_handled(tmp_path: Path) -> None:
    rag = NovaRAG(tmp_path / "knowledge.db")
    first = rag.ingest_text("First version about memory.", source_id="source", title="A")
    duplicate = rag.ingest_text("First version about memory.", source_id="source", title="A")
    second = rag.ingest_text("Second version about structured memory.", source_id="source", title="A")

    assert not first["deduplicated"]
    assert duplicate["deduplicated"]
    assert second["document_id"] != first["document_id"]
    found = rag.search("structured memory", source_id="source")
    assert len(found.passages) == 1
    assert "Second version" in found.passages[0].text
    rag.close()


def test_hybrid_retrieval_uses_configured_embedding_provider(tmp_path: Path) -> None:
    rag = NovaRAG(tmp_path / "knowledge.db", embedding_provider=FakeEmbeddingProvider())
    rag.ingest_text(
        "Temporal attention makes long video clips expensive.",
        source_id="video",
        title="Video",
    )
    found = rag.search("video temporal representation")

    assert found.retrieval_mode == "hybrid"
    assert found.passages
    assert found.passages[0].vector_score > 0
    rag.close()


def test_missing_evidence_is_explicit(tmp_path: Path) -> None:
    rag = NovaRAG(tmp_path / "knowledge.db")
    rag.ingest_text("Only apples are discussed here.", source_id="fruit", title="Fruit")
    found = rag.search("quantum chromodynamics")

    assert found.status == "insufficient_evidence"
    assert found.passages == ()
    assert found.context() == ""
    rag.close()


def test_anatomy_record_contains_reviewed_corrections_and_no_leaked_code(tmp_path: Path) -> None:
    rag = NovaRAG(tmp_path / "knowledge.db")
    result = ingest_ai_anatomy_record(rag)
    found = rag.search("autoregressively forward pass", source_id="anatomy-ai-field-guide-2026-07-21")
    record_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "knowledge"
        / "anatomy_of_ai_field_guide_2026.json"
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))

    assert result["chunks"] >= 1
    assert found.passages
    assert any("autoregressively" in passage.text for passage in found.passages)
    assert len(record["claims"]) == 8
    assert record["proprietary_leaked_source_included"] is False
    allowed = {
        "verified_technical",
        "conceptual_simplification",
        "author_interpretation",
        "time_sensitive",
        "requires_external_verification",
    }
    assert all(claim["label"] in allowed for claim in record["claims"])
    rag.close()
