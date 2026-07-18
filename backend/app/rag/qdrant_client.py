"""
Qdrant vector store client for VERITAS policy RAG.

Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384-dim, local, no API key).
Collection: veritas_policies
Each point: one policy section chunk (~300 tokens) with metadata.

In production, swap the embedding model for Gemini text embeddings via LiteLLM
for consistency with the primary model — the interface here doesn't change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings

logger = logging.getLogger("veritas.rag")
settings = get_settings()

VECTOR_SIZE = 384       # all-MiniLM-L6-v2 output dimension
COLLECTION = settings.qdrant_collection
TOP_K = 3               # chunks to retrieve per query


@dataclass
class PolicyChunk:
    chunk_id: str
    policy_name: str
    section: str
    text: str
    score: float          # cosine similarity


class VeritasQdrantClient:
    def __init__(self):
        from qdrant_client import QdrantClient as _QdrantClient
        self._client = _QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        self._embedding_model = None  # lazy init — model load is slow

    def _get_embedding_model(self):
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer
            self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Sentence-transformers model loaded (all-MiniLM-L6-v2, 384-dim)")
        return self._embedding_model

    def embed(self, text: str) -> list[float]:
        model = self._get_embedding_model()
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def collection_exists(self) -> bool:
        try:
            self._client.get_collection(COLLECTION)
            return True
        except Exception:
            return False

    def create_collection(self):
        from qdrant_client.models import Distance, VectorParams
        self._client.recreate_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", COLLECTION)

    def upsert(self, chunk_id: str, text: str, metadata: dict):
        from qdrant_client.models import PointStruct
        vector = self.embed(text)
        self._client.upsert(
            collection_name=COLLECTION,
            points=[
                PointStruct(
                    id=abs(hash(chunk_id)) % (2**63),  # Qdrant needs uint64
                    vector=vector,
                    payload={**metadata, "text": text, "chunk_id": chunk_id},
                )
            ],
        )

    def search(self, query: str, top_k: int = TOP_K) -> list[PolicyChunk]:
        """Return the top_k most relevant policy chunks for a query."""
        vector = self.embed(query)
        try:
            results = self._client.search(
                collection_name=COLLECTION,
                query_vector=vector,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            logger.warning("Qdrant search failed: %s — returning empty results", exc)
            return []

        return [
            PolicyChunk(
                chunk_id=str(r.payload.get("chunk_id", r.id)),
                policy_name=r.payload.get("policy_name", ""),
                section=r.payload.get("section", ""),
                text=r.payload.get("text", ""),
                score=float(r.score),
            )
            for r in results
        ]


@lru_cache(maxsize=1)
def get_qdrant_client() -> VeritasQdrantClient:
    return VeritasQdrantClient()
