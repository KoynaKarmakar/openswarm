# VERITAS Fabric — AI Trust Middleware for Banking

**Team SentiCoders · IDBI Innovate 2026 · Problem Statement 5**

> *"From Reconciliation to Real-Time"* — co-lending decisions in <2 seconds vs 2-5 days manual reconciliation.

VERITAS Fabric is a compliance-first, explainable AI middleware that sits between banking staff/partners and LLM-powered tools. Every decision is audit-logged to an immutable SHA-256 hash-chain ledger. PII never reaches the LLM.

---

## Architecture Overview

```
User / MCP Client
        │
        ▼
  ┌─────────────────────────────────────────┐
  │  FastAPI Backend (port 8000)            │
  │                                         │
  │  PII Redaction Gate (Presidio)          │
  │        │                                │
  │        ▼                                │
  │  LangGraph Agent Pipeline               │
  │  ├── identity_agent (BankAdapter)       │
  │  ├── fraud_agent   (XGBoost model)      │
  │  ├── compliance_agent (CLM/UEBT rules)  │
  │  ├── policy_agent  (Qdrant RAG)         │
  │  └── decision_coordinator              │
  │        │                                │
  │        ▼                                │
  │  SHA-256 Hash-Chain Ledger (Postgres)  │
  │  Outbox Worker → AuditRecord            │
  └─────────────────────────────────────────┘
        │               │
        ▼               ▼
  React Frontend    MCP Server
  (port 5173)       (stdio, Claude Desktop)
```

**Key design decisions:**

| Principle | Implementation |
|---|---|
| PII never reaches LLM | Presidio redaction gate — token→original map is in-process only, never persisted or returned via any API |
| Every decision is auditable | SHA-256 hash chain; each record's hash covers previous hash + payload + timestamp |
| Hard rules first, LLM only as fallback | `compliance_agent` fires CLM/UEBT rules deterministically; `rule_fired=True` skips LLM call |
| BankAdapter interface | All agents call `BankAdapter` ABC only; swap `MockBankAdapter` → `IDBISandboxAdapter` with one config change |
| LiteLLM as sole LLM gateway | Only `backend/app/llm/router.py` may call `litellm.acompletion()` — enforced by structural tests |

---

## Prerequisites

- **Docker & Docker Compose** (tested: Docker 26+)
- **Python 3.13** (for local dev / tests)
- **Node.js 20+** (for frontend local dev)
- macOS ARM: `brew install libomp` (required for XGBoost)

---

## Quick Start — Docker Compose (Recommended)

```bash
# 1. Clone and enter the repo
git clone <this-repo-url> veritas-fabric
cd veritas-fabric

# 2. Copy and configure environment
cp .env.example .env
# Edit .env: set GEMINI_API_KEY and/or OPENAI_API_KEY (see LLM_PRIMARY_MODEL / LLM_FALLBACK_MODEL)

# 3. Make sure Docker Desktop is running, then build and start everything
docker compose up --build

# First build takes ~10-15 min (XGBoost/spaCy/torch deps + spaCy model download).
# Subsequent runs are fast thanks to Docker layer caching.

# Services once healthy:
#   http://localhost:8000       FastAPI backend + Swagger docs (/docs)
#   http://localhost:5173       React frontend
#   http://localhost:6333       Qdrant vector DB (dashboard)
```

**Demo login:** `demo@idbi.bank` / `demo1234`

**Useful day-2 commands:**

```bash
docker compose up --build -d       # same as above, but detached
docker compose up -d --build backend    # rebuild+restart just the backend (needed after requirements.txt changes)
docker compose up -d --build frontend   # rebuild+restart just the frontend (needed after ANY frontend code change — it's a static Nginx build, no hot reload in Docker)
docker compose logs -f backend     # tail backend logs
docker compose ps                  # check service health
docker compose down                # stop and remove containers (add -v to also wipe volumes/data)
```

> Backend runs `uvicorn --reload` with `./backend` bind-mounted, so backend `.py` edits reload automatically without a rebuild. Frontend changes do NOT hot-reload in Docker — rebuild the `frontend` service after editing anything under `frontend/src`.

---

## Local Development Setup

### Backend

```bash
cd backend

# Create venv with Python 3.13 (important: not 3.14)
/opt/homebrew/bin/python3.13 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Download spaCy model (needed for Presidio NER)
python -m spacy download en_core_web_lg

# Start infrastructure only (Postgres, Valkey, Qdrant)
docker compose up postgres valkey qdrant -d

# Run backend
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

### Backend Tests

```bash
cd backend
pytest             # runs all tests
pytest tests/test_00_adapter_model.py -v   # fast smoke tests (no DB needed)
pytest tests/test_chain.py -v              # hash chain tests
```

> **Note on test ordering:** `test_00_adapter_model.py` must run before LangGraph is imported (prefixed `00_` so pytest collects it first). Presidio imports are lazy inside `RedactionGate.__init__()` to avoid an OpenMP conflict with XGBoost on macOS ARM.

---

## MCP Server (Claude Desktop Integration)

The MCP server exposes 4 banking tools so non-coding staff can use VERITAS directly from Claude Desktop without touching APIs.

### Install

```bash
cd mcp_server
pip install -r requirements.txt
```

### Configure Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "veritas-fabric": {
      "command": "python",
      "args": ["/absolute/path/to/veritas-fabric/mcp_server/server.py"],
      "env": {
        "VERITAS_BACKEND_URL": "http://localhost:8000",
        "VERITAS_API_KEY": ""
      }
    }
  }
}
```

