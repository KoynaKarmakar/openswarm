"""
LangGraph node: circular_gate_node

Position in graph: immediately after redaction_gate, before identity_agent.

Validates the redacted statement against IDBI policy circulars via
CircularComplianceGate (hard rules → LLM fallback).

If the statement is NON_COMPLIANT:
  - Sets rule_fired=True, final_outcome=REJECTED
  - Short-circuits to decision_coordinator (skips all downstream agents)

If COMPLIANT or AMBIGUOUS:
  - Passes through to identity_agent normally
  - Appends circular_result to state for tracing
"""

from __future__ import annotations

import logging

from app.agents.state import AgentResult, VeritasState

logger = logging.getLogger("veritas.circular_gate")


def make_circular_gate_node(gate):
    """
    Factory. `gate` is a CircularComplianceGate (or None if Qdrant unavailable).
    Returns a coroutine function suitable for StateGraph.add_node().
    """
    async def circular_gate_node(state: VeritasState) -> dict:
        if gate is None:
            return {
                "circular_result": None,
                "trace": ["circular_gate: store unavailable — pass-through"],
            }

        statement = state.get("redacted_input") or state.get("raw_input", "")

        # Build context from state (used by hard rule evaluator)
        context: dict = {}
        if state.get("extra_context"):
            ec = state["extra_context"]
            for key in (
                "risk_tier", "kyc_status", "fraud_score",
                "transaction_amount", "velocity_1h",
                "is_geo_mismatch", "transaction_type",
                "account_balance", "transaction_status",
            ):
                if key in ec:
                    context[key] = ec[key]

        result = await gate.validate(statement, context=context)
        result_dict = result.to_dict()

        trace_line = (
            f"circular_gate [{result.phase}]: verdict={result.verdict} "
            f"confidence={result.confidence:.2f} "
            f"rules={result.violated_rules or '—'}"
        )

        if not result.valid:
            # Hard block — short-circuit the entire pipeline
            logger.warning(
                "Circular gate BLOCKED request: %s | reason: %s",
                result.violated_rules, result.reason,
            )
            return {
                "circular_result": result_dict,
                "rule_fired": True,
                "final_outcome": "REJECTED",
                "final_confidence": result.confidence,
                "compliance_result": AgentResult(
                    outcome="REJECTED",
                    confidence=result.confidence,
                    rule_id=result.violated_rules[0] if result.violated_rules else None,
                    details={
                        "reason": result.reason,
                        "violated_circulars": result.violated_rules,
                        "relevant_circulars": result.relevant_circulars,
                        "gate": "circular_compliance",
                    },
                ),
                "trace": [trace_line, f"circular_gate: BLOCKED — {result.reason}"],
            }

        return {
            "circular_result": result_dict,
            "trace": [trace_line],
        }

    return circular_gate_node


def route_after_circular_gate(state: VeritasState) -> str:
    """
    Conditional edge after circular_gate_node.
    If blocked (rule_fired + REJECTED) → jump to decision_coordinator.
    Otherwise → identity_agent.
    """
    if state.get("rule_fired") and state.get("final_outcome") == "REJECTED":
        return "decision_coordinator"
    return "identity_agent"
