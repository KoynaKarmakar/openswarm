"""
Circular Compliance Gate — validates a banking statement against IDBI policy circulars.

Two-phase validation:
  Phase 1 (FAST, deterministic):
    Extract hard rules from retrieved circular chunks.
    Evaluate rule conditions against structured context (risk_tier, kyc_status,
    fraud_score, transaction amounts, etc.).
    If a hard rule gives a definitive COMPLIANT or VIOLATION → return immediately.

  Phase 2 (SEMANTIC, LLM):
    Only reached when no hard rule fires (soft/ambiguous policy territory).
    LLM receives the relevant circular sections + the statement and must judge:
      COMPLIANT / NON_COMPLIANT / AMBIGUOUS
    LLM call goes exclusively through app.llm.router.chat_completion().

Result:
  CircularValidationResult
    valid: bool              — True = penetrates the gate, False = blocked
    phase: "hard_rule" | "llm" | "no_circulars"
    verdict: "COMPLIANT" | "NON_COMPLIANT" | "AMBIGUOUS"
    violated_rules: list[str]       — rule IDs that fired against the statement
    relevant_circulars: list[str]   — circular sections retrieved
    reason: str                     — human-readable explanation
    confidence: float               — 0.0–1.0
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("veritas.circulars.gate")


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class CircularValidationResult:
    valid: bool
    phase: str                           # "hard_rule" | "llm" | "no_circulars"
    verdict: str                         # COMPLIANT / NON_COMPLIANT / AMBIGUOUS
    violated_rules: list[str] = field(default_factory=list)
    relevant_circulars: list[str] = field(default_factory=list)
    reason: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "phase": self.phase,
            "verdict": self.verdict,
            "violated_rules": self.violated_rules,
            "relevant_circulars": self.relevant_circulars,
            "reason": self.reason,
            "confidence": self.confidence,
        }


# ── Hard rule evaluator ────────────────────────────────────────────────────────

_AMOUNT_PATTERN = re.compile(r"₹?\s*([\d,]+(?:\.\d+)?)\s*(?:lakh|L|k)?", re.IGNORECASE)

def _parse_amount_from_text(text: str) -> float | None:
    """Extract the first rupee amount mentioned in a statement."""
    match = _AMOUNT_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    val = float(raw)
    # Normalize common suffixes
    lower = text[match.start():match.end()].lower()
    if "lakh" in lower or " l" in lower:
        val *= 100_000
    elif "k" in lower:
        val *= 1_000
    return val


def _evaluate_hard_rules(
    rule_blocks: list[dict],
    context: dict,
) -> tuple[str | None, str | None, str | None]:
    """
    Walk retrieved rule blocks and check conditions against `context`.
    context keys (all optional):
      risk_tier, kyc_status, fraud_score, transaction_amount,
      velocity_1h, is_geo_mismatch, transaction_type, account_balance

    Returns (verdict, rule_id, reason) or (None, None, None) if no rule fires.
    verdict is "COMPLIANT" or "NON_COMPLIANT".
    """
    risk_tier     = context.get("risk_tier", "")
    kyc_status    = context.get("kyc_status", "")
    fraud_score   = context.get("fraud_score")
    amount        = context.get("transaction_amount")
    velocity_1h   = context.get("velocity_1h")
    is_geo       = context.get("is_geo_mismatch", False)
    txn_type      = context.get("transaction_type", "")

    for rule in rule_blocks:
        rule_id = rule.get("rule_id", "UNKNOWN")
        cond = rule.get("condition", {})
        outcome = rule.get("outcome", "")

        # --- KYC rules ---
        if "kyc_status" in cond:
            expected = cond["kyc_status"]
            if isinstance(expected, dict):
                # {"not": "VERIFIED"} means fire when kyc_status != "VERIFIED"
                if "not" in expected and kyc_status and kyc_status != expected["not"]:
                    return "NON_COMPLIANT", rule_id, rule.get("reason") or f"KYC status '{kyc_status}' violates {rule_id}"
                # {"in": ["REJECTED", "EXPIRED"]} means fire when kyc_status is in the list
                if "in" in expected and kyc_status and kyc_status in expected["in"]:
                    return "NON_COMPLIANT", rule_id, rule.get("reason") or f"KYC status '{kyc_status}' violates {rule_id}"
            elif kyc_status and kyc_status == expected:
                # Rule says kyc_status: VERIFIED → if our status matches, it's compliant
                if risk_tier:
                    tier_cond = cond.get("risk_tier")
                    if tier_cond and isinstance(tier_cond, list) and risk_tier not in tier_cond:
                        continue
                    if tier_cond and isinstance(tier_cond, str) and risk_tier != tier_cond:
                        continue
                return "COMPLIANT", rule_id, f"Matches {rule_id}: outcome={outcome}"

        # --- Risk tier rules ---
        if "risk_tier" in cond and not "kyc_status" in cond:
            expected_tier = cond["risk_tier"]
            if risk_tier:
                if isinstance(expected_tier, list) and risk_tier in expected_tier:
                    return "NON_COMPLIANT" if "REJECT" in outcome else "COMPLIANT", rule_id, f"Risk tier {risk_tier} → {rule_id}: {outcome}"
                elif isinstance(expected_tier, str) and risk_tier == expected_tier:
                    return "NON_COMPLIANT" if "REJECT" in outcome else "COMPLIANT", rule_id, f"Risk tier {risk_tier} → {rule_id}: {outcome}"

        # --- Fraud score rules (UEBT) ---
        if "fraud_score" in cond and fraud_score is not None:
            fs_cond = cond["fraud_score"]
            if isinstance(fs_cond, dict):
                if ">" in fs_cond and fraud_score > float(fs_cond[">"]):
                    return "NON_COMPLIANT", rule_id, f"Fraud score {fraud_score:.2f} exceeds threshold → {rule_id}: {outcome}"
                if "between" in fs_cond:
                    lo, hi = fs_cond["between"]
                    if lo <= fraud_score <= hi:
                        return "NON_COMPLIANT", rule_id, f"Fraud score {fraud_score:.2f} in risky range → {rule_id}: {outcome}"

        # --- Velocity rules (UEBT) ---
        if "velocity_10min" in cond and velocity_1h is not None:
            v_cond = cond["velocity_10min"]
            if isinstance(v_cond, dict) and ">" in v_cond:
                if velocity_1h > v_cond[">"]:
                    return "NON_COMPLIANT", rule_id, f"Transaction velocity {velocity_1h} exceeds threshold → {rule_id}"

        # --- Transaction status (COMP rules) ---
        if "transaction_status" in cond:
            tx_status = context.get("transaction_status", "")
            if tx_status and tx_status == cond["transaction_status"]:
                if amount is not None:
                    amt_cond = cond.get("amount", {})
                    if isinstance(amt_cond, dict) and ">" in amt_cond:
                        if amount > amt_cond[">"]:
                            return "COMPLIANT", rule_id, f"Compensation eligible per {rule_id}"

    return None, None, None


# ── LLM-based semantic validation ─────────────────────────────────────────────

_VERDICT_PATTERN = re.compile(
    r"\b(COMPLIANT|NON_COMPLIANT|NON COMPLIANT|AMBIGUOUS)\b", re.IGNORECASE
)
_RULE_EXTRACT_PATTERN = re.compile(r"\b(CLM|UEBT|KYC|COMP)-\d{3}\b")

_SYSTEM_PROMPT = """You are a banking compliance officer AI for IDBI Bank.
You validate whether a banking statement or request complies with IDBI/RBI policy circulars.

