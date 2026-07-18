"""
VERITAS Fabric MCP Server — production-grade MCP SDK surface.

Exposes 4 banking tools over the MCP protocol so non-coding staff
(compliance officers, risk analysts) can invoke VERITAS directly from
Claude Desktop / any MCP client without touching APIs.

Usage (stdio mode, as configured in claude_desktop_config.json):
    python mcp_server/server.py

Env vars:
    VERITAS_BACKEND_URL   Base URL of FastAPI backend (default: http://localhost:8000)
    VERITAS_API_KEY       Shared API key for backend auth (optional; passed as Bearer token)
"""

import asyncio
import os
import json
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

BACKEND_URL = os.getenv("VERITAS_BACKEND_URL", "http://localhost:8000")
API_KEY     = os.getenv("VERITAS_API_KEY", "")


def _headers() -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


async def _post(path: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BACKEND_URL}{path}", json=payload, headers=_headers())
        r.raise_for_status()
        return r.json()


async def _get(path: str, params: dict | None = None) -> dict | list:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{BACKEND_URL}{path}", params=params or {}, headers=_headers())
        r.raise_for_status()
        return r.json()


app = Server("veritas-fabric")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="verify_identity",
            description=(
                "Verify a customer's identity using VERITAS Fabric. "
                "Returns KYC status, risk tier, co-lending eligibility, and a W3C-style "
                "DID-ready credential (no raw PII in the credential). "
                "Every call is logged to the immutable audit ledger."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Customer identifier (e.g. CUST00001)",
                    }
                },
                "required": ["customer_id"],
            },
        ),
        types.Tool(
            name="check_fraud_risk",
            description=(
                "Run an XGBoost fraud-risk assessment on the most recent transactions "
                "for an account. Returns fraud score (0-1), outcome, UEBT policy rule "
                "applied, and an explainability trace of all agent steps. "
                "Scores above 0.85 → FLAGGED; 0.60-0.85 → NEEDS_REVIEW; below → CLEARED."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Account identifier (e.g. ACC000010)",
                    }
                },
                "required": ["account_id"],
            },
        ),
        types.Tool(
            name="ask_assistant",
            description=(
                "Ask the VERITAS AI banking assistant a question. "
                "The message is passed through a PII redaction gate BEFORE reaching the LLM — "
                "PAN numbers, Aadhaar, phone numbers, and bank account numbers are replaced "
                "with labelled tokens server-side. "
                "Returns the AI response, redacted version of your message (showing what the "
                "LLM actually saw), detected PII types, compliance outcome, and agent trace."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Your question or request (may include PII — it will be redacted before LLM call)",
                    },
                    "customer_id": {
                        "type": "string",
                        "description": "Optional customer context ID",
                    },
                    "account_id": {
                        "type": "string",
                        "description": "Optional account context ID",
                    },
                },
                "required": ["message"],
            },
        ),
        types.Tool(
            name="get_audit_trail",
            description=(
                "Retrieve the VERITAS audit ledger. Each record contains the decision type, "
                "outcome, SHA-256 hash linking it to the previous record, and the agent trace. "
                "Optionally verify the entire hash chain integrity."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of records to return (default 20)",
                        "default": 20,
                    },
                    "verify_chain": {
                        "type": "boolean",
                        "description": "If true, also verify the SHA-256 hash chain and return integrity status",
                        "default": False,
                    },
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "verify_identity":
            customer_id = arguments.get("customer_id", "").strip()
            if not customer_id:
                raise ValueError("customer_id is required")
            result = await _post("/identity/verify", {"customer_id": customer_id})
            summary = _format_identity(result)
            return [types.TextContent(type="text", text=summary)]

        elif name == "check_fraud_risk":
            account_id = arguments.get("account_id", "").strip()
            if not account_id:
                raise ValueError("account_id is required")
            result = await _post("/fraud/check", {"account_id": account_id})
            summary = _format_fraud(result)
            return [types.TextContent(type="text", text=summary)]

        elif name == "ask_assistant":
            message    = arguments.get("message", "").strip()
            if not message:
                raise ValueError("message is required")
            payload: dict = {"message": message}
            if arguments.get("customer_id"):
                payload["customer_id"] = arguments["customer_id"]
            if arguments.get("account_id"):
                payload["account_id"] = arguments["account_id"]
            result = await _post("/assistant/chat", payload)
            summary = _format_assistant(result)
            return [types.TextContent(type="text", text=summary)]

        elif name == "get_audit_trail":
            limit        = int(arguments.get("limit", 20))
            verify       = bool(arguments.get("verify_chain", False))
            records      = await _get("/audit/trail", {"limit": limit})
            verify_info  = None
            if verify:
                try:
                    verify_info = await _get("/audit/verify")
                except Exception as e:
                    verify_info = {"error": str(e)}
            summary = _format_audit(records, verify_info)
            return [types.TextContent(type="text", text=summary)]

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            pass
        return [types.TextContent(type="text", text=f"Backend error {e.response.status_code}: {detail or str(e)}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_identity(r: dict) -> str:
    lines = [
        f"## Identity Verification — {r.get('customer_id', '')}",
        f"**Outcome:** {r.get('outcome', '?')}",
        f"**KYC Status:** {r.get('kyc_status', '?')}",
        f"**Risk Tier:** {r.get('risk_tier', '?')}",
        f"**Co-Lending Eligible:** {'Yes' if r.get('co_lending_eligible') else 'No'}",
    ]
    cred = r.get("did_credential", {})
    if cred:
        lines += [
            "",
            "**DID-Ready Credential** (no raw PII):",
            f"  issuer: {cred.get('issuer', '?')}",
            f"  kyc_status: {cred.get('credentialSubject', {}).get('kyc_status', '?')}",
            f"  risk_tier: {cred.get('credentialSubject', {}).get('risk_tier', '?')}",
            f"  co_lending_eligible: {cred.get('credentialSubject', {}).get('co_lending_eligible', '?')}",
        ]
    trace = r.get("trace", [])
    if trace:
        lines += ["", "**Agent Trace:**"] + [f"  ▸ {s}" for s in trace]
    return "\n".join(lines)


def _format_fraud(r: dict) -> str:
    score = r.get("fraud_score")
    score_str = f"{score * 100:.1f}%" if score is not None else "N/A"
    lines = [
        f"## Fraud Risk — {r.get('account_id', '')}",
        f"**Outcome:** {r.get('outcome', '?')}",
        f"**Fraud Score:** {score_str}",
        f"**Confidence:** {r.get('confidence', 0) * 100:.0f}%",
        f"**Transactions Checked:** {r.get('transactions_checked', 0)}",
    ]
    if r.get("rule_id"):
        lines.append(f"**Policy Rule Applied:** {r['rule_id']}")
    trace = r.get("trace", [])
    if trace:
        lines += ["", "**Agent Trace:**"] + [f"  ▸ {s}" for s in trace]
    return "\n".join(lines)


def _format_assistant(r: dict) -> str:
    pii_types = r.get("detected_pii_types", [])
    lines = [
        "## VERITAS AI Assistant Response",
        "",
        f"**AI Response:** {r.get('response', '')}",
        "",
        f"**Outcome:** {r.get('outcome', '?')}",
        f"**Confidence:** {r.get('confidence', 0) * 100:.0f}%",
        f"**Memory Hit (cached):** {'Yes' if r.get('memory_hit') else 'No'}",
        "",
        "**PII Redaction Summary:**",
        f"  Redacted message sent to LLM: {r.get('redacted_message', '')}",
        f"  PII types detected & redacted: {', '.join(pii_types) if pii_types else 'None'}",
    ]
    trace = r.get("trace", [])
    if trace:
        lines += ["", "**Agent Trace:**"] + [f"  ▸ {s}" for s in trace]
    return "\n".join(lines)


def _format_audit(records: list, verify_info: dict | None) -> str:
    lines = [f"## Audit Ledger — {len(records)} records"]
    if verify_info:
        if "error" in verify_info:
            lines.append(f"**Chain Verification:** Error — {verify_info['error']}")
        elif verify_info.get("valid"):
            lines.append(f"**Chain Integrity:** ✓ VALID ({verify_info.get('records_checked', '?')} records verified)")
        else:
            lines.append(f"**Chain Integrity:** ✗ BROKEN at index {verify_info.get('break_at_index')}: {verify_info.get('break_reason')}")
    lines.append("")
    for i, rec in enumerate(records[:10]):  # show first 10 inline
        curr = rec.get("curr_hash", "")
        curr_short = f"{curr[:8]}…{curr[-6:]}" if len(curr) > 16 else curr
        lines.append(f"  #{i+1} [{rec.get('decision_type','?')}] {rec.get('outcome','?')} — hash: {curr_short}")
    if len(records) > 10:
        lines.append(f"  … and {len(records) - 10} more")
    return "\n".join(lines)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
