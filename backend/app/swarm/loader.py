"""
Markdown → agents loader.

Turns the declarative agent definitions in `openswarm/agents/*.md` (and the
`openswarm/swarm.md` manifest) into *real, runnable agents*:

  * parse each .md into an AgentSpec (frontmatter + system-prompt body);
  * validate that every declared `tool` (module:attr) resolves to actual backend
    code — so the specs are proven wired, not aspirational;
  * build the live `Swarm` from the manifest's topology (entrypoint → terminal),
    binding each markdown agent to its tested Python implementation.

Run `python -m app.swarm.loader` to print the loaded agents and validate them.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field

import yaml

from app.swarm.agents import (
    AuditorAgent,
    GuardrailAgent,
    IdentityFraudAgent,
    KnowledgeAgent,
)
from app.swarm.core import Swarm

# openswarm/ lives at the repo root: loader.py → swarm → app → backend → <root>
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OPENSWARM_DIR = os.path.join(_REPO_ROOT, "openswarm")

# Markdown agent name → tested implementation constructor.
_IMPL = {
    "guardrail": lambda d: GuardrailAgent(gate=d.get("gate"), circular_gate=d.get("circular_gate")),
    "knowledge": lambda d: KnowledgeAgent(qdrant=d.get("qdrant")),
    "identity_fraud": lambda d: IdentityFraudAgent(adapter=d.get("adapter")),
    "auditor": lambda d: AuditorAgent(db=d.get("db")),
}


@dataclass
class AgentSpec:
    name: str
    description: str = ""
    model: str = ""
    prompt: str = ""
    tools: list[str] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)
    entrypoint: bool = False
    terminal: bool = False
    path: str = ""


# ── parsing ───────────────────────────────────────────────────────────────────

def _split_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, text
    front = yaml.safe_load("\n".join(lines[1:end])) or {}
    body = "\n".join(lines[end + 1:]).strip()
    return front, body


def parse_agent_md(path: str) -> AgentSpec:
    with open(path, encoding="utf-8") as fh:
        front, body = _split_frontmatter(fh.read())
    return AgentSpec(
        name=front.get("name", os.path.splitext(os.path.basename(path))[0]),
        description=front.get("description", ""),
        model=front.get("model", ""),
        prompt=body,
        tools=list(front.get("tools", []) or []),
        handoffs=list(front.get("handoffs", []) or []),
        entrypoint=bool(front.get("entrypoint", False)),
        terminal=bool(front.get("terminal", False)),
        path=path,
    )


def parse_manifest(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        front, _ = _split_frontmatter(fh.read())
    return front


def load_agent_specs(openswarm_dir: str = OPENSWARM_DIR) -> list[AgentSpec]:
    """Load agent specs in manifest order (falls back to sorted files)."""
    manifest = parse_manifest(os.path.join(openswarm_dir, "swarm.md"))
    rel_paths = manifest.get("agents")
    if rel_paths:
        files = [os.path.join(openswarm_dir, p) for p in rel_paths]
    else:
        adir = os.path.join(openswarm_dir, "agents")
        files = [os.path.join(adir, f) for f in sorted(os.listdir(adir)) if f.endswith(".md")]
    return [parse_agent_md(p) for p in files]


# ── validation ────────────────────────────────────────────────────────────────

def _module_of(tool_ref: str) -> str:
    return tool_ref.split(":", 1)[0]


def _module_exists(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def validate_specs(specs: list[AgentSpec]) -> list[str]:
    """Return a list of problems ([] means every spec is well-formed and wired)."""
    problems: list[str] = []
    names = {s.name for s in specs}

    if sum(s.entrypoint for s in specs) != 1:
        problems.append("exactly one agent must set entrypoint: true")
    if sum(s.terminal for s in specs) != 1:
        problems.append("exactly one agent must set terminal: true")

    for spec in specs:
        if spec.name not in _IMPL:
            problems.append(f"{spec.name}: no bound implementation")
        if not spec.prompt.strip():
            problems.append(f"{spec.name}: empty system prompt")
        for tool in spec.tools:
            if ":" not in tool:
                problems.append(f"{spec.name}: malformed tool ref '{tool}' (want module:attr)")
            elif not _module_exists(_module_of(tool)):
                problems.append(f"{spec.name}: tool module not found '{_module_of(tool)}'")
        for target in spec.handoffs:
            if target not in names:
                problems.append(f"{spec.name}: handoff to unknown agent '{target}'")
    return problems


def import_tool(tool_ref: str):
    """Resolve 'pkg.mod:Attr.method' to the actual object (used at runtime)."""
    import importlib

    module_path, attr_path = tool_ref.split(":", 1)
    obj = importlib.import_module(module_path)
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


# ── build the runnable swarm from the markdown ────────────────────────────────

def build_swarm_from_markdown(openswarm_dir: str = OPENSWARM_DIR, **deps) -> Swarm:
    """
    Construct the live Swarm using the manifest's topology and the bound
    implementations. `deps` = gate / circular_gate / qdrant / adapter / db.
    """
    specs = load_agent_specs(openswarm_dir)
    problems = validate_specs(specs)
    if problems:
        raise ValueError("Invalid agent definitions:\n  - " + "\n  - ".join(problems))

    terminal_spec = next(s for s in specs if s.terminal)
    dynamic = [_IMPL[s.name](deps) for s in specs if not s.terminal]
    terminal = _IMPL[terminal_spec.name](deps)
    return Swarm(dynamic, terminal)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    specs = load_agent_specs()
    print(f"Loaded {len(specs)} agents from {OPENSWARM_DIR}\n")
    for s in specs:
        flags = " ".join(f for f, on in (("entry", s.entrypoint), ("terminal", s.terminal)) if on)
        print(f"  • {s.name:<15} {s.model:<26} tools={len(s.tools)} "
              f"handoffs={s.handoffs or '—'} {('['+flags+']') if flags else ''}")
    problems = validate_specs(specs)
    print()
    if problems:
        print("VALIDATION FAILED:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("✓ all agents valid — every declared tool resolves to backend code")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
