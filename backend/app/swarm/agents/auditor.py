"""
📜 Agent 4 — Auditor (verification + logging). The deterministic terminal agent.

Filled in on branch `agent-auditor`. It will:
  * resolve the final outcome from the agent results in ctx.vars;
  * compute and print a Confidence Score;
  * write the decision into the SHA-256 hash-chain ledger (ledger/chain.py) via
    the outbox intent (ledger/outbox.py) — every request, no exceptions.

This agent ALWAYS runs last (Swarm terminal), so no branch of the swarm can
escape the audit trail — the same guarantee `decision_coordinator` gave in the
LangGraph design.

Placeholder below records a trace line so the smoke test can assert the terminal
agent always ran.
"""

from __future__ import annotations

from app.swarm.context import SwarmContext
from app.swarm.core import Directive


class AuditorAgent:
    name = "auditor"

    def __init__(self, **_deps):
        # Base placeholder swallows injected deps (db);
        # the agent-auditor branch tightens this signature.
        pass

    async def run(self, ctx: SwarmContext) -> Directive:
        ctx.log(
            "auditor: placeholder — final outcome + hash-chain write happens here "
            f"(path={' → '.join(ctx.handoff_path)})"
        )
        return Directive()
