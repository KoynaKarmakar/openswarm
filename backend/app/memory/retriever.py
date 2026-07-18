"""
Data memory retriever — semantic search over `veritas_data_memory` Qdrant collection.

Complements the policy RAG (veritas_policies) with customer/account/risk knowledge.
"""

from __future__ import annotations

import logging

from app.memory.ingester import COLLECTION

logger = logging.getLogger("veritas.memory.retriever")


async def search_data_memory(
    qdrant_client,
    query: str,
    limit: int = 5,
    doc_type: str | None = None,
) -> list[dict]:
    """
    Semantic search over veritas_data_memory.

    Args:
        qdrant_client: VeritasQdrantClient instance
        query:         Natural-language query string
        limit:         Max results to return
        doc_type:      Optional filter — "customer" | "account" | "account_risk_profile"

    Returns:
        List of {text, score, doc_type, metadata} dicts, ranked by cosine similarity.
    """
    try:
        vector = qdrant_client.embed(query)
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return []

    search_kwargs: dict = {
        "collection_name": COLLECTION,
        "query_vector": vector,
        "limit": limit,
        "with_payload": True,
    }

    if doc_type:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        search_kwargs["query_filter"] = Filter(
            must=[FieldCondition(key="doc_type", match=MatchValue(value=doc_type))]
        )

    try:
        results = qdrant_client._client.search(**search_kwargs)
    except Exception as exc:
        logger.warning("Data memory search failed: %s", exc)
        return []

    return [
        {
            "text":      r.payload.get("text", ""),
            "score":     float(r.score),
            "doc_type":  r.payload.get("doc_type", ""),
            "metadata":  {k: v for k, v in r.payload.items() if k not in ("text", "chunk_id")},
        }
        for r in results
    ]


async def get_customer_context(qdrant_client, customer_id: str) -> str | None:
    """
    Retrieve the stored customer profile text for a specific customer_id.
    Returns the text string or None if not found.
    """
    results = await search_data_memory(
        qdrant_client,
        query=f"Customer {customer_id}",
        limit=5,
        doc_type="customer",
    )
    for r in results:
        if r["metadata"].get("customer_id") == customer_id:
            return r["text"]
    return None


async def get_account_risk_context(qdrant_client, account_id: str) -> str | None:
    """
    Retrieve the aggregated risk profile for a specific account_id.
    Returns the text string or None if not found.
    """
    results = await search_data_memory(
        qdrant_client,
        query=f"Account {account_id} transaction risk",
        limit=5,
        doc_type="account_risk_profile",
    )
    for r in results:
        if r["metadata"].get("account_id") == account_id:
            return r["text"]
    return None
