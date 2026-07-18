"""
VERITAS LLM Router — the ONLY file in the codebase allowed to call litellm.

Every call to litellm.acompletion() must go through `chat_completion()` here.
test_no_llm_bypass.py greps for raw litellm calls outside this file and fails
the test suite if any are found.

The router:
1. Accepts already-redacted messages (caller's responsibility — enforced by tests).
2. Tries the primary model (Gemini 2.5).
3. Falls back to the secondary model (OpenAI GPT-4o-mini) on any error.
4. Records which model was actually used so the trace is accurate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import get_settings

logger = logging.getLogger("veritas.llm")
settings = get_settings()


@dataclass
class LLMResponse:
    content: str
    model_used: str
    input_tokens: int
    output_tokens: int


async def chat_completion(
    messages: list[dict],
    *,
    temperature: float = 0.1,
    max_tokens: int = 1024,
) -> LLMResponse:
    """
    Send pre-redacted messages to the LLM.

    messages must already have PII replaced with entity-type labels.
    This function does NOT call the redaction gate — the graph node
    (llm_call_node in graph.py) is responsible for passing redacted_input.

    Raises RuntimeError if both primary and fallback models fail.
    """
    import litellm  # deferred import — not available in test environment without API keys

    litellm.drop_params = True  # ignore unsupported params per model

    for model in [settings.llm_primary_model, settings.llm_fallback_model]:
        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or ""
            usage = response.usage or {}
            logger.info("LLM call succeeded via %s (%d output tokens)", model, usage.get("completion_tokens", 0))
            return LLMResponse(
                content=content,
                model_used=model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed for model %s: %s — trying next", model, exc)

    raise RuntimeError(
        f"All LLM models failed. Primary: {settings.llm_primary_model}, "
        f"Fallback: {settings.llm_fallback_model}"
    )


async def acompletion_with_tools(
    *,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str | None = "auto",
    temperature: float = 0.7,
    parallel_tool_calls: bool = True,
):
    """
    Function-calling completion for the OpenAI-Swarm engine (app/swarm/oai/core.py).

    Returns the raw provider message (OpenAI-compatible: `.content` and
    `.tool_calls`). This is the ONLY place litellm is called with tools — the
    Swarm loop must never call a provider SDK directly (test_no_llm_bypass.py).

    Callers pass already-redacted `messages`.
    """
    import litellm  # deferred — not available without API keys in test env

    litellm.drop_params = True
    params: dict = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        params["tools"] = tools
        params["tool_choice"] = tool_choice or "auto"
        params["parallel_tool_calls"] = parallel_tool_calls
    response = await litellm.acompletion(**params)
    return response.choices[0].message
