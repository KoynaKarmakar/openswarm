"""
VERITAS swarm CLI — run the agents from a single command.

    python -m app.swarm "What is the co-lending exposure limit? PAN ABCDE1234F"
    python -m app.swarm "Onboard me" --aadhaar 999941057058 --otp 123456
    python -m app.swarm "..." --engine oai      # LLM-driven Swarm (needs a model)

This is what OpenSwarm's `openswarm run` (or any terminal/agent) invokes to
execute the four-agent swarm. It grounds on the integrity-verified policy memory,
degrades gracefully when heavy deps (Presidio/XGBoost) aren't installed, and
prints the live agent trace + decision.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from types import SimpleNamespace

# ── ANSI (no dependency) ──────────────────────────────────────────────────────
_C = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m", "b": "\033[36m",
      "d": "\033[90m", "w": "\033[97m", "x": "\033[0m"}
def _c(s, col): return f"{_C[col]}{s}{_C['x']}"


# ── lightweight redaction gate shim (works without Presidio) ──────────────────
_PII = [
    ("IN_PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("IN_AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("IN_IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    ("EMAIL_ADDRESS", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("IN_PHONE", re.compile(r"\b(?:\+?91[- ]?)?[6-9]\d{9}\b")),
]


class _RegexGate:
    """Fallback gate with the RedactionGate.redact() contract."""
    def redact(self, text):
        out, entity_map, mapping, detected = text or "", {}, {}, []
        for label, rx in _PII:
            for m in rx.findall(out):
                tok = f"<{label}>"
                entity_map[tok] = label
                mapping[tok] = m if isinstance(m, str) else m[0]
                if label not in detected:
                    detected.append(label)
            out = rx.sub(f"<{label}>", out)
        return SimpleNamespace(text=out, entity_map=entity_map, mapping=mapping, detected_types=detected)


def _make_gate():
    try:
        from app.redaction.gate import get_redaction_gate
        return get_redaction_gate(), "presidio"
    except Exception:
        return _RegexGate(), "regex-fallback"


# ── deterministic run ─────────────────────────────────────────────────────────
async def _run_graph(args, retriever):
    from app.swarm.context import SwarmContext
    from app.swarm.orchestrator import build_swarm

    gate, gate_kind = _make_gate()
    adapter = None
    try:
        import numpy  # noqa: F401 — the fraud model needs it; skip identity/fraud if absent
        import xgboost  # noqa: F401
        from app.adapters.mock_adapter import MockBankAdapter
        adapter = MockBankAdapter()
    except Exception:
        adapter = None

    extra = {}
    if args.aadhaar:
        extra["aadhaar"] = args.aadhaar
        if args.otp:
            extra["aadhaar_otp"] = args.otp

    swarm = build_swarm(gate=gate, adapter=adapter, qdrant=retriever, db=None, circular_gate=None)
    ctx = SwarmContext(request_id="cli", request_type=args.request_type,
                       raw_input=args.request, extra_context=extra)
    ctx = await swarm.run(ctx)

    print(_c(f"\n  gate: {gate_kind}   adapter: {'mock' if adapter else 'none (identity/fraud skipped)'}\n", "d"))
    _print_trace(ctx.handoff_path, ctx.trace)
    policy = ctx.get("policy_result") or {}
    _print_result(
        outcome=ctx.get("final_outcome") or "NEEDS_REVIEW",
        score=ctx.get("confidence_score"),
        redacted=ctx.get("redacted_input"),
        answer=ctx.get("llm_response"),
        cited=(policy.get("details") or {}).get("policies_cited"),
        decision_id=ctx.get("decision_id"),
    )


# ── LLM-driven (OpenAI-Swarm) run ─────────────────────────────────────────────
async def _run_oai(args, retriever):
    from app.swarm.oai import Swarm
    from app.swarm.oai.agents import run_veritas, summarize_run

    try:
        resp = await run_veritas(Swarm(), args.request,
                                 aadhaar=args.aadhaar or "", aadhaar_otp=args.otp or "",
                                 retriever=retriever)
    except Exception as exc:
        print(_c(f"\n  OAI engine needs a configured LLM (router.py). Error: {exc}\n", "y"))
        print(_c("  Falling back to the deterministic engine.\n", "d"))
        return await _run_graph(args, retriever)

    s = summarize_run(resp)
    _print_trace(s["handoff_path"], s["trace"])
    _print_result(outcome=s["outcome"], score=s["confidence_score"], redacted=s["redacted"],
                  answer=s["answer"], cited=s["cited"], decision_id=None)


# ── printing ──────────────────────────────────────────────────────────────────
def _print_trace(path, trace):
    print(_c("  swarm ▸ " + " → ".join(path), "b"))
    print(_c("  " + "─" * 60, "d"))
    for line in trace:
        agent = line.split(":", 1)[0]
        rest = line[len(agent):]
        print("  " + _c(agent, "b") + rest)
    print(_c("  " + "─" * 60, "d"))


def _print_result(*, outcome, score, redacted, answer, cited, decision_id):
    col = "g" if outcome == "APPROVED" else "r" if outcome == "REJECTED" else "y"
    print("  " + _c(f"OUTCOME  {outcome}", col) + _c(f"   confidence {score}/100", "w"))
    if redacted:
        print("  " + _c("redacted ", "d") + redacted)
    if answer:
        print("  " + _c("answer   ", "d") + answer)
    if cited:
        print("  " + _c("cited    ", "d") + ", ".join(cited))
    if decision_id:
        print("  " + _c("ledger   ", "d") + str(decision_id))
    print()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m app.swarm", description="Run the VERITAS trust swarm agents")
    ap.add_argument("request", help="the request / question to run through the swarm")
    ap.add_argument("--engine", choices=["graph", "oai"], default="graph",
                    help="graph = deterministic (default), oai = LLM-driven OpenAI-Swarm")
    ap.add_argument("--request-type", default="ASSISTANT", dest="request_type")
    ap.add_argument("--aadhaar", default="")
    ap.add_argument("--otp", default="")
    args = ap.parse_args(argv)

    from app.memory.verified_store import get_verified_memory
    retriever = get_verified_memory()

    print(_c(f"\n🐙 VERITAS swarm · engine={args.engine} · verified memory: "
             f"{len(retriever.verify_integrity())} sources ({'all verified' if retriever.all_verified else 'INTEGRITY BREAK'})", "w"))
    runner = _run_oai if args.engine == "oai" else _run_graph
    asyncio.run(runner(args, retriever))
    return 0


if __name__ == "__main__":
    sys.exit(main())
