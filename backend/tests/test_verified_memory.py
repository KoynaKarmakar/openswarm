"""
Verified memory tests — integrity gating, cited retrieval, and Knowledge grounding.
"""

from __future__ import annotations

import json

from app.memory.verified_store import (
    VerifiedMemoryStore,
    build_manifest,
    sha256_hex,
)
from app.swarm.agents.knowledge import KnowledgeAgent
from app.swarm.context import SwarmContext


# ── the real committed corpus ─────────────────────────────────────────────────

def test_real_corpus_all_verified():
    store = VerifiedMemoryStore()
    integrity = store.verify_integrity()
    assert integrity and all(v == "verified" for v in integrity.values())
    assert store.all_verified is True


def test_search_returns_cited_source():
    store = VerifiedMemoryStore()
    hits = store.search("co-lending exposure share limit", top_k=2)
    assert hits, "expected a co-lending hit"
    top = hits[0]
    assert "Co-Lending" in top.policy_name
    assert top.score >= 0.3
    assert top.source["ref"].startswith("RBI/2020-21/63")   # genuine provenance
    assert "rbi.org.in" in top.source["url"]


def test_offtopic_query_returns_nothing():
    # nothing verified matches → Knowledge agent will refuse ("I cannot verify this")
    assert VerifiedMemoryStore().search("how do I launder money offshore") == []


def test_chunk_is_qdrant_compatible():
    c = VerifiedMemoryStore().search("KYC periodic updation", top_k=1)[0]
    for attr in ("chunk_id", "policy_name", "section", "text", "score"):
        assert hasattr(c, attr)


# ── integrity gating with a temp corpus ───────────────────────────────────────

def _seed(tmp_path, body="Co-lending retained exposure is 20 percent of each loan."):
    d = tmp_path / "verified"
    d.mkdir()
    f = d / "entry.md"
    f.write_text(f"---\npolicy_name: Test Policy\nsection: X\nref: R1\nurl: http://x\n---\n{body}\n")
    manifest = d / "manifest.json"
    manifest.write_text(json.dumps({"entry.md": sha256_hex(f.read_bytes())}))
    return d, f, manifest


def test_tampered_file_is_quarantined(tmp_path):
    d, f, _ = _seed(tmp_path)
    store = VerifiedMemoryStore(directory=str(d))
    assert store.search("co-lending exposure")            # verified → searchable

    f.write_text(f.read_text() + "\nInjected unverified sentence.")  # tamper after vouching
    store.reload()
    assert store.verify_integrity()["entry.md"] == "tampered"
    assert store.search("co-lending exposure") == []      # quarantined → not returned
    assert store.all_verified is False


def test_unlisted_file_is_quarantined(tmp_path):
    d, _, manifest = _seed(tmp_path)
    (d / "rogue.md").write_text("---\npolicy_name: Rogue\n---\nUntrusted co-lending claim.")
    store = VerifiedMemoryStore(directory=str(d))
    assert store.verify_integrity()["rogue.md"] == "unlisted"
    assert all(c.chunk_id != "rogue.md" for c in store.search("co-lending claim"))


def test_manifest_is_deterministic():
    m1, m2 = build_manifest(), build_manifest()
    assert m1 == m2 and len(m1) >= 4


# ── Knowledge agent grounds on verified memory (drop-in for Qdrant) ───────────

async def test_knowledge_grounds_on_verified_memory():
    captured = {}

    async def fake_complete(messages, *, temperature, max_tokens):
        captured["prompt"] = messages[1]["content"]
        class _R:
            content = "Per the RBI Co-Lending Model, the NBFC retains at least 20%."
            model_used = "test"
        return _R()

    store = VerifiedMemoryStore()
    agent = KnowledgeAgent(qdrant=store, completion_fn=fake_complete)   # store IS the retriever
    ctx = SwarmContext(request_id="r1", request_type="ASSISTANT",
                       raw_input="What is the co-lending retained exposure share?")
    ctx.set("redacted_input", ctx.raw_input)

    await agent.run(ctx)

    assert ctx.get("llm_response").startswith("Per the RBI Co-Lending Model")
    policy = ctx.get("policy_result")
    assert "RBI Co-Lending Model (CLM)" in policy["details"]["policies_cited"]
    assert "20%" in captured["prompt"]                    # genuine text reached the grounding prompt
