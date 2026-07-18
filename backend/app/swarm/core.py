"""
The Swarm conductor and the agent contract.

Topology (Way C — hybrid):

    entry ─▶ [ dynamic zone: agents hand off to each other ] ─▶ terminal (always)

  * Agents in the dynamic zone steer routing by returning a `Directive`:
      - `Directive()`                    → proceed to the next agent in order
      - `Directive(next_agent="knowledge")` → explicit handoff (Swarm-style)
      - `Directive(halt=True)`           → short-circuit straight to the terminal
                                           agent (e.g. Guardrail catches PII /
                                           prompt-injection and skips the rest)
  * The `terminal` agent (the Auditor) ALWAYS runs exactly once, last, no matter
    how the dynamic zone exits. This is what preserves the "every decision is
    logged" guarantee that the LangGraph design enforced via `decision_coordinator`.

The conductor performs no LLM calls itself; agents that need reasoning call
`app.llm.router.chat_completion`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.swarm.context import SwarmContext

logger = logging.getLogger("veritas.swarm")

# Safety valve: the dynamic zone cannot execute more agent steps than this,
# guarding against a handoff cycle (agent A → B → A → …).
_MAX_STEPS = 16


@dataclass
class Directive:
    """What an agent returns to steer the conductor."""
    next_agent: str | None = None   # explicit handoff target by agent name
    halt: bool = False              # short-circuit: jump straight to the terminal agent
    reason: str = ""                # human-readable why, for the trace


@runtime_checkable
class SwarmAgent(Protocol):
    """The contract every swarm agent implements."""
    name: str

    async def run(self, ctx: SwarmContext) -> Directive: ...


class Swarm:
    """
    Conductor for the dynamic zone + the deterministic terminal agent.

    Parameters
    ----------
    agents : list[SwarmAgent]
        The dynamic-zone agents, in default execution order.
    terminal : SwarmAgent
        Always runs last (the Auditor). Never part of the dynamic order.
    """

    def __init__(self, agents: list[SwarmAgent], terminal: SwarmAgent):
        if not agents:
            raise ValueError("Swarm needs at least one dynamic-zone agent")
        self._order = [a.name for a in agents]
        self._by_name = {a.name: a for a in agents}
        if terminal.name in self._by_name:
            raise ValueError(
                f"terminal agent '{terminal.name}' must not also be in the dynamic zone"
            )
        self._terminal = terminal

    def _next_in_order(self, current: str) -> str | None:
        idx = self._order.index(current)
        return self._order[idx + 1] if idx + 1 < len(self._order) else None

    async def run(self, ctx: SwarmContext) -> SwarmContext:
        """Execute the swarm end-to-end, mutating and returning `ctx`."""
        current: str | None = self._order[0]
        steps = 0

        while current is not None:
            if steps >= _MAX_STEPS:
                ctx.log(f"swarm: MAX_STEPS ({_MAX_STEPS}) exceeded — forcing terminal")
                logger.warning("Swarm exceeded max steps for request %s", ctx.request_id)
                break

            agent = self._by_name[current]
            ctx.handoff_path.append(agent.name)
            steps += 1

            directive = await agent.run(ctx)

            if directive.halt:
                ctx.log(
                    f"swarm: '{agent.name}' short-circuited → terminal"
                    + (f" ({directive.reason})" if directive.reason else "")
                )
                break

            if directive.next_agent:
                if directive.next_agent not in self._by_name:
                    ctx.log(
                        f"swarm: '{agent.name}' requested unknown handoff "
                        f"'{directive.next_agent}' — falling through to order"
                    )
                    current = self._next_in_order(current)
                else:
                    ctx.log(f"swarm: '{agent.name}' → '{directive.next_agent}'")
                    current = directive.next_agent
                continue

            current = self._next_in_order(current)

        # Deterministic tail — always runs exactly once, last.
        ctx.handoff_path.append(self._terminal.name)
        await self._terminal.run(ctx)
        return ctx
