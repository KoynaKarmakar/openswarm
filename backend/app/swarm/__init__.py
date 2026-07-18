"""
VERITAS OpenSwarm runtime.

A router-compliant realization of the OpenAI Swarm handoff pattern:
  * `SwarmAgent`  — an agent with a name and an async `run(ctx)` method
                    (mirrors a Swarm "Agent").
  * `Directive`   — what an agent returns to steer routing
                    (mirrors a Swarm handoff / function-that-returns-an-Agent).
  * `SwarmContext`— shared mutable context passed between agents
                    (mirrors Swarm "context_variables") plus an append-only trace.
  * `Swarm`       — the conductor that runs the dynamic zone and then always
                    runs the deterministic terminal agent (the Auditor).

Design constraint honoured here: every LLM reasoning step performed by an agent
must go through `app.llm.router.chat_completion`. This runtime never calls an LLM
itself, so the single-LLM-chokepoint rule (test_no_llm_bypass.py) stays intact.
"""

from app.swarm.context import SwarmContext
from app.swarm.core import Directive, Swarm, SwarmAgent

__all__ = ["SwarmContext", "Directive", "Swarm", "SwarmAgent"]
