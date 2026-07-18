"""
The four VERITAS swarm agents.

Dynamic zone (hand off to each other):
    GuardrailAgent  → KnowledgeAgent → IdentityFraudAgent
Deterministic tail (always runs last):
    AuditorAgent

On the base branch these are minimal pass-through placeholders so the runtime
imports and the smoke test passes. Each is filled in on its own feature branch:
    agent-guardrail / agent-knowledge / agent-identity-fraud / agent-auditor
"""

from app.swarm.agents.auditor import AuditorAgent
from app.swarm.agents.guardrail import GuardrailAgent
from app.swarm.agents.identity_fraud import IdentityFraudAgent
from app.swarm.agents.knowledge import KnowledgeAgent

__all__ = [
    "GuardrailAgent",
    "KnowledgeAgent",
    "IdentityFraudAgent",
    "AuditorAgent",
]
