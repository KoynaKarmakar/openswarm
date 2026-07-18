"""
function_to_json — faithful to github.com/openai/swarm (swarm/util.py).

Introspects a Python function's signature and turns it into the JSON tool schema
the model needs to call it.
"""

from __future__ import annotations

import inspect


def function_to_json(func) -> dict:
    """Convert a Python function into a JSON-serializable tool schema."""
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    try:
        signature = inspect.signature(func)
    except ValueError as e:  # pragma: no cover
        raise ValueError(f"Failed to get signature for function {func.__name__}: {e}")

    parameters = {}
    for param in signature.parameters.values():
        try:
            param_type = type_map.get(param.annotation, "string")
        except KeyError as e:  # pragma: no cover
            raise KeyError(f"Unknown type annotation {param.annotation} for parameter {param.name}: {e}")
        parameters[param.name] = {"type": param_type}

    required = [p.name for p in signature.parameters.values() if p.default == inspect._empty]

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": (func.__doc__ or "").strip(),
            "parameters": {"type": "object", "properties": parameters, "required": required},
        },
    }


def debug_print(debug: bool, *args) -> None:
    if debug:
        print("\033[97m[\033[90mSWARM\033[97m]\033[90m", *args, "\033[0m")
