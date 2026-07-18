"""
OpenAI-Swarm types, faithful to github.com/openai/swarm (swarm/types.py).

Same fields as the upstream Pydantic models, as dataclasses (functions are plain
Python callables, so no arbitrary-type config is needed). An agent function may
return: a value (stringified), a dict (merged into context_variables via Result),
an Agent (handoff), or a Result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# An agent function is any callable; it may accept a `context_variables` kwarg,
# which the Swarm injects at call time (and strips from the tool schema).
AgentFunction = Callable


@dataclass
class Agent:
    name: str = "Agent"
    model: str = "gemini/gemini-2.5-flash"
    instructions: str | Callable = "You are a helpful agent."
    functions: list = field(default_factory=list)
    tool_choice: str | None = None
    parallel_tool_calls: bool = True


@dataclass
class Result:
    """
    Encapsulates the possible return values for an agent function.

    value              : the result value as a string.
    agent              : the agent to hand off to, if any.
    context_variables  : a dict merged into the run's shared context.
    """
    value: str = ""
    agent: "Agent | None" = None
    context_variables: dict = field(default_factory=dict)


@dataclass
class Response:
    messages: list = field(default_factory=list)
    agent: "Agent | None" = None
    context_variables: dict = field(default_factory=dict)
