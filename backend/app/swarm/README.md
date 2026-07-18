# VERITAS OpenSwarm layer

Router-compliant realization of the **OpenAI Swarm** handoff pattern. It replaces
the static LangGraph conductor (`app/agents/graph.py`) with **dynamic, handoff-based
orchestration** while keeping every existing engine (redaction, RAG, XGBoost fraud,
hash-chain ledger) untouched.

## Way C — hybrid

```
entry ─▶ [ DYNAMIC ZONE: agents hand off at runtime ] ─▶ TERMINAL (always runs)

  🛡️ guardrail  ─▶  🔍 knowledge  ─▶  👤 identity_fraud  ─▶  📜 auditor
       │ halt=True (PII / injection / NON_COMPLIANT catch)          ▲
       └────────────────────────── short-circuit ───────────────────┘
```

* **Dynamic zone** — agents steer routing by returning a `Directive`
  (`next_agent=…` for an explicit handoff, `halt=True` to short-circuit).
* **Deterministic tail** — the Auditor is the Swarm *terminal* agent and **always
  runs exactly once, last**. This preserves the "every decision is logged"
  guarantee the LangGraph design enforced via `decision_coordinator`.

## Swarm-concept mapping

| OpenAI Swarm         | Here                                   |
|----------------------|----------------------------------------|
| `Agent`              | `SwarmAgent` (`core.py`)               |
| handoff / fn→Agent   | `Directive(next_agent=…)` (`core.py`)  |
| `context_variables`  | `SwarmContext.vars` (`context.py`)     |
| `client.run(...)`    | `Swarm.run(ctx)` (`core.py`)           |

## LLM chokepoint (unchanged rule)

The conductor performs **no** LLM calls. Any agent that needs reasoning calls
`app.llm.router.chat_completion`, keeping the provider SDK call isolated to
`app/llm/router.py` (enforced by `tests/test_no_llm_bypass.py`).

## Reusing the existing engine nodes

`SwarmContext` is keyed to match `VeritasState`, so an agent can drive a legacy
node directly:

```python
delta = await identity_node(ctx.snapshot_state(), adapter)
ctx.absorb(delta)   # merges trace (append) + results (overwrite) back in
```

## Files

| File                         | Role                                              |
|------------------------------|---------------------------------------------------|
| `core.py`                    | `Swarm` conductor, `SwarmAgent`, `Directive`      |
| `context.py`                 | `SwarmContext` (shared state + trace bridge)      |
| `orchestrator.py`            | `build_swarm(...)` — the DI assembly point        |
| `agents/guardrail.py`        | 🛡️ PII redaction + injection + hard compliance    |
| `agents/knowledge.py`        | 🔍 grounded Qdrant RAG                             |
| `agents/identity_fraud.py`   | 👤 identity + XGBoost fraud + Google Verifiable Credentials |
| `agents/auditor.py`          | 📜 confidence score + hash-chain ledger write     |

## Branch plan

Base branch ships the runtime + placeholder agents (this commit). Each agent is
implemented on its own feature branch off the base:
`agent-guardrail`, `agent-knowledge`, `agent-identity-fraud`, `agent-auditor`.
