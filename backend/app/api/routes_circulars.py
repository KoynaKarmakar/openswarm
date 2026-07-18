"""
Circular Compliance API — expose the circular gate as a standalone endpoint.

POST /circulars/validate
  Validate any banking statement directly against IDBI policy circulars.
  Useful for compliance officers to test statements before processing.
  The statement is PII-redacted first (gate.redact) then passed to CircularComplianceGate.

GET /circulars/search
  Semantic search over the circular vector store — retrieve relevant sections.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.schemas import TokenData

router = APIRouter(prefix="/circulars", tags=["circulars"])


class ValidateRequest(BaseModel):
    statement: str
    context: dict | None = None    # optional structured facts (risk_tier, kyc_status, etc.)
    top_k: int = 5


class ValidateResponse(BaseModel):
    # Statement as seen by the gate (PII-redacted)
    redacted_statement: str
    detected_pii_types: list[str]
    # Gate result
    valid: bool                     # True = penetrates the gate
    phase: str                      # "hard_rule" | "llm" | "no_circulars"
    verdict: str                    # COMPLIANT / NON_COMPLIANT / AMBIGUOUS
    violated_rules: list[str]
    relevant_circulars: list[str]
    reason: str
    confidence: float


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filter_has_rules: bool = False  # return only chunks with hard rules


class SearchResult(BaseModel):
    policy_name: str
    section: str
    text: str
    rule_ids: list[str]
    has_hard_rules: bool
    score: float


@router.post("/validate", response_model=ValidateResponse)
async def validate_statement(
    payload: ValidateRequest,
    request: Request,
    _: TokenData = Depends(get_current_user),
):
    """
    Validate a banking statement against IDBI policy circulars.

    The statement passes through:
    1. PII redaction gate (Presidio) — raw PII stripped before any processing
    2. Circular compliance gate — hard rules first, LLM fallback

    Returns whether the statement PENETRATES the gate (valid=True) or is BLOCKED.
    """
    gate = request.app.state.redaction_gate
    circular_gate = getattr(request.app.state, "circular_gate", None)

    if circular_gate is None:
        raise HTTPException(
            status_code=503,
            detail="Circular compliance gate unavailable (Qdrant may not be running)",
        )

    # Always redact PII before passing to gate
    redaction = gate.redact(payload.statement)

    result = await circular_gate.validate(
        redaction.text,
        context=payload.context or {},
        top_k=payload.top_k,
    )

    return ValidateResponse(
        redacted_statement=redaction.text,
        detected_pii_types=redaction.detected_types,
        valid=result.valid,
        phase=result.phase,
        verdict=result.verdict,
        violated_rules=result.violated_rules,
        relevant_circulars=result.relevant_circulars,
        reason=result.reason,
        confidence=result.confidence,
    )


@router.post("/search", response_model=list[SearchResult])
async def search_circulars(
    payload: SearchRequest,
    request: Request,
    _: TokenData = Depends(get_current_user),
):
    """
    Semantic search over IDBI policy circulars.
    Returns the most relevant sections for a given query.
    """
    circular_gate = getattr(request.app.state, "circular_gate", None)
    if circular_gate is None:
        raise HTTPException(status_code=503, detail="Circular gate unavailable")

    hits = circular_gate._store.search(payload.query, top_k=payload.top_k)

    if payload.filter_has_rules:
        hits = [h for h in hits if h.get("has_hard_rules")]

    return [
        SearchResult(
            policy_name=h["policy_name"],
            section=h["section"],
            text=h["text"],
            rule_ids=h["rule_ids"],
            has_hard_rules=h["has_hard_rules"],
            score=h["score"],
        )
        for h in hits
    ]


@router.get("/rules")
async def list_all_rules(
    request: Request,
    _: TokenData = Depends(get_current_user),
):
    """
    Return all hard rule IDs extracted from the circular documents.
    Shows which rules the gate can evaluate deterministically.
    """
    circular_gate = getattr(request.app.state, "circular_gate", None)
    if circular_gate is None:
        raise HTTPException(status_code=503, detail="Circular gate unavailable")

    # Search broadly and collect all rule blocks
    hits = circular_gate._store.search("policy rule condition outcome", top_k=20)

    all_rules: dict[str, dict] = {}
    for h in hits:
        for rb in h.get("rule_blocks", []):
            rid = rb.get("rule_id")
            if rid and rid not in all_rules:
                all_rules[rid] = {
                    "rule_id": rid,
                    "description": rb.get("description", ""),
                    "outcome": rb.get("outcome", ""),
                    "source": h["policy_name"],
                }

    # Sort by rule ID
    sorted_rules = sorted(all_rules.values(), key=lambda r: r["rule_id"])
    return {
        "total": len(sorted_rules),
        "rules": sorted_rules,
    }
