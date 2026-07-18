"""
Assemble the VERITAS swarm.

This is the OpenSwarm equivalent of `build_graph()` in agents/graph.py. It wires
the four agents into a `Swarm` with the dynamic zone in order and the Auditor as
the deterministic terminal agent.

Dependencies (RedactionGate, BankAdapter, Qdrant client, DB session) are injected
here and captured by the agents, exactly as the LangGraph builder injected them —
nodes/agents stay free of global state.
"""

from __future__ import annotations

from app.swarm.agents import (
    AuditorAgent,
    GuardrailAgent,
    IdentityFraudAgent,
    KnowledgeAgent,
)
from app.swarm.core import Swarm


def build_swarm(
    *,
    gate=None,
    adapter=None,
    qdrant=None,
    db=None,
    circular_gate=None,
) -> Swarm:
    """
    Build the swarm. Keyword deps are optional so the base branch is importable
    and testable before the agents are wired to their engines. Each agent branch
    threads the deps it needs into its own constructor.
    """
    dynamic_zone = [
        GuardrailAgent(gate=gate, circular_gate=circular_gate),
        KnowledgeAgent(qdrant=qdrant),
        IdentityFraudAgent(adapter=adapter),
    ]
    terminal = AuditorAgent(db=db)
    return Swarm(dynamic_zone, terminal)