Instructions:
1. Read the retrieved circular sections carefully.
2. Assess whether the statement COMPLIES with, VIOLATES, or is AMBIGUOUS relative to the circulars.
3. Respond in this exact JSON format:
{
  "verdict": "COMPLIANT" | "NON_COMPLIANT" | "AMBIGUOUS",
  "violated_rules": ["RULE-ID", ...],
  "reason": "One concise sentence explaining the verdict.",
  "confidence": 0.0 to 1.0
}

Rules:
- NON_COMPLIANT only when a clear policy rule is violated. Cite the rule_id.
- COMPLIANT when the statement aligns with or is permitted by the circulars.
- AMBIGUOUS when not enough context to judge.
- confidence > 0.85 only when you are certain.
- NEVER include raw PII in your response.
"""


async def _llm_validate(statement: str, circular_sections: list[dict]) -> CircularValidationResult:
    """Phase 2: LLM semantic validation against retrieved circular text."""
    from app.llm.router import chat_completion  # sole gateway — enforced by structural tests

    context_text = "\n\n---\n\n".join(
        f"[{c['policy_name']} — {c['section']}]\n{c['text'][:800]}"
        for c in circular_sections
    )

    user_msg = (
        f"CIRCULAR SECTIONS RETRIEVED:\n{context_text}\n\n"
        f"STATEMENT TO VALIDATE:\n{statement}\n\n"
        "Respond with the JSON verdict only."
    )

    try:
        resp = await chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        raw = resp.content.strip()

        # Extract JSON even if wrapped in markdown
        json_match = re.search(r"\{[\s\S]+\}", raw)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            parsed = json.loads(raw)

        verdict = parsed.get("verdict", "AMBIGUOUS").upper().replace(" ", "_")
        violated = parsed.get("violated_rules", [])
        reason = parsed.get("reason", "")
        confidence = float(parsed.get("confidence", 0.7))

    except Exception as exc:
        logger.warning("LLM circular validation failed: %s — defaulting AMBIGUOUS", exc)
        verdict, violated, reason, confidence = "AMBIGUOUS", [], f"LLM unavailable: {exc}", 0.5

    valid = verdict != "NON_COMPLIANT"
    return CircularValidationResult(
        valid=valid,
        phase="llm",
        verdict=verdict,
        violated_rules=violated,
        relevant_circulars=[f"{c['policy_name']} — {c['section']}" for c in circular_sections],
        reason=reason,
        confidence=confidence,
    )


# ── Main gate class ────────────────────────────────────────────────────────────

class CircularComplianceGate:
    """
    Stateless gate. Requires a CircularVectorStore injected at construction.
    Call validate(statement, context) for every incoming request.
    """

    def __init__(self, vector_store):
        self._store = vector_store  # CircularVectorStore

    async def validate(
        self,
        statement: str,
        context: dict | None = None,
        top_k: int = 5,
    ) -> CircularValidationResult:
        """
        Validate a statement against IDBI policy circulars.

        Args:
            statement:  The banking request / query (already PII-redacted).
            context:    Structured facts known at validation time:
                        risk_tier, kyc_status, fraud_score, transaction_amount,
                        velocity_1h, is_geo_mismatch, transaction_type, ...
            top_k:      How many circular chunks to retrieve.

        Returns:
            CircularValidationResult — valid=True means the statement penetrates the gate.
        """
        if self._store is None:
            logger.warning("Circular store unavailable — gate open (pass-through)")
            return CircularValidationResult(
                valid=True, phase="no_circulars", verdict="AMBIGUOUS",
                reason="Circular vector store unavailable — gate defaulting to pass-through",
                confidence=0.3,
            )

        context = context or {}

        # Retrieve top-k relevant circular chunks
        hits = self._store.search(statement, top_k=top_k)
        if not hits:
            return CircularValidationResult(
                valid=True, phase="no_circulars", verdict="AMBIGUOUS",
                reason="No circular sections retrieved — unable to validate, defaulting open",
                confidence=0.3,
            )

        relevant_names = [f"{h['policy_name']} — {h['section']}" for h in hits]

        # --- Phase 1: Hard rule evaluation ---
        all_rule_blocks = []
        for h in hits:
            all_rule_blocks.extend(h.get("rule_blocks", []))

        if all_rule_blocks:
            verdict, rule_id, reason = _evaluate_hard_rules(all_rule_blocks, context)
            if verdict is not None:
                valid = (verdict == "COMPLIANT")
                logger.info(
                    "Circular gate [hard_rule]: %s rule=%s statement='%.60s'",
                    verdict, rule_id, statement,
                )
                return CircularValidationResult(
                    valid=valid,
                    phase="hard_rule",
                    verdict=verdict,
                    violated_rules=[rule_id] if rule_id and not valid else [],
                    relevant_circulars=relevant_names,
                    reason=reason or "",
                    confidence=0.98,
                )

        # --- Phase 2: LLM semantic validation ---
        logger.info("Circular gate [llm]: no hard rule fired — invoking LLM for '%s'", statement[:60])
        result = await _llm_validate(statement, hits[:3])
        result.relevant_circulars = relevant_names
        logger.info(
            "Circular gate [llm]: %s confidence=%.2f rule=%s",
            result.verdict, result.confidence, result.violated_rules,
        )
        return result
