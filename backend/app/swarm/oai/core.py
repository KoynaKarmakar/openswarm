"""
Swarm — faithful to github.com/openai/swarm (swarm/core.py), adapted for VERITAS:

  * async (our engines + router are async);
  * the LLM call goes through `app.llm.router.acompletion_with_tools` instead of
    the OpenAI client directly — so the single-LLM-chokepoint rule holds
    (test_no_llm_bypass.py). The completion fn is injectable for tests.

The control flow matches upstream exactly:
  run(agent, messages, context_variables) loops up to max_turns:
    1. get_chat_completion(active_agent, history, context_variables)
    2. append the assistant message to history
    3. if no tool_calls (or execute_tools=False) → stop
    4. handle_tool_calls → run each function, merge context_variables, and if a
       function returned an Agent, switch the active agent (handoff)
  returns Response(messages, agent, context_variables).
"""

from __future__ import annotations

import copy
import inspect
import json
from collections import defaultdict

from app.swarm.oai.types import Agent, Response, Result
from app.swarm.oai.util import debug_print, function_to_json

__CTX_VARS_NAME__ = "context_variables"


async def _router_completion(*, model, messages, tools, tool_choice, parallel_tool_calls):
    """Default completion — routes through the sanctioned litellm chokepoint."""
    from app.llm.router import acompletion_with_tools

    return await acompletion_with_tools(
        model=model, messages=messages, tools=tools,
        tool_choice=tool_choice, parallel_tool_calls=parallel_tool_calls,
    )


def _message_to_dict(message, sender: str) -> dict:
    """Serialize a provider (or fake) message into a history dict."""
    if hasattr(message, "model_dump"):
        d = message.model_dump()
    elif isinstance(message, dict):
        d = dict(message)
    else:
        d = {"role": "assistant", "content": getattr(message, "content", None)}
        tcs = getattr(message, "tool_calls", None)
        if tcs:
            d["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tcs
            ]
    d.setdefault("role", "assistant")
    d["sender"] = sender
    return d


class Swarm:
    def __init__(self, completion=None):
        """completion: async fn(model, messages, tools, tool_choice,
        parallel_tool_calls) -> message. Defaults to the router chokepoint."""
        self._completion = completion or _router_completion

    async def get_chat_completion(self, agent: Agent, history, context_variables, model_override, debug):
        context_variables = defaultdict(str, context_variables)
        instructions = agent.instructions(context_variables) if callable(agent.instructions) else agent.instructions
        messages = [{"role": "system", "content": instructions}, *history]
        debug_print(debug, "Getting chat completion for:", agent.name)

        tools = [function_to_json(f) for f in agent.functions]
        # hide context_variables from the model — it's injected by us, not the LLM
        for tool in tools:
            params = tool["function"]["parameters"]
            params["properties"].pop(__CTX_VARS_NAME__, None)
            if __CTX_VARS_NAME__ in params["required"]:
                params["required"].remove(__CTX_VARS_NAME__)

        return await self._completion(
            model=model_override or agent.model,
            messages=messages,
            tools=tools or None,
            tool_choice=agent.tool_choice,
            parallel_tool_calls=agent.parallel_tool_calls,
        )

    def handle_function_result(self, result, debug) -> Result:
        if isinstance(result, Result):
            return result
        if isinstance(result, Agent):
            return Result(value=json.dumps({"assistant": result.name}), agent=result)
        try:
            return Result(value=str(result))
        except Exception as e:  # pragma: no cover
            raise TypeError(f"Failed to cast response to string: {result}. {e}")

    async def handle_tool_calls(self, tool_calls, functions, context_variables, debug) -> Response:
        function_map = {f.__name__: f for f in functions}
        partial_response = Response(messages=[], agent=None, context_variables={})

        for tool_call in tool_calls:
            name = tool_call.function.name
            if name not in function_map:
                debug_print(debug, f"Tool {name} not found in function map.")
                partial_response.messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "tool_name": name,
                     "content": f"Error: Tool {name} not found."})
                continue

            args = json.loads(tool_call.function.arguments or "{}")
            func = function_map[name]
            # inject context_variables if the function declares it
            if __CTX_VARS_NAME__ in func.__code__.co_varnames:
                args[__CTX_VARS_NAME__] = context_variables

            raw_result = func(**args)
            if inspect.isawaitable(raw_result):
                raw_result = await raw_result
            result = self.handle_function_result(raw_result, debug)

            partial_response.messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "tool_name": name, "content": result.value})
            partial_response.context_variables.update(result.context_variables)
            if result.agent:
                partial_response.agent = result.agent

        return partial_response

    async def run(self, agent: Agent, messages, context_variables=None, model_override=None,
                  debug=False, max_turns=float("inf"), execute_tools=True) -> Response:
        active_agent = agent
        context_variables = copy.deepcopy(context_variables or {})
        history = copy.deepcopy(messages)
        init_len = len(messages)

        while len(history) - init_len < max_turns and active_agent:
            message = await self.get_chat_completion(active_agent, history, context_variables, model_override, debug)
            history.append(_message_to_dict(message, active_agent.name))

            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls or not execute_tools:
                debug_print(debug, "Ending turn.")
                break

            partial_response = await self.handle_tool_calls(tool_calls, active_agent.functions, context_variables, debug)
            history.extend(partial_response.messages)
            context_variables.update(partial_response.context_variables)
            if partial_response.agent:
                active_agent = partial_response.agent

        return Response(messages=history[init_len:], agent=active_agent, context_variables=context_variables)