Restart Claude Desktop. You'll see 4 tools available: **verify_identity**, **check_fraud_risk**, **ask_assistant**, **get_audit_trail**.

### Available MCP Tools

| Tool | Input | What it does |
|---|---|---|
| `verify_identity` | `customer_id` | KYC + risk tier + DID credential (no raw PII) |
| `check_fraud_risk` | `account_id` | XGBoost score + UEBT rule + trace |
| `ask_assistant` | `message` (+ optional context) | PII-redacted LLM chat with compliance outcome |
| `get_audit_trail` | `limit`, `verify_chain` | Hash-chain ledger + optional integrity check |

---

## Load Test

```bash
cd backend

# With backend running, run 50 concurrent users for 2 minutes
python load_test.py

# Custom settings
python load_test.py --url http://localhost:8000 --users 50 --duration 120

# Output: console table + backend/results.json
```

Expected output format:
```
────────────────────────────────────────────────────────────
Endpoint         Count    OK%    p50ms    p95ms    p99ms
────────────────────────────────────────────────────────────
assistant          842   98.1%    890.2   1820.3   2340.1
fraud             1203   99.8%    142.1    310.5    480.2
identity          1198   99.9%     98.3    210.7    380.1
────────────────────────────────────────────────────────────
ALL               3243   99.3%    280.4    980.1   1920.3
────────────────────────────────────────────────────────────
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PRIMARY_MODEL` | `openai/gpt-4o-mini` | Primary LiteLLM model string |
| `LLM_FALLBACK_MODEL` | `openai/gpt-3.5-turbo` | Fallback if primary fails |
| `LLM_API_KEY` | — | API key (OpenAI, Anthropic, etc.) |
| `POSTGRES_HOST` | `localhost` | Postgres host |
| `POSTGRES_PORT` | `5432` | Postgres port |
| `POSTGRES_USER` | `veritas` | Postgres user |
| `POSTGRES_PASSWORD` | `veritas_secret` | Postgres password |
| `POSTGRES_DB` | `veritas_db` | Database name |
| `VALKEY_HOST` | `localhost` | Valkey/Redis host |
| `VALKEY_PORT` | `6379` | Valkey port |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `JWT_SECRET_KEY` | `change-me-in-production` | JWT signing key |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXPIRE_MINUTES` | `480` | Token lifetime |

---

## Key Demo: Co-Lending in <2 Seconds

1. Open the **AI Assistant** page
2. Type: `Is CUST00001 eligible for co-lending? PAN: ABCDE1234F`
3. Watch the redaction panel — `ABCDE1234F` becomes `<IN_PAN>` before the LLM sees it
4. The response comes from the **CLM-001 hard rule** (`rule_fired=True` in the trace) — no LLM call needed
5. The decision is already in the **Audit Timeline** with a linked hash

This demonstrates the "Reconciliation to Real-Time" claim: co-lending eligibility is resolved by the VERITAS credential layer in <2 seconds vs 2-5 days of manual KYC reconciliation across lending partners.

---

## Project Structure

```
veritas-fabric/
├── backend/
│   ├── app/
│   │   ├── adapters/         # BankAdapter ABC + MockBankAdapter + IDBI stub
│   │   ├── agents/           # LangGraph graph, state, all agent nodes
│   │   ├── api/              # FastAPI routers (auth, identity, fraud, assistant, audit)
│   │   ├── ledger/           # SHA-256 chain.py + outbox.py
│   │   ├── llm/              # LiteLLM router (sole gateway to LLM APIs)
│   │   ├── ml/               # XGBoost fraud model + training script
│   │   ├── models/           # SQLAlchemy ORM models
│   │   └── redaction/        # Presidio gate.py (lazy imports, PII token mapping)
│   ├── tests/
│   ├── load_test.py          # 50-user concurrent load test → results.json
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/client.js     # Axios + JWT in module memory (not localStorage)
│   │   ├── components/       # Layout, Badge, TracePanel
│   │   └── pages/            # Login, Dashboard, Assistant, FraudAlerts, AuditTimeline
│   └── Dockerfile
├── mcp_server/
│   └── server.py             # MCP SDK server — 4 banking tools
├── seed_data/
│   ├── customers.json        # 10 synthetic customers (no real PII)
│   ├── accounts.json
│   ├── transactions.json     # 1,200 synthetic transactions
│   └── sample_policies/      # 5 IDBI policy markdown files for RAG
├── docker-compose.yml
└── .env.example
```

---

## Limitations & Honest Notes

- **Synthetic data only** — all customers, accounts, and transactions are procedurally generated. No real IDBI data.
- **XGBoost AUC 1.0** on test set — this is expected when synthetic features are engineered from labels. Real-world performance will differ.
- **Hash chain ≠ blockchain** — SHA-256 linking in Postgres is tamper-evident but not decentralized. Hyperledger Fabric integration would be the production path.
- **DID credentials** follow W3C VC 2.0 schema but are not registered on any ledger (`did:idbi:veritas-fabric-v1` is a prototype DID method).
- **IDBI Sandbox adapter** (`backend/app/adapters/idbi_adapter.py`) is a stub with endpoint paths documented. Real integration requires IDBI API credentials.

---

## Team

Team SentiCoders — IDBI Innovate 2026
Leader: Soham Walam
