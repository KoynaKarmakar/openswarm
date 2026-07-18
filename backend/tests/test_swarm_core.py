"""
Swarm runtime tests — pure, no heavy engine dependencies.

Verifies the Way-C hybrid guarantees:
  1. agents run in default order when they don't steer;
  2. an explicit handoff jumps to the named agent;
  3. Directive(halt=True) short-circuits straight to the terminal agent;
  4. the terminal (Auditor) agent ALWAYS runs exactly once, last;
  5. a handoff cycle is bounded by _MAX_STEPS and still terminates.
"""

from __future__ import annotations

import pytest

from app.swarm.context import SwarmContext
from app.swarm.core import Directive, Swarm


def _ctx() -> SwarmContext:
    return SwarmContext(request_id="req-1", request_type="ASSISTANT", raw_input="hi")


class _Recorder:
    """Minimal agent that records that it ran and returns a fixed directive."""

    def __init__(self, name: str, directive: Directive | None = None):
        self.name = name
        self._directive = directive or Directive()

    async def run(self, ctx: SwarmContext) -> Directive:
        ctx.set(f"ran_{self.name}", True)
        return self._directive


async def test_default_order_then_terminal():
    a = _Recorder("a")
    b = _Recorder("b")
    term = _Recorder("auditor")
    ctx = await Swarm([a, b], term).run(_ctx())

    assert ctx.handoff_path == ["a", "b", "auditor"]
    assert ctx.get("ran_a") and ctx.get("ran_b") and ctx.get("ran_auditor")


async def test_explicit_handoff_skips_middle():
    a = _Recorder("a", Directive(next_agent="c"))
    b = _Recorder("b")           # should be skipped
    c = _Recorder("c")
    term = _Recorder("auditor")
    ctx = await Swarm([a, b, c], term).run(_ctx())

    assert ctx.handoff_path == ["a", "c", "auditor"]
    assert ctx.get("ran_b") is None


async def test_halt_short_circuits_to_terminal():
    a = _Recorder("a", Directive(halt=True, reason="pii caught"))
    b = _Recorder("b")           # must not run
    term = _Recorder("auditor")
    ctx = await Swarm([a, b], term).run(_ctx())

    assert ctx.handoff_path == ["a", "auditor"]
    assert ctx.get("ran_b") is None
    assert any("short-circuited" in line for line in ctx.trace)


async def test_terminal_always_runs_once():
    a = _Recorder("a", Directive(halt=True))
    term = _Recorder("auditor")
    ctx = await Swarm([a], term).run(_ctx())

    assert ctx.handoff_path.count("auditor") == 1


async def test_handoff_cycle_is_bounded():
    # a → b → a → b … must not hang; terminal still runs.
    a = _Recorder("a", Directive(next_agent="b"))
    b = _Recorder("b", Directive(next_agent="a"))
    term = _Recorder("auditor")
    ctx = await Swarm([a, b], term).run(_ctx())

    assert ctx.handoff_path[-1] == "auditor"
    assert any("MAX_STEPS" in line for line in ctx.trace)


async def test_terminal_cannot_be_in_dynamic_zone():
    dup = _Recorder("auditor")
    with pytest.raises(ValueError):
        Swarm([dup], _Recorder("auditor"))


async def test_absorb_merges_trace_and_vars():
    ctx = _ctx()
    ctx.log("first")
    ctx.absorb({"trace": ["from node"], "identity_result": {"outcome": "APPROVED"}})

    assert ctx.trace == ["first", "from node"]
    assert ctx.get("identity_result") == {"outcome": "APPROVED"}
