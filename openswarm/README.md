# Running VERITAS inside OpenSwarm

This folder packages the VERITAS trust middleware as an **OpenSwarm swarm**: four
agent system-prompt definitions (`agents/*.md`) + a topology manifest
(`swarm.md`). The agents wire to the real Python tools in `../backend` (import
root `app.*`).

## Two ways to run it

**A. Native OpenSwarm runtime** — the agent markdown drives OpenSwarm's own
orchestration:
```bash
# from the repo root
openswarm init                 # register this repo as an OpenSwarm project
openswarm run "Assess this co-lending request: <redacted request>" \
  --path .                     # runs guardrail → knowledge → identity_fraud → auditor
```

**B. The Python swarm (already built & tested)** — the same topology as a FastAPI
service:
```bash
cd backend && uvicorn app.main:app --reload
# POST /swarm/decide  → runs the swarm, returns outcome, confidence, handoff path,
#                       redacted message, VC + Aadhaar results, trace
```

## Deploy the demo App to the canvas

`../demo/veritas-swarm-dashboard.html` is a self-contained App. On the OpenSwarm
dashboard, add it as an HTML App to run it live on the workspace canvas (or open
the file directly in a browser). It visualizes the full swarm — redaction,
injection catch, grounded RAG, Google VC, **Aadhaar OTP**, confidence gauge, and
the SHA-256 ledger.

## Infra (matches the OpenSwarm deploy model)

```bash
docker compose up --build      # backend + Postgres + Valkey + Qdrant (see docker-compose.yml)
```

## ⚠️ Schema reconciliation (one detail to confirm)

The frontmatter keys here (`name`, `model`, `tools`, `handoffs`, `entrypoint`,
`terminal`) follow the common OpenSwarm agent-definition pattern, but the exact
keys your OpenSwarm build expects may differ. **Run `openswarm init` once and
share what it scaffolds** (its `openswarm.yaml` / agent template), and the
frontmatter here can be aligned field-for-field. The agent *bodies* (the system
prompts) and the tool mappings are correct regardless of the wrapper.
