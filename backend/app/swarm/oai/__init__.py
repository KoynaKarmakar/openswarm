"""
OpenAI-Swarm-style engine for VERITAS — faithful to github.com/openai/swarm,
routed through the litellm chokepoint (app/llm/router.py).

  Swarm.run(agent, messages, context_variables) drives an LLM that calls the
  agent's functions and hands off by returning other Agents.
"""

from app.swarm.oai.core import Swarm
from app.swarm.oai.types import Agent, Response, Result
from app.swarm.oai.util import function_to_json

__all__ = ["Swarm", "Agent", "Response", "Result", "function_to_json"]
