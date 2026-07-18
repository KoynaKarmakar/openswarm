"""
Knowledge agent tests. Fakes for Qdrant + the LLM completion — no keys/network.
"""

from __future__ import annotations

import pytest

from app.swarm.agents.knowledge import KnowledgeAgent
from app.swarm.context import SwarmContext


class _Chunk:
    def __init__(self, score, policy_name, section, text):
        self.score = score
        self.policy_name = policy_name
        self.section = section
        self.text = text


class _FakeQdrant:
    def __init__(self, chunks):
        self._chunks = chunks

    def search(self, query, top_k=3):
        return list(self._chunks)


class _Resp:
    def __init__(self, content, model):
        self.content = content
        self.model_used = model


def _ctx(raw="What is the co-lending exposure limit?", rtype="ASSISTANT") -> SwarmContext:
    c = SwarmContext(request_id="r1", request_type=rtype, raw_input=raw)
    c.set("redacted_input", raw)
    return c


async def test_knowledge_grounds_when_policy_found():
    captured = {}

    async def fake_complete(messages, *, temperature, max_tokens):
        captured["messages"] = messages
        return _Resp("Per CLM Policy, the co-lending limit is 20%.", "gemini/test")

    qdrant = _FakeQdrant([_Chunk(0.82, "CLM Policy", "3.1", "Co-lending exposure capped at 20%.")])
    agent = KnowledgeAgent(qdrant=qdrant, completion_fn=fake_complete)
    ctx = _ctx()

    directive = await agent.run(ctx)

    assert directive.next_agent == "identity_fraud"
    assert ctx.get("llm_response") == "Per CLM Policy, the co-lending limit is 20%."
    assert ctx.get("model_used") == "gemini/test"
    # anti-hallucination instruction reached the model
    assert "I cannot verify this." in captured["messages"][0]["content"]
    # bounded context contained the retrieved policy text
    assert "20%" in captured["messages"][1]["content"]


async def test_knowledge_refuses_without_calling_llm_when_no_policy():
    async def exploding_complete(messages, *, temperature, max_tokens):
        raise AssertionError("LLM must NOT be called when no policy was retrieved")

    # score below MIN_RELEVANCE_SCORE (0.3) → no relevant chunks
    qdrant = _FakeQdrant([_Chunk(0.05, "Unrelated", "1", "irrelevant")])
    agent = KnowledgeAgent(qdrant=qdrant, completion_fn=exploding_complete)
    ctx = _ctx()

    directive = await agent.run(ctx)

    assert directive.next_agent == "identity_fraud"
    assert ctx.get("llm_response") == "I cannot verify this."


async def test_knowledge_survives_llm_failure():
    async def failing_complete(messages, *, temperature, max_tokens):
        raise RuntimeError("model down")

    qdrant = _FakeQdrant([_Chunk(0.9, "CLM Policy", "3.1", "Co-lending exposure capped at 20%.")])
    agent = KnowledgeAgent(qdrant=qdrant, completion_fn=failing_complete)
    ctx = _ctx()

    directive = await agent.run(ctx)

    assert directive.next_agent == "identity_fraud"
    assert ctx.get("llm_response") is None
    assert ctx.get("error") == "model down"


async def test_knowledge_no_qdrant_refuses_question():
    agent = KnowledgeAgent(qdrant=None)
    ctx = _ctx()

    directive = await agent.run(ctx)

    assert directive.next_agent == "identity_fraud"
    assert ctx.get("llm_response") == "I cannot verify this."
