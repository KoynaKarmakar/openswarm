"""
🔍 Agent 2 — Knowledge (grounded RAG, anti-hallucination).

Two steps:

  1. **Retrieve** — reuse the existing, tested `policy_node` to pull the top
     policy / RBI-circular chunks from Qdrant and build a bounded context string.
     (If a hard rule already fired upstream, `policy_node` skips retrieval.)
  2. **Ground** — if relevant policy was found, ask the LLM to answer using ONLY
     that text, else say exactly "I cannot verify this". If nothing relevant was
     retrieved for a question, we return that refusal WITHOUT calling the LLM.

The LLM is reached exclusively through `app.llm.router.chat_completion` (the
single chokepoint). It is injectable via `completion_fn` so tests never need
network/keys; production defaults to the router.

Hands off to the Identity & Fraud agent.
"""

from __future__ import annotations

import logging

from app.agents.policy_agent import policy_node
from app.swarm.context import SwarmContext
from app.swarm.core import Directive

logger = logging.getLogger("veritas.swarm.knowledge")

_CANNOT_VERIFY = "I cannot verify this."

_GROUNDING_SYSTEM = (
    "You are VERITAS Knowledge, a banking-policy assistant. "
    "Answer the question using ONLY the policy text provided below. "
    "Do not use outside knowledge. If the answer is not contained in the "
    f'provided text, reply with exactly: "{_CANNOT_VERIFY}" '
    "Never repeat or ask for PII. Cite the policy name in your answer."
)


class KnowledgeAgent:
    name = "knowledge"

    def __init__(self, *, qdrant=None, completion_fn=None):
        """
        qdrant        : Qdrant client (rag/qdrant_client.py). If None, retrieval
                        returns no context and questions get the refusal.
        completion_fn : async (messages, *, temperature, max_tokens) -> response
                        with `.content` and `.model_used`. Defaults to
                        app.llm.router.chat_completion (lazy import).
        """
        self._qdrant = qdrant
        self._completion_fn = completion_fn

    async def _complete(self, messages, *, temperature, max_tokens):
        fn = self._completion_fn
        if fn is None:
            from app.llm.router import chat_completion  # deferred — keeps import light
            fn = chat_completion
        return await fn(messages, temperature=temperature, max_tokens=max_tokens)

    async def run(self, ctx: SwarmContext) -> Directive:
        # ── 1. Retrieve (reuse the tested policy node) ───────────────────────
        delta = await policy_node(ctx.snapshot_state(), qdrant_client=self._qdrant)
        ctx.absorb(delta)

        policy_result = ctx.get("policy_result") or {}
        details = policy_result.get("details", {}) if isinstance(policy_result, dict) else {}
        policy_context = details.get("policy_context", "")
        is_question = ctx.request_type in ("ASSISTANT", "COMPLIANCE")

        # ── 2. Ground the answer ─────────────────────────────────────────────
        if policy_context:
            question = ctx.get("redacted_input") or ctx.raw_input
            messages = [
                {"role": "system", "content": _GROUNDING_SYSTEM},
                {"role": "user", "content": f"Policy text:\n{policy_context}\n\nQuestion: {question}"},
            ]
            try:
                response = await self._complete(messages, temperature=0.1, max_tokens=512)
                ctx.set("llm_response", response.content)
                ctx.set("model_used", response.model_used)
                ctx.log(
                    f"knowledge: grounded answer via {response.model_used} "
                    f"(cited={details.get('policies_cited')})"
                )
            except Exception as exc:  # noqa: BLE001 — never let RAG failure crash the swarm
                logger.warning("Knowledge LLM call failed: %s", exc)
                ctx.set("llm_response", None)
                ctx.set("error", str(exc))
                ctx.log(f"knowledge: LLM call FAILED — {exc}")
        elif is_question:
            # No relevant policy retrieved for a question → refuse, no LLM call.
            ctx.set("llm_response", _CANNOT_VERIFY)
            ctx.log("knowledge: no relevant policy — returning 'I cannot verify this' (no LLM call)")
        else:
            ctx.log("knowledge: no policy context and not a question — deferring to downstream agents")

        return Directive(next_agent="identity_fraud")
