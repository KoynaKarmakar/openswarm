"""
Data memory ingester — loads all seed data into Qdrant collection `veritas_data_memory`.

Ingests three document types:
  customer          — KYC/risk profile per customer (100 docs)
  account           — account summary per account (131 docs)
  account_risk_profile — aggregated transaction risk stats per account

Skips re-ingestion if collection already has data (idempotent on startup).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger("veritas.memory.ingest")

SEED        = Path(__file__).parent.parent.parent.parent / "seed_data"
COLLECTION  = "veritas_data_memory"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2


def _load(filename: str) -> list[dict] | dict:
    path = SEED / filename
    if not path.exists():
        raise FileNotFoundError(f"Seed data not found: {path}")
    with open(path) as f:
        return json.load(f)


def _ensure_collection(qdrant_client) -> None:
    from qdrant_client.models import Distance, VectorParams
    try:
        qdrant_client._client.get_collection(COLLECTION)
    except Exception:
        qdrant_client._client.recreate_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", COLLECTION)


def _collection_count(qdrant_client) -> int:
    try:
        return qdrant_client._client.count(COLLECTION).count
    except Exception:
        return 0


def _upsert(qdrant_client, chunk_id: str, text: str, metadata: dict) -> None:
    from qdrant_client.models import PointStruct
    vector = qdrant_client.embed(text)
    qdrant_client._client.upsert(
        collection_name=COLLECTION,
        points=[
            PointStruct(
                id=abs(hash(chunk_id)) % (2 ** 63),
                vector=vector,
                payload={**metadata, "text": text, "chunk_id": chunk_id},
            )
        ],
    )


def _build_customer_docs(customers: list[dict]) -> list[tuple[str, str, dict]]:
    docs = []
    for c in customers:
        cid     = c["customer_id"]
        co_str  = "eligible" if c["co_lending_eligible"] else "not eligible"
        verified = c.get("kyc_verified_at") or "N/A"
        expires  = c.get("kyc_expires_at") or "N/A"
        text = (
            f"Customer {cid}: KYC status {c['kyc_status']}, risk tier {c['risk_tier']}, "
            f"co-lending {co_str}, city {c['city']}. "
            f"KYC verified: {verified}, expires: {expires}."
        )
        docs.append((
            f"customer::{cid}",
            text,
            {"doc_type": "customer", "customer_id": cid, "kyc_status": c["kyc_status"],
             "risk_tier": c["risk_tier"], "co_lending_eligible": c["co_lending_eligible"]},
        ))
    return docs


def _build_account_docs(accounts: list[dict]) -> list[tuple[str, str, dict]]:
    docs = []
    for a in accounts:
        aid       = a["account_id"]
        frozen_str = "frozen" if a["is_frozen"] else "active"
        text = (
            f"Account {aid} ({a['account_type']}): Balance ₹{a['balance']:,.2f}, "
            f"KYC status {a['kyc_status']}, {frozen_str}, "
            f"home city {a['home_city']}. Owned by customer {a['customer_id']}."
        )
        docs.append((
            f"account::{aid}",
            text,
            {"doc_type": "account", "account_id": aid, "customer_id": a["customer_id"],
             "account_type": a["account_type"], "is_frozen": a["is_frozen"]},
        ))
    return docs


def _build_risk_profile_docs(transactions: list[dict]) -> list[tuple[str, str, dict]]:
    by_account: dict[str, list[dict]] = defaultdict(list)
    for t in transactions:
        by_account[t["account_id"]].append(t)

    docs = []
    for aid, txns in by_account.items():
        fraud_txns  = [t for t in txns if t.get("is_fraud") == 1]
        legit_txns  = [t for t in txns if t.get("is_fraud") == 0]
        legit_amounts = [t["amount"] for t in legit_txns] or [0]
        all_amounts   = [t["amount"] for t in txns]
        geo_mismatch  = sum(1 for t in txns if t.get("is_geo_mismatch") == 1)
        avg_velocity  = sum(t.get("velocity_1h", 0) for t in txns) / max(len(txns), 1)

        text = (
            f"Account {aid} transaction risk profile: {len(txns)} total transactions, "
            f"{len(fraud_txns)} fraud detected, "
            f"average legitimate amount ₹{sum(legit_amounts)/max(len(legit_amounts),1):,.0f}, "
            f"max amount ₹{max(all_amounts):,.0f}, "
            f"{geo_mismatch} geo-mismatch events, "
            f"average hourly velocity {avg_velocity:.1f}."
        )
        docs.append((
            f"risk_profile::{aid}",
            text,
            {"doc_type": "account_risk_profile", "account_id": aid,
             "total_txns": len(txns), "fraud_count": len(fraud_txns),
             "geo_mismatch_count": geo_mismatch},
        ))
    return docs


def ingest_all(qdrant_client, force: bool = False) -> int:
    _ensure_collection(qdrant_client)

    if not force:
        count = _collection_count(qdrant_client)
        if count > 0:
            logger.info("Data memory already populated (%d docs) — skipping ingest", count)
            return 0

    customers    = _load("synthetic_customers.json")
    accounts     = _load("synthetic_accounts.json")
    transactions = _load("synthetic_transactions.json")

    all_docs: list[tuple[str, str, dict]] = []
    all_docs.extend(_build_customer_docs(customers))
    all_docs.extend(_build_account_docs(accounts))
    all_docs.extend(_build_risk_profile_docs(transactions))

    for chunk_id, text, metadata in all_docs:
        _upsert(qdrant_client, chunk_id, text, metadata)

    logger.info(
        "Data memory ingested: %d customers + %d accounts + %d risk profiles = %d total docs",
        len(customers), len(accounts),
        len(all_docs) - len(customers) - len(accounts),
        len(all_docs),
    )
    return len(all_docs)


async def ingest_data_on_startup(qdrant_client) -> None:
    try:
        ingest_all(qdrant_client, force=False)
    except Exception as exc:
        logger.warning("Data memory ingestion skipped: %s", exc)
