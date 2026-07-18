# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

VERITAS Fabric is AI trust middleware for banking (co-lending decisions). Request flow:

1. **Presidio PII redaction gate** (`backend/app/redaction/gate.py`) — PII must never reach the LLM. The token→original map lives in-process only, never persisted or returned.
2. **LangGraph agent pipeline** (`backend/app/agents/graph.py`): `identity_agent` → `fraud_agent` (XGBoost) → `compliance_agent` (hard CLM/UEBT rules — if `rule_fired=True`, the LLM call is skipped) → `policy_agent` (Qdrant RAG) → `decision_coordinator`.
3. **SHA-256 hash-chain ledger** (`backend/app/ledger/chain.py`) — every decision is auditable; each record covers the previous hash + payload + timestamp. An outbox worker writes to `AuditRecord`.

`BankAdapter` (`backend/app/adapters/`) is an ABC; `MockBankAdapter` is used today, swappable for `IDBISandboxAdapter` (currently a stub) via config.

## Critical architectural rule

**`litellm.acompletion()` may only be called from `backend/app/llm/router.py`.** This is enforced by `backend/tests/test_no_llm_bypass.py` — never add a direct LLM call anywhere else.

## Known gaps (don't "fix" without asking)

- **Alembic is not wired up.** `alembic/` has only an empty `versions/` dir — no `env.py`/`alembic.ini`. Schema is created via `Base.metadata.create_all()` at startup (see comment in `backend/app/main.py`). Don't assume `alembic upgrade head` works.
- **Python version mismatch**: README requires Python 3.13 locally, but `backend/Dockerfile` uses `python:3.11-slim`. Local dev and Docker are not equivalent environments.
- **JWT is kept in module memory in the frontend, not localStorage** — this is an intentional security decision (`frontend/src/api/client.js`), not an oversight.

## Commands

**Docker (primary workflow):**
```bash
cp .env.example .env
docker compose up --build            # first run / infra changes
docker compose up -d --build backend  # after backend/requirements.txt changes
docker compose up -d --build frontend # after ANY frontend/src change — no hot reload in Docker
docker compose logs -f backend
```
Backend hot-reloads automatically (bind mount + `uvicorn --reload`); frontend does not.

**Backend tests:**
```bash
cd backend
pytest                              # run all
pytest tests/test_ledger_chain.py -v
```
Test collection order matters: `tests/test_00_adapter_model.py` is prefixed `00_` to force it to run first — XGBoost must load before spaCy on macOS ARM (OpenMP conflict). Presidio imports are intentionally lazy inside `RedactionGate.__init__()` for the same reason. On macOS ARM, `brew install libomp` is required for XGBoost.

**Frontend:**
```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build
```
No lint or test scripts are defined for the frontend.

## Other notes

- Demo login is auto-seeded on backend startup: `demo@idbi.bank` / `demo1234`.
- `backend/app/ml/fraud_model.joblib` is a committed pre-trained artifact; regenerate via `seed_data/generate_and_train.py`, not on every build.
- No linting/formatting tooling is configured for backend or frontend.
