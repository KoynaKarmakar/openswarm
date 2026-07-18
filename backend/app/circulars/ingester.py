"""
Circular document ingestion — indexes IDBI policy circulars into the
`veritas_circulars` Qdrant collection.

Separate from `veritas_policies` (used for open-ended RAG retrieval) — this
collection is purpose-built for compliance gating: each point carries the
extracted rule blocks so the gate can do hard-rule evaluation without an LLM.

Called from app lifespan on startup. Idempotent: skips if already populated.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

from app.circulars.chunker import CircularChunk, load_all_circular_chunks

logger = logging.getLogger("veritas.circulars.ingest")

CIRCULAR_COLLECTION = "veritas_circulars"
VECTOR_SIZE = 384


class CircularVectorStore:
    """Thin Qdrant wrapper dedicated to the circulars collection."""

    def __init__(self, qdrant_client):
        # qdrant_client is a VeritasQdrantClient from app.rag.qdrant_client
        self._q = qdrant_client

    def _ensure_collection(self) -> None:
        try:
            self._q._client.get_collection(CIRCULAR_COLLECTION)
        except Exception:
            from qdrant_client.models import Distance, VectorParams
            self._q._client.create_collection(
                collection_name=CIRCULAR_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection: %s", CIRCULAR_COLLECTION)

    def _point_count(self) -> int:
        try:
            return self._q._client.count(CIRCULAR_COLLECTION).count
        except Exception:
            return 0

    def upsert_chunk(self, chunk: CircularChunk) -> None:
        from qdrant_client.models import PointStruct
        vector = self._q.embed(chunk.text)
        payload = {
            "chunk_id": chunk.chunk_id,
            "policy_name": chunk.policy_name,
            "section": chunk.section,
            "text": chunk.text,
            "source_file": chunk.source_file,
            "rule_ids": chunk.rule_ids,
            "has_hard_rules": chunk.has_hard_rules,
            # Store rule blocks as JSON string so Qdrant payload handles nesting
            "rule_blocks_json": json.dumps(chunk.rule_blocks),
        }
        self._q._client.upsert(
            collection_name=CIRCULAR_COLLECTION,
            points=[
                PointStruct(
                    id=abs(hash(chunk.chunk_id)) % (2**63),
                    vector=vector,
                    payload=payload,
                )
            ],
        )

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Return top-k circular chunks most relevant to the query.
        Each result dict has keys matching CircularChunk fields + `score`.
        """
        vector = self._q.embed(query)
        try:
            results = self._q._client.search(
                collection_name=CIRCULAR_COLLECTION,
                query_vector=vector,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            logger.warning("Circular search failed: %s", exc)
            return []

        out = []
        for r in results:
            p = r.payload or {}
            rule_blocks = []
            raw_rb = p.get("rule_blocks_json", "[]")
            try:
                rule_blocks = json.loads(raw_rb)
            except Exception:
                pass
            out.append({
                "chunk_id": p.get("chunk_id", ""),
                "policy_name": p.get("policy_name", ""),
                "section": p.get("section", ""),
                "text": p.get("text", ""),
                "source_file": p.get("source_file", ""),
                "rule_ids": p.get("rule_ids", []),
                "has_hard_rules": p.get("has_hard_rules", False),
                "rule_blocks": rule_blocks,
                "score": float(r.score),
            })
        return out


def ingest_circulars(qdrant_client, force: bool = False) -> int:
    """
    Load circular chunks and upsert into Qdrant.
    Returns number of chunks ingested (0 if already populated).
    """
    store = CircularVectorStore(qdrant_client)
    store._ensure_collection()

    if not force and store._point_count() > 0:
        logger.info(
            "veritas_circulars already populated (%d points) — skipping ingestion",
            store._point_count(),
        )
        return 0

    chunks = load_all_circular_chunks()
    if not chunks:
        logger.warning("No circular chunks found — check sample_policies/ directory")
        return 0

    for chunk in chunks:
        store.upsert_chunk(chunk)

    logger.info("Circular ingestion complete — %d chunks → veritas_circulars", len(chunks))
    return len(chunks)


async def ingest_circulars_on_startup(qdrant_client) -> CircularVectorStore | None:
    """Called from app lifespan. Returns the store for use by the gate."""
    try:
        ingest_circulars(qdrant_client, force=False)
        return CircularVectorStore(qdrant_client)
    except Exception as exc:
        logger.warning("Circular ingestion skipped (Qdrant unavailable): %s", exc)
        return None
