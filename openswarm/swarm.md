---
name: veritas-trust-swarm
description: AI trust middleware for banking co-lending decisions — PII-safe, grounded, audited
entrypoint: guardrail
terminal: auditor
agents:
  - agents/guardrail.md
  - agents/knowledge.md
  - agents/identity_fraud.md
  - agents/auditor.md
runtime:
  backend: ../backend            # Python tools live here (import root: app.*)
  shared_context: VeritasState   # see app/swarm/context.py
---

# VERITAS Trust Swarm

Four specialized agents pass context dynamically. The Guardrail is the entry
point; the Auditor is the deterministic terminal that always runs last.

```
[request] → 🛡️ guardrail → 🔍 knowledge → 👤 identity_fraud → 📜 auditor (always)
                 │ halt (PII / injection / non-compliant) ──────────────┘
```

## Shared context (what agents pass)

Keyed to `app/swarm/context.py::SwarmContext.vars` (VeritasState-compatible):
`redacted_input`, `entity_map`, `identity_result`, `fraud_result`,
`compliance_result`, `policy_result`, `llm_response`, plus an append-only
`trace` and the `handoff_path`. The raw input and the PII mapping are request-
scoped and never enter the shared context.

## Guarantees the runtime must preserve

1. **Single LLM chokepoint** — every model call goes through
   `app.llm.router:chat_completion`. No agent calls a provider SDK directly.
2. **Auditor always runs** — even when Guardrail short-circuits, the terminal
   agent runs and writes the hash-chain ledger entry.
3. **PII never reaches the LLM** — only redacted/entity-labelled context does.

## Reference implementation

This manifest describes the same topology already implemented and tested in
Python at `backend/app/swarm/` (`orchestrator.build_swarm()` + `core.Swarm`),
with 79 passing tests. If you run the swarm purely inside OpenSwarm's own
runtime, these agent prompts drive it; if you run the Python swarm, the agents
above map 1:1 to the classes in `backend/app/swarm/agents/`.
