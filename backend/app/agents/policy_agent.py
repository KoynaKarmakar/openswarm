from __future__ import annotations

import logging

from app.agents.state import AgentResult, VeritasState

logger = logging.getLogger("veritas.policy")

MIN_RELEVANCE_SCORE = 0.3   # cosine similarity threshold for RAG results


async def policy_node(state: VeritasState, qdrant_client=None) -> dict:
    """
    Retrieve relevant IDBI policy sections via Qdrant RAG.
    If a hard rule already fired (from compliance_agent), skip retrieval.
    The retrieved text is included in the LLM prompt via the state.
    """
    if state.get("rule_fired"):
        return {
            "policy_result": AgentResult(
                outcome="APPROVED",
                confidence=1.0,
                details={"note": "skipped — hard rule already resolved request"},
            ),
            "trace": ["policy_agent: skipped (hard rule resolved request)"],
        }

    query = state.get("redacted_input") or state.get("raw_input", "")
    request_type = state.get("request_type", "")

    if not query or not qdrant_client:
        return {
            "policy_result": AgentResult(
                outcome="NEEDS_REVIEW", confidence=0.5,
                details={"note": "no query or Qdrant unavailable"},
            ),
            "trace": ["policy_agent: no query/Qdrant — LLM path with no policy context"],
        }

    try:
        chunks = qdrant_client.search(query, top_k=3)
    except Exception as exc:
        logger.warning("Qdrant search error: %s", exc)
        chunks = []

    relevant = [c for c in chunks if c.score >= MIN_RELEVANCE_SCORE]

    if not relevant:
        return {
            "policy_result": AgentResult(
                outcome="NEEDS_REVIEW", confidence=0.5,
                details={"note": "no relevant policy found — open LLM path"},
            ),
            "trace": [f"policy_agent: no relevant chunks (threshold={MIN_RELEVANCE_SCORE})"],
        }

    policy_context = "\n\n---\n\n".join(
        f"[{c.policy_name} — {c.section}]\n{c.text}"
        for c in relevant
    )

    best_score = relevant[0].score

    return {
        "policy_result": AgentResult(
            outcome="NEEDS_REVIEW",
            confidence=float(best_score),
            details={
                "retrieved_chunks": len(relevant),
                "best_relevance_score": round(best_score, 4),
                "policy_context": policy_context,  # passed to LLM prompt
                "policies_cited": [c.policy_name for c in relevant],
            },
        ),
        "trace": [
            f"policy_agent: retrieved {len(relevant)} chunks "
            f"(best={best_score:.3f}) from policies={[c.policy_name for c in relevant]}"
        ],
    }
