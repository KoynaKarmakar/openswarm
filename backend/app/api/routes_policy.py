from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/policy", tags=["policy"])

# rule_id → natural-language query used to retrieve the real clause from
# Qdrant. Mirrors frontend/src/data/citations.js descriptions — kept small
# and explicit rather than trying to derive a query from the rule_id alone.
RULE_QUERY_MAP: dict[str, str] = {
    "UEBT-001": "Flag transaction if geo mismatch detected, transaction location differs from average by distance",
    "UEBT-002": "Flag if more than 3 transactions of similar amount within 10 minutes, velocity check",
    "UEBT-003": "Auto-reject transaction if fraud score greater than 0.85",
    "UEBT-004": "Flag for review if fraud score is between 0.60 and 0.85",
    "CLM-001": "Approve co-lending fast-track if risk tier is A and KYC status is verified",
    "CLM-002": "Approve co-lending standard if risk tier is B or C and KYC status is verified",
    "CLM-003": "Flag for enhanced due diligence if risk tier is D",
    "CLM-004": "Reject co-lending if KYC status is not verified",
    "KYC-001": "Approve identity if KYC status is verified and not expired",
    "KYC-002": "Flag for re-KYC if KYC is older than 2 years",
    "KYC-003": "Reject if KYC status is rejected or expired",
    "COMP-001": "Trigger compensation check if transaction is flagged failed and amount greater than 0",
    "COMP-002": "Escalate to branch manager if compensation amount greater than 10000",
}

# External reference kept server-side as the single source of truth — the
# frontend citations.js mirrors this as an instant-fallback only.
EXTERNAL_REF: dict[str, dict] = {
    **{k: {"ref": "RBI/2017-18/15", "refLabel": "RBI Master Direction — Customer Protection in UEBT"} for k in
       ("UEBT-001", "UEBT-002", "UEBT-003", "UEBT-004")},
    **{k: {"ref": "RBI/DOR/2025-26/139", "refLabel": "RBI — Co-Lending Arrangements Directions, 2025"} for k in
       ("CLM-001", "CLM-002", "CLM-003", "CLM-004")},
    **{k: {"ref": "IDBI Bank Policy", "refLabel": "Master Direction — Know Your Customer (KYC), RBI"} for k in
       ("KYC-001", "KYC-002", "KYC-003")},
    **{k: {"ref": "IDBI Board-Approved Policy", "refLabel": "Customer Compensation Policy"} for k in
       ("COMP-001", "COMP-002")},
}


class PolicyCitationResponse(BaseModel):
    rule_id: str
    policy_name: str | None
    section: str | None
    text: str | None
    score: float | None
    ref: str | None
    ref_label: str | None
    source: str  # "qdrant" | "unavailable"


@router.get("/citation/{rule_id}", response_model=PolicyCitationResponse)
async def get_policy_citation(
    rule_id: str,
    request: Request,
    _=Depends(get_current_user),
):
    """
    Live retrieval of the clause backing a rule_id from the Qdrant policy
    RAG index — this is what makes the citation chip's drawer literally
    backed by the RAG layer, not just a static string table.
    """
    ext_ref = EXTERNAL_REF.get(rule_id, {})
    query = RULE_QUERY_MAP.get(rule_id)

    if not query:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown rule_id: {rule_id}")

    qdrant_client = request.app.state.qdrant_client
    if qdrant_client is None:
        return PolicyCitationResponse(
            rule_id=rule_id, policy_name=None, section=None, text=None, score=None,
            ref=ext_ref.get("ref"), ref_label=ext_ref.get("refLabel"), source="unavailable",
        )

    chunks = qdrant_client.search(query, top_k=1)
    if not chunks:
        return PolicyCitationResponse(
            rule_id=rule_id, policy_name=None, section=None, text=None, score=None,
            ref=ext_ref.get("ref"), ref_label=ext_ref.get("refLabel"), source="unavailable",
        )

    top = chunks[0]
    return PolicyCitationResponse(
        rule_id=rule_id,
        policy_name=top.policy_name,
        section=top.section,
        text=top.text,
        score=round(top.score, 4),
        ref=ext_ref.get("ref"),
        ref_label=ext_ref.get("refLabel"),
        source="qdrant",
    )
