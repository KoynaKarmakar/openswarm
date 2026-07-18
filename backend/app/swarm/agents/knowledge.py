"""
🔍 Agent 2 — Knowledge (grounded RAG, anti-hallucination).

Filled in on branch `agent-knowledge`. It will:
  * retrieve verified policy / RBI-circular chunks from Qdrant (rag/qdrant_client.py);
  * build a tightly bounded context string;
  * call `app.llm.router.chat_completion` with the instruction to answer using
    ONLY the provided text, else say "I cannot verify this".

Placeholder below is a no-op pass-through.
"""

from __future__ import annotations

from app.swarm.context import SwarmContext
from app.swarm.core import Directive


class KnowledgeAgent:
    name = "knowledge"

    async def run(self, ctx: SwarmContext) -> Directive:
        ctx.log("knowledge: placeholder pass-through (base branch)")
        return Directive()
