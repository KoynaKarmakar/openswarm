# VERITAS Swarm — canvas Apps

Two self-contained, single-file Apps you can drop onto the **OpenSwarm workspace
canvas** (or open directly in a browser) — no build, no server, no network:

| File | What it is |
|---|---|
| `veritas-swarm-console.html` | **The real React Swarm Console UI** — the actual `/swarm/decide` frontend, built to one file, running the agents client-side (`window.__SWARM_MOCK__`) with staged "agents running" animation. Regenerate: `cd frontend && npm run build:standalone` → `dist-standalone/standalone.html`. |
| `veritas-swarm-dashboard.html` | A lighter hand-built dashboard visualization of the same swarm. |

Both show the four agents running end-to-end (redaction, injection catch, grounded
RAG, Google VC, Aadhaar OTP, confidence gauge, SHA-256 ledger). The Console mirrors
the production UI; when a backend is reachable it calls the live API instead.

---

## veritas-swarm-dashboard.html

`veritas-swarm-dashboard.html` is a **self-contained, single-file** interactive
demo of the OpenSwarm-orchestrated VERITAS trust swarm. No build step, no server,
no network — open it directly, or drop it onto the **OpenSwarm workspace canvas**
as an App.

## What it shows (your golden demo path)

Pick a scenario chip, then **Run through swarm** and watch the four agents work:

| Scenario | What the judge sees |
|---|---|
| **A — Valid co-lending query** | PII (PAN/IFSC) redacted → Knowledge grounds the answer in RBI policy → identity + Google VC verified → **APPROVED**, high confidence, ledger block sealed |
| **B — Injection / illegal advice** | Guardrail catches the jailbreak + money-laundering ask and **short-circuits straight to the Auditor** — Knowledge and Identity are skipped, nothing reaches the LLM → **REJECTED** |
| **C — KYC with Aadhaar** | Heavy PII redaction; the presented Google VC is from an untrusted issuer → signature **unchecked** → **NEEDS_REVIEW** |
| **D — High-risk transfer** | XGBoost fraud score crosses the UEBT threshold → fraud verdict overrides everything → **REJECTED / FLAGGED** |

Also live: the redaction diff, the "answer only from policy, else *I cannot verify
this*" refusal, the Google Verifiable Credential signature states, a 0–100
confidence gauge, a **real `crypto.subtle` SHA-256 hash-chain ledger** (each run
appends a tamper-evident block), and the append-only explainability trace.

The client-side logic deliberately mirrors the real backend agents — the same
redaction recognizers, the same injection/policy-evasion rules, the same VC
signature/trust logic, the same outcome precedence, and the same hash-chain
formula (`SHA256(prev + payload + timestamp)`).

## Run it

- **Locally:** open `veritas-swarm-dashboard.html` in any browser.
- **In the OpenSwarm canvas:** add it as an App / HTML block on the dashboard.

## Wire it to the live backend

Replace the simulated `run()` with a call to the real endpoint added in this work
(`backend/app/api/routes_swarm.py`):

```js
const res = await fetch("/swarm/decide", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({
    message,
    request_type: "CO_LENDING",
    verifiable_credential: vc,   // optional presented Google VC
  }),
});
const data = await res.json();
// data.outcome, data.confidence_score, data.redacted_message,
// data.detected_pii_types, data.handoff_path, data.vc_verification, data.trace
```
