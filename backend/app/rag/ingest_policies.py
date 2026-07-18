"""
Policy document ingestion — chunk IDBI policy markdown files and load into Qdrant.
Run at startup if the collection is empty, or as a standalone script.

Chunking strategy: split on markdown headers (##, ###) to preserve semantic units.
Each chunk is one section of a policy document.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger("veritas.rag.ingest")

POLICY_DIR = Path(__file__).parent.parent.parent.parent / "seed_data" / "sample_policies"
MIN_CHUNK_CHARS = 100   # skip tiny sections


def _chunk_markdown(text: str, policy_name: str) -> list[dict]:
    """Split a markdown doc on ## and ### headers into semantic chunks."""
    # Split on lines starting with ## or ###
    sections = re.split(r"\n(?=#{2,3} )", text)
    chunks = []
    for i, section in enumerate(sections):
        section = section.strip()
        if len(section) < MIN_CHUNK_CHARS:
            continue
        # Extract the section title from the first line
        first_line = section.split("\n")[0].lstrip("#").strip()
        chunks.append({
            "chunk_id": f"{policy_name}::{i}::{first_line[:40]}",
            "policy_name": policy_name,
            "section": first_line,
            "text": section,
        })
    return chunks


def ingest_all(qdrant_client, force: bool = False) -> int:
    """
    Ingest all policy docs from sample_policies/ into Qdrant.
    Returns number of chunks ingested.
    Skips if collection already has data (unless force=True).
    """
    if not force and qdrant_client.collection_exists():
        try:
            info = qdrant_client._client.get_collection(qdrant_client._client.__class__.__name__)
        except Exception:
            pass
        # Check point count
        try:
            count = qdrant_client._client.count(
                qdrant_client._client.__class__.__name__
            ).count
            if count > 0:
                logger.info("Qdrant collection already populated (%d chunks) — skipping ingest", count)
                return 0
        except Exception:
            pass

    if not qdrant_client.collection_exists():
        qdrant_client.create_collection()

    if not POLICY_DIR.exists():
        logger.warning("Policy directory not found: %s", POLICY_DIR)
        return 0

    policy_files = list(POLICY_DIR.glob("*.md"))
    if not policy_files:
        logger.warning("No .md files in %s", POLICY_DIR)
        return 0

    total = 0
    for policy_path in policy_files:
        policy_name = policy_path.stem.replace("_", " ").title()
        text = policy_path.read_text(encoding="utf-8")
        chunks = _chunk_markdown(text, policy_name)

        for chunk in chunks:
            qdrant_client.upsert(
                chunk_id=chunk["chunk_id"],
                text=chunk["text"],
                metadata={
                    "policy_name": chunk["policy_name"],
                    "section": chunk["section"],
                    "source_file": policy_path.name,
                },
            )
            total += 1

        logger.info("Ingested %s → %d chunks", policy_path.name, len(chunks))

    logger.info("Policy ingestion complete — %d total chunks in Qdrant", total)
    return total


async def ingest_on_startup(qdrant_client) -> None:
    """Called from app lifespan — runs ingestion if Qdrant is reachable."""
    try:
        ingest_all(qdrant_client, force=False)
    except Exception as exc:
        logger.warning("Policy ingestion skipped (Qdrant may not be running): %s", exc)
