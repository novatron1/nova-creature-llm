"""Provider-independent local knowledge ingestion and hybrid retrieval."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Iterable, Protocol
import uuid


RAG_SCHEMA_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize(text: str) -> str:
    value = str(text or "").replace("\x00", " ")
    value = re.sub(r"\r\n?", "\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


class EmbeddingProvider(Protocol):
    provider_id: str
    model_id: str

    def embed(self, inputs: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class RAGPassage:
    source_id: str
    document_id: str
    document_title: str
    author: str | None
    publication_date: str | None
    ingestion_date: str
    source_location: str
    section_heading: str
    chunk_number: int
    text: str
    trust_level: str
    freshness_status: str
    score: float
    lexical_score: float = 0.0
    vector_score: float = 0.0
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def citation(self) -> str:
        return f"[{self.source_id}:{self.chunk_number}]"


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    passages: tuple[RAGPassage, ...]
    status: str
    retrieval_mode: str
    schema_version: str = RAG_SCHEMA_VERSION

    def context(self) -> str:
        if not self.passages:
            return ""
        return "\n\n".join(
            (
                f"{passage.citation} {passage.document_title}"
                + (f" — {passage.section_heading}" if passage.section_heading else "")
                + f"\n{passage.text}\nSource: {passage.source_location}"
            )
            for passage in self.passages
        )

    def safe_trace(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "retrieval_mode": self.retrieval_mode,
            "passage_count": len(self.passages),
            "sources": [
                {
                    "source_id": item.source_id,
                    "document_id": item.document_id,
                    "chunk_number": item.chunk_number,
                    "trust_level": item.trust_level,
                    "freshness_status": item.freshness_status,
                    "score": round(item.score, 4),
                }
                for item in self.passages
            ],
            "schema_version": self.schema_version,
            "content_logged": False,
        }


class NovaRAG:
    def __init__(
        self,
        database: str | Path = "data/nova_knowledge.db",
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_provider = embedding_provider
        self._lock = RLock()
        self._connection = sqlite3.connect(str(self.path), timeout=10, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rag_documents (
                    document_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    publication_date TEXT,
                    ingestion_date TEXT NOT NULL,
                    source_location TEXT NOT NULL,
                    trust_level TEXT NOT NULL,
                    freshness_status TEXT NOT NULL,
                    version_hash TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_number INTEGER NOT NULL,
                    section_heading TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding_json TEXT,
                    embedding_provider TEXT,
                    embedding_model TEXT,
                    FOREIGN KEY(document_id) REFERENCES rag_documents(document_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_document_version
                    ON rag_documents(source_id, version_hash);
                CREATE INDEX IF NOT EXISTS idx_rag_chunk_document
                    ON rag_chunks(document_id, chunk_number);
                CREATE VIRTUAL TABLE IF NOT EXISTS rag_fts USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    title,
                    section_heading,
                    text
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _split(text: str, *, target_chars: int = 1200, overlap_chars: int = 180) -> list[tuple[str, str]]:
        heading = ""
        units: list[tuple[str, str]] = []
        for block in re.split(r"\n\s*\n", _normalize(text)):
            block = block.strip()
            if not block:
                continue
            lines = block.splitlines()
            first_line = lines[0].strip()
            if re.match(r"^#{1,6}\s+", first_line):
                heading = re.sub(r"^#{1,6}\s+", "", first_line).strip()
                block = "\n".join(lines[1:]).strip()
                if not block:
                    continue
            elif len(lines) == 1 and re.match(r"^[A-Z][A-Z0-9 :/&-]{4,80}$", first_line):
                heading = first_line
                continue
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", block.replace("\n", " "))
            for sentence in sentences:
                sentence = sentence.strip()
                if sentence:
                    units.append((heading, sentence))

        chunks: list[tuple[str, str]] = []
        current_heading = ""
        current = ""
        for unit_heading, sentence in units:
            if current and len(current) + len(sentence) + 1 > target_chars:
                chunks.append((current_heading, current.strip()))
                overlap = current[-overlap_chars:].lstrip()
                current = overlap
            if unit_heading:
                current_heading = unit_heading
            current = (current + " " + sentence).strip()
        if current:
            chunks.append((current_heading, current))
        return chunks

    def ingest_text(
        self,
        text: str,
        *,
        source_id: str,
        title: str,
        author: str | None = None,
        publication_date: str | None = None,
        source_location: str = "local",
        trust_level: str = "unverified",
        freshness_status: str = "unknown",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = _normalize(text)
        if not normalized:
            raise ValueError("RAG source text cannot be empty.")
        version_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        with self._lock:
            existing = self._connection.execute(
                "SELECT document_id FROM rag_documents WHERE source_id=? AND version_hash=?",
                (source_id, version_hash),
            ).fetchone()
        if existing:
            with self._lock:
                chunk_count = int(
                    self._connection.execute(
                        "SELECT COUNT(*) FROM rag_chunks WHERE document_id=?",
                        (existing["document_id"],),
                    ).fetchone()[0]
                )
            if chunk_count:
                return {
                    "document_id": existing["document_id"],
                    "source_id": source_id,
                    "version_hash": version_hash,
                    "deduplicated": True,
                    "chunks": chunk_count,
                }
            # Repair an incomplete prior ingestion transaction or an older
            # splitter bug instead of permanently treating it as a valid copy.
            with self._lock, self._connection:
                self._connection.execute(
                    "DELETE FROM rag_fts WHERE document_id=?",
                    (existing["document_id"],),
                )
                self._connection.execute(
                    "DELETE FROM rag_documents WHERE document_id=?",
                    (existing["document_id"],),
                )

        chunks = self._split(normalized)
        embeddings: list[list[float]] = []
        if self.embedding_provider and chunks:
            embeddings = self.embedding_provider.embed([chunk for _, chunk in chunks])
            if len(embeddings) != len(chunks):
                raise ValueError("Embedding provider returned the wrong number of vectors.")
        document_id = "doc_" + uuid.uuid4().hex
        ingestion_date = _now()
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE rag_documents SET active=0 WHERE source_id=?",
                (source_id,),
            )
            self._connection.execute(
                """
                INSERT INTO rag_documents(
                    document_id, source_id, title, author, publication_date,
                    ingestion_date, source_location, trust_level, freshness_status,
                    version_hash, metadata_json, active
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (
                    document_id, source_id, title, author, publication_date,
                    ingestion_date, source_location, trust_level, freshness_status,
                    version_hash, json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            for index, (section, chunk_text) in enumerate(chunks):
                chunk_id = "chunk_" + uuid.uuid4().hex
                vector = embeddings[index] if embeddings else None
                self._connection.execute(
                    """
                    INSERT INTO rag_chunks(
                        chunk_id, document_id, chunk_number, section_heading,
                        text, embedding_json, embedding_provider, embedding_model
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        chunk_id, document_id, index, section, chunk_text,
                        json.dumps(vector) if vector is not None else None,
                        getattr(self.embedding_provider, "provider_id", None),
                        getattr(self.embedding_provider, "model_id", None),
                    ),
                )
                self._connection.execute(
                    "INSERT INTO rag_fts(chunk_id, document_id, title, section_heading, text) VALUES(?,?,?,?,?)",
                    (chunk_id, document_id, title, section, chunk_text),
                )
        return {
            "document_id": document_id,
            "source_id": source_id,
            "version_hash": version_hash,
            "deduplicated": False,
            "chunks": len(chunks),
            "embedding_provider": getattr(self.embedding_provider, "provider_id", None),
        }

    def _lexical(self, query: str, limit: int) -> list[tuple[str, float]]:
        tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 1]
        if not tokens:
            return []
        expression = " OR ".join(f'"{token}"' for token in tokens[:16])
        try:
            rows = self._connection.execute(
                """
                SELECT chunk_id, bm25(rag_fts) AS rank
                FROM rag_fts
                WHERE rag_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (expression, max(1, limit)),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [
            (row["chunk_id"], 1.0 / (1.0 + max(0.0, float(row["rank"]) + 10.0)))
            for row in rows
        ]

    def _vectors(self, query: str, limit: int) -> list[tuple[str, float]]:
        if self.embedding_provider is None:
            return []
        query_vectors = self.embedding_provider.embed([query])
        if not query_vectors:
            return []
        query_vector = query_vectors[0]
        rows = self._connection.execute(
            "SELECT chunk_id, embedding_json FROM rag_chunks WHERE embedding_json IS NOT NULL"
        ).fetchall()
        scored = [
            (row["chunk_id"], _cosine(query_vector, list(json.loads(row["embedding_json"]))))
            for row in rows
        ]
        return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]

    def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        trust_levels: Iterable[str] | None = None,
        source_id: str | None = None,
    ) -> RetrievalResult:
        limit = max(1, min(int(top_k), 50))
        with self._lock:
            lexical = self._lexical(query, limit * 4)
            vectors = self._vectors(query, limit * 4)
            fused: dict[str, dict[str, float]] = {}
            for rank, (chunk_id, score) in enumerate(lexical):
                entry = fused.setdefault(chunk_id, {"lexical": 0.0, "vector": 0.0, "rrf": 0.0})
                entry["lexical"] = score
                entry["rrf"] += 0.60 / (60 + rank + 1)
            for rank, (chunk_id, score) in enumerate(vectors):
                entry = fused.setdefault(chunk_id, {"lexical": 0.0, "vector": 0.0, "rrf": 0.0})
                entry["vector"] = score
                entry["rrf"] += 0.40 / (60 + rank + 1)

            passages: list[RAGPassage] = []
            allowed_trust = {str(item) for item in trust_levels or ()}
            for chunk_id, scores in sorted(
                fused.items(),
                key=lambda item: item[1]["rrf"],
                reverse=True,
            ):
                row = self._connection.execute(
                    """
                    SELECT c.*, d.source_id, d.title, d.author, d.publication_date,
                        d.ingestion_date, d.source_location, d.trust_level,
                        d.freshness_status, d.metadata_json
                    FROM rag_chunks c JOIN rag_documents d ON d.document_id=c.document_id
                    WHERE c.chunk_id=? AND d.active=1
                    """,
                    (chunk_id,),
                ).fetchone()
                if row is None:
                    continue
                if source_id and row["source_id"] != source_id:
                    continue
                if allowed_trust and row["trust_level"] not in allowed_trust:
                    continue
                trust_weight = {
                    "verified": 1.0,
                    "reviewed": 0.92,
                    "author_interpretation": 0.75,
                    "unverified": 0.65,
                }.get(row["trust_level"], 0.70)
                freshness_weight = 0.70 if row["freshness_status"] == "stale" else 1.0
                score = scores["rrf"] * trust_weight * freshness_weight
                passages.append(
                    RAGPassage(
                        source_id=row["source_id"],
                        document_id=row["document_id"],
                        document_title=row["title"],
                        author=row["author"],
                        publication_date=row["publication_date"],
                        ingestion_date=row["ingestion_date"],
                        source_location=row["source_location"],
                        section_heading=row["section_heading"],
                        chunk_number=int(row["chunk_number"]),
                        text=row["text"],
                        trust_level=row["trust_level"],
                        freshness_status=row["freshness_status"],
                        score=score,
                        lexical_score=scores["lexical"],
                        vector_score=scores["vector"],
                        metadata=json.loads(row["metadata_json"] or "{}"),
                    )
                )
                if len(passages) >= limit:
                    break
        mode = "hybrid" if vectors else "lexical_fts5"
        return RetrievalResult(
            query=query,
            passages=tuple(passages),
            status="answered" if passages else "insufficient_evidence",
            retrieval_mode=mode,
        )

    def health_check(self) -> dict[str, Any]:
        with self._lock:
            documents = self._connection.execute(
                "SELECT COUNT(*) FROM rag_documents WHERE active=1"
            ).fetchone()[0]
            chunks = self._connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
        return {
            "ok": True,
            "schema_version": RAG_SCHEMA_VERSION,
            "database": str(self.path),
            "active_documents": int(documents),
            "chunks": int(chunks),
            "fts5": True,
            "vector_enabled": self.embedding_provider is not None,
        }


_DEFAULT_RAG: NovaRAG | None = None
_DEFAULT_LOCK = RLock()


def get_default_rag(database: str | Path | None = None) -> NovaRAG:
    global _DEFAULT_RAG
    if database is not None:
        return NovaRAG(database)
    with _DEFAULT_LOCK:
        if _DEFAULT_RAG is None:
            root = Path(__file__).resolve().parents[1]
            configured = Path(os.environ.get("NOVA_RAG_DATABASE", "data/nova_knowledge.db"))
            if not configured.is_absolute():
                configured = root / configured
            _DEFAULT_RAG = NovaRAG(configured)
        return _DEFAULT_RAG


def ingest_ai_anatomy_record(
    rag: NovaRAG | None = None,
    *,
    record_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    path = Path(record_path) if record_path else root / "data" / "knowledge" / "anatomy_of_ai_field_guide_2026.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    claim_lines = []
    for claim in record["claims"]:
        claim_lines.append(
            f"## {claim['label']}\n{claim['text']}\nAssessment: {claim['assessment']}"
        )
    return (rag or get_default_rag()).ingest_text(
        "\n\n".join(claim_lines),
        source_id=record["source_id"],
        title=record["title"],
        author=record["author"],
        publication_date=record["publication_date"],
        source_location=str(path),
        trust_level="reviewed",
        freshness_status="time_sensitive_sections_flagged",
        metadata={
            "record_type": "reviewed_summary_with_corrections",
            "original_article_not_treated_as_fully_verified": True,
            "proprietary_leaked_code_ingested": False,
        },
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Nova local RAG ingestion and search")
    subparsers = parser.add_subparsers(dest="command", required=True)
    article = subparsers.add_parser("ingest-ai-anatomy", help="Ingest Nova's reviewed article record")
    article.add_argument("--database", default="data/nova_knowledge.db")
    ingest = subparsers.add_parser("ingest", help="Ingest a UTF-8 text/Markdown file")
    ingest.add_argument("path")
    ingest.add_argument("--source-id", required=True)
    ingest.add_argument("--title", required=True)
    ingest.add_argument("--author")
    ingest.add_argument("--publication-date")
    ingest.add_argument("--database", default="data/nova_knowledge.db")
    search = subparsers.add_parser("search", help="Search the local Nova knowledge store")
    search.add_argument("query")
    search.add_argument("--database", default="data/nova_knowledge.db")
    args = parser.parse_args()
    rag = NovaRAG(args.database)
    if args.command == "ingest-ai-anatomy":
        result = ingest_ai_anatomy_record(rag)
    elif args.command == "ingest":
        source = Path(args.path)
        result = rag.ingest_text(
            source.read_text(encoding="utf-8"),
            source_id=args.source_id,
            title=args.title,
            author=args.author,
            publication_date=args.publication_date,
            source_location=str(source.resolve()),
        )
    else:
        result = rag.search(args.query).safe_trace()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
