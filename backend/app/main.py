import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import AsyncSessionLocal, engine, Base
from app.redaction.gate import get_redaction_gate

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("veritas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── DB tables (dev: create_all; prod: use Alembic) ──────────────────────
    # Import every model module so its table is registered on Base.metadata
    # before create_all runs.
    from app.models import account, audit, case, decision, transaction, user  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── Demo user seeding (creates demo@idbi.bank / demo1234 if absent) ──────
    from sqlalchemy import select as _select
    from app.models.user import User, UserRole
    from app.auth.jwt import hash_password
    async with AsyncSessionLocal() as _db:
        async with _db.begin():
            existing = await _db.execute(_select(User).where(User.email == "demo@idbi.bank"))
            demo_user = existing.scalar_one_or_none()
            if demo_user is None:
                # role=STAFF so the demo login can exercise the case-override
                # control (gated to STAFF/MANAGER/ADMIN) out of the box.
                _db.add(User(
                    email="demo@idbi.bank", hashed_password=hash_password("demo1234"),
                    full_name="Demo User", role=UserRole.STAFF,
                ))
                logger.info("Demo user created: demo@idbi.bank (role=STAFF)")
            elif demo_user.role == UserRole.CUSTOMER:
                demo_user.role = UserRole.STAFF
                logger.info("Demo user role upgraded to STAFF")

    # ── Redaction gate (warms up spaCy model) ────────────────────────────────
    logger.info("Warming up redaction gate...")
    gate = get_redaction_gate()
    app.state.redaction_gate = gate

    # ── Bank adapter ──────────────────────────────────────────────────────────
    from app.adapters.mock_adapter import MockBankAdapter
    adapter = MockBankAdapter()
    app.state.bank_adapter = adapter

    # ── Valkey (Redis-compatible cache) ───────────────────────────────────────
    valkey = aioredis.from_url(settings.valkey_url, decode_responses=True)
    app.state.valkey = valkey

    # ── Qdrant RAG client + policy ingestion ─────────────────────────────────
    try:
        from app.rag.qdrant_client import get_qdrant_client
        from app.rag.ingest_policies import ingest_on_startup
        qdrant = get_qdrant_client()
        await ingest_on_startup(qdrant)
        app.state.qdrant_client = qdrant
    except Exception as exc:
        logger.warning("Qdrant unavailable at startup — policy RAG disabled: %s", exc)
        app.state.qdrant_client = None

    # ── Data memory ingestion (customers, accounts, risk profiles → Qdrant) ──
    if app.state.qdrant_client is not None:
        try:
            from app.memory.ingester import ingest_data_on_startup
            await ingest_data_on_startup(app.state.qdrant_client)
        except Exception as exc:
            logger.warning("Data memory ingestion failed: %s", exc)

    # ── Circular compliance gate (ingests circulars + builds gate) ────────────
    app.state.circular_gate = None
    if app.state.qdrant_client is not None:
        try:
            from app.circulars.ingester import ingest_circulars_on_startup
            from app.circulars.gate import CircularComplianceGate
            circular_store = await ingest_circulars_on_startup(app.state.qdrant_client)
            if circular_store is not None:
                app.state.circular_gate = CircularComplianceGate(circular_store)
                logger.info("Circular compliance gate ready")
        except Exception as exc:
            logger.warning("Circular gate unavailable: %s", exc)

    # ── Fraud model warm-up ───────────────────────────────────────────────────
    try:
        from app.ml.fraud_model import get_fraud_model
        get_fraud_model()
    except Exception as exc:
        logger.warning("Fraud model unavailable: %s", exc)

    # ── LangGraph agent graph ─────────────────────────────────────────────────
    from app.agents.graph import build_graph
    async with AsyncSessionLocal() as db:
        graph = build_graph(
            gate=gate,
            adapter=adapter,
            valkey=valkey,
            db=db,
            qdrant=app.state.qdrant_client,
            circular_gate=app.state.circular_gate,
        )
    app.state.agent_graph = graph

    # ── Outbox worker (background asyncio task) ───────────────────────────────
    from app.ledger.outbox import run_outbox_worker
    outbox_task = asyncio.create_task(run_outbox_worker(AsyncSessionLocal))
    logger.info("VERITAS Fabric ready")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    outbox_task.cancel()
    try:
        await outbox_task
    except asyncio.CancelledError:
        pass
    await valkey.aclose()
    await engine.dispose()


app = FastAPI(
    title="VERITAS Fabric API",
    description="AI Trust Middleware for Banking — compliance-first, explainable, audit-logged",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Route registration ────────────────────────────────────────────────────────
from app.api.routes_auth import router as auth_router
from app.api.routes_identity import router as identity_router
from app.api.routes_fraud import router as fraud_router
from app.api.routes_assistant import router as assistant_router
from app.api.routes_audit import router as audit_router
from app.api.routes_circulars import router as circulars_router
from app.api.routes_cases import router as cases_router
from app.api.routes_policy import router as policy_router

app.include_router(auth_router)
app.include_router(identity_router)
app.include_router(fraud_router)
app.include_router(assistant_router)
app.include_router(audit_router)
app.include_router(circulars_router)
app.include_router(cases_router)
app.include_router(policy_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "veritas-fabric"}
