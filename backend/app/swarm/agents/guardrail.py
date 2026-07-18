"""
🛡️ Agent 1 — Guardrail (PII redaction + prompt-injection + hard compliance).

Filled in on branch `agent-guardrail`. It will:
  * run the Presidio RedactionGate (redaction/gate.py) to redact Indian PII
    (Aadhaar/PAN/IFSC/bank-account/phone) into entity-type labels;
  * scan for prompt-injection patterns;
  * apply the hard circular/compliance rules;
  * on a catch (PII leak attempt or NON_COMPLIANT), return Directive(halt=True)
    to short-circuit straight to the Auditor — nothing reaches the LLM.

Placeholder below is a no-op pass-through so the base runtime imports and the
smoke test runs without the heavy Presidio/spaCy dependencies.
"""

from __future__ import annotations

from app.swarm.context import SwarmContext
from app.swarm.core import Directive


class GuardrailAgent:
    name = "guardrail"

    def __init__(self, **_deps):
        # Base placeholder swallows injected deps (gate, circular_gate);
        # the agent-guardrail branch tightens this signature.
        pass

    async def run(self, ctx: SwarmContext) -> Directive:
        ctx.log("guardrail: placeholder pass-through (base branch)")
        return Directive()
