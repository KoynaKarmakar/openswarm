"""
🛡️ Agent 1 — Guardrail (PII redaction + prompt-injection + hard compliance).

The firewall for every incoming request. In order:

  1. **PII redaction** — run the Presidio RedactionGate so Indian PII
     (Aadhaar/PAN/IFSC/bank-account/phone) becomes entity-type labels before
     anything else sees the text. `redacted_input` + `entity_map` are written to
     the context; the token→original mapping is deliberately discarded.
  2. **Prompt-injection / policy-evasion scan** — cheap regex over the RAW input.
     A hit (jailbreak, or a request to launder money / fake KYC / evade tax) is a
     hard catch: mark the request REJECTED and `Directive(halt=True)` straight to
     the Auditor. Nothing reaches the LLM. (Demo "Scenario B".)
  3. **Hard compliance circulars** — reuse the existing CircularComplianceGate via
     the legacy `circular_gate_node`. NON_COMPLIANT ⇒ short-circuit to the Auditor.

Clean input hands off to the Knowledge agent.
"""

from __future__ import annotations

import logging

from app.agents.circular_gate_node import make_circular_gate_node
from app.agents.state import AgentResult
from app.swarm.context import SwarmContext
from app.swarm.core import Directive
from app.swarm.guards import detect_injection

logger = logging.getLogger("veritas.swarm.guardrail")


class GuardrailAgent:
    name = "guardrail"

    def __init__(self, *, gate=None, circular_gate=None):
        """
        gate          : RedactionGate (redaction/gate.py). If None, redaction is
                        skipped (raw text is passed through unredacted).
        circular_gate : CircularComplianceGate. If None, the hard-rule step is a
                        pass-through (mirrors the LangGraph node's behaviour).
        """
        self._gate = gate
        self._circular_gate = circular_gate

    async def run(self, ctx: SwarmContext) -> Directive:
        raw = ctx.raw_input or ""

        # ── 1. PII redaction ────────────────────────────────────────────────
        if self._gate is not None:
            result = self._gate.redact(raw)
            ctx.set("redacted_input", result.text)
            ctx.set("entity_map", result.entity_map)
            ctx.log(
                f"guardrail/redaction: detected=[{', '.join(result.detected_types) or '—'}] "
                f"entities_masked={len(result.mapping)}"
            )
        else:
            ctx.set("redacted_input", raw)
            ctx.log("guardrail/redaction: no gate configured — pass-through")

        # ── 2. Prompt-injection / policy-evasion scan (on RAW input) ─────────
        hits = detect_injection(raw)
        if hits:
            categories = sorted({h.category for h in hits})
            labels = [h.label for h in hits]
            logger.warning("Guardrail BLOCKED request %s: %s", ctx.request_id, labels)
            ctx.set("rule_fired", True)
            ctx.set("final_outcome", "REJECTED")
            ctx.set("final_confidence", 0.99)
            ctx.set(
                "compliance_result",
                AgentResult(
                    outcome="REJECTED",
                    confidence=0.99,
                    rule_id="GRD-INJ-001",
                    details={
                        "reason": "prompt-injection / policy-evasion attempt blocked",
                        "categories": categories,
                        "matched_rules": labels,
                        "gate": "guardrail_injection",
                    },
                ),
            )
            ctx.log(
                f"guardrail/injection: BLOCKED categories={categories} rules={labels}"
            )
            return Directive(halt=True, reason=f"injection:{','.join(categories)}")

        ctx.log("guardrail/injection: clean")

        # ── 3. Hard compliance circulars (reuse existing tested node) ────────
        if self._circular_gate is not None:
            node = make_circular_gate_node(self._circular_gate)
            delta = await node(ctx.snapshot_state())
            ctx.absorb(delta)
            if ctx.get("rule_fired") and ctx.get("final_outcome") == "REJECTED":
                ctx.log("guardrail/circular: NON_COMPLIANT — short-circuit to Auditor")
                return Directive(halt=True, reason="circular:non_compliant")
        else:
            ctx.log("guardrail/circular: no gate configured — pass-through")

        return Directive(next_agent="knowledge")
