# VERITAS × OpenSwarm — roadmap

AI trust middleware for banking, orchestrated as a 4-agent OpenSwarm:
**Guardrail → Knowledge → Identity & Fraud → Auditor** (dynamic handoffs; the
Auditor always runs last, so nothing escapes the audit trail).

## Shipped ✅

- **Swarm runtime** — router-compliant OpenAI-Swarm handoff pattern (`app/swarm/`);
  the conductor makes no LLM calls, agents route through `llm/router.py`.
- **Guardrail** — Presidio PII redaction + prompt-injection/policy-evasion guard
  (short-circuits Scenario B before the LLM).
- **Knowledge** — Qdrant RAG grounded answer, "answer only from policy, else
  *I cannot verify this*".
- **Identity & Fraud** — KYC + XGBoost fraud + **Google Verifiable Credentials**
  (Ed25519) + **Aadhaar** (UIDAI Auth 2.5-shaped: DEMO, LIVE seam, and a
  **KUA-aggregator** licence-free path).
- **Auditor** — confidence score + SHA-256 hash-chain ledger.
- **`POST /swarm/decide`** API + **interactive demo dashboard** (OpenSwarm canvas App).
- ~80 swarm unit tests; secrets kept out of git.

## Next up 🔜 (near-term)

1. **Cut over the main flow** — point `/assistant/chat` (or the frontend) at the
   swarm instead of the legacy LangGraph graph; keep the graph as a fallback flag.
2. **Structured LLM output** — have the Knowledge/Auditor path return a typed
   decision (outcome + rationale + citations) via the router, replacing the
   heuristic outcome parse.
3. **Frontend wiring** — a real "Swarm" page in `frontend/` calling `/swarm/decide`,
   rendering the handoff path, confidence gauge, and ledger (the dashboard is the
   design reference).
4. **Aadhaar OTP two-step in the API** — expose `generate_otp` → `verify` as two
   endpoints so the KUA/live flow works end-to-end for onboarding.

## Mid-term 🧭

5. **Real IDBI adapter** — implement `IDBISandboxAdapter` behind the `BankAdapter`
   ABC (today a stub); config-switch from `MockBankAdapter`.
6. **Ledger verification endpoint hardening** — periodic chain re-verification +
   an alert when `/audit/verify` finds a break.
7. **Policy corpus expansion** — ingest more RBI circulars; add citation coverage
   metrics to the Knowledge agent.
8. **Per-agent metrics & tracing** — latency/decision-source counters; export the
   swarm trace as OpenTelemetry spans.
9. **e-KYC (KUA) demographic + photo** — extend the aggregator client beyond OTP
   yes/no to fetch the offline e-KYC XML (name/photo/address) where licensed.

## Hardening / production 🔐

10. **Alembic migrations** — currently `create_all()` at startup; wire real
    migrations before any non-demo deployment.
11. **Secrets management** — move license keys/certs to a vault; the connectors
    already read from env/config.
12. **Load & resilience** — extend `load_test.py` to the swarm path; add circuit
    breakers around external connectors (UIDAI/KUA/Qdrant).

See `docs/AADHAAR_GOLIVE.md` for the Aadhaar connection paths and go-live steps.
