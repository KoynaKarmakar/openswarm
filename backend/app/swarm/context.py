"""
SwarmContext — the shared object every agent reads from and writes to.

This is the Swarm equivalent of `context_variables`, adapted to VERITAS:
  * `vars`         holds the agent results (identity_result, fraud_result, …),
                   keyed exactly like `VeritasState` so existing engine nodes
                   can be reused without rewriting them.
  * `trace`        is append-only — the Explainable-AI output. No node overwrites
                   another node's trace lines.
  * `handoff_path` records which agents ran, in order, so the Auditor can prove
                   the request traversed the swarm (and where it short-circuited).

PII rule (unchanged from the LangGraph design):
  raw_input is set once at entry and never sent to an LLM. Only `redacted_input`
  (produced by the Guardrail agent) and the non-PII agent results are ever passed
  to `router.chat_completion`. The token→original mapping is never stored here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SwarmContext:
    # ── Input (set once at entry) ────────────────────────────────────────────
    request_id: str
    request_type: str                      # FRAUD_CHECK | IDENTITY | COMPLIANCE | ASSISTANT
    raw_input: str                         # user's original text — never sent to an LLM
    user_id: str | None = None
    account_id: str | None = None
    transaction_id: str | None = None
    extra_context: dict = field(default_factory=dict)

    # ── Shared mutable context (Swarm "context_variables") ───────────────────
    # Keyed to match VeritasState (redacted_input, identity_result, fraud_result,
    # compliance_result, policy_result, entity_map, …) so engine nodes drop in.
    vars: dict[str, Any] = field(default_factory=dict)

    # ── Explainability ───────────────────────────────────────────────────────
    trace: list[str] = field(default_factory=list)      # append-only
    handoff_path: list[str] = field(default_factory=list)

    # ── Convenience accessors ────────────────────────────────────────────────
    def log(self, message: str) -> None:
        """Append one line to the append-only trace."""
        self.trace.append(message)

    def set(self, key: str, value: Any) -> None:
        self.vars[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.vars.get(key, default)

    # ── Bridge to the existing VeritasState-based engine nodes ───────────────
    def snapshot_state(self) -> dict:
        """
        Produce a VeritasState-compatible dict for a legacy engine node.

        `trace` is intentionally emptied in the snapshot: engine nodes return
        their own trace lines, which we merge back via `absorb()` — this keeps
        the trace append-only and avoids duplicating earlier lines.
        """
        return {
            "request_id": self.request_id,
            "request_type": self.request_type,
            "raw_input": self.raw_input,
            "user_id": self.user_id,
            "account_id": self.account_id,
            "transaction_id": self.transaction_id,
            "extra_context": self.extra_context,
            "trace": [],
            **self.vars,
        }

    def absorb(self, delta: dict | None) -> None:
        """
        Merge an engine node's return dict back into the context.

        `trace` entries are appended (never replaced); everything else is a
        straight key overwrite into `vars`, exactly how LangGraph merges a
        node's partial-state return.
        """
        if not delta:
            return
        for key, value in delta.items():
            if key == "trace" and isinstance(value, list):
                self.trace.extend(value)
            else:
                self.vars[key] = value
