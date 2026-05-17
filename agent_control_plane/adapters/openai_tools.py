from __future__ import annotations

import inspect
from typing import Any, Callable, get_args, get_origin

from agent_control_plane.gateway import AgentControlPlane
from agent_control_plane.models import ToolCard


def _json_type(annotation: Any) -> str:
    if annotation in {str, inspect._empty}:
        return "string"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    origin = get_origin(annotation)
    if origin in {list, tuple, set}:
        return "array"
    if origin is dict:
        return "object"
    return "string"


def _schema_for_annotation(annotation: Any) -> dict[str, Any]:
    json_type = _json_type(annotation)
    schema: dict[str, Any] = {"type": json_type}
    origin = get_origin(annotation)
    if json_type == "array":
        args = get_args(annotation)
        schema["items"] = _schema_for_annotation(args[0]) if args else {"type": "string"}
    return schema


def to_openai_tool_schema(fn: Callable[..., Any], card: ToolCard | None = None) -> dict[str, Any]:
    """Generate a generic OpenAI-compatible function tool schema.

    This avoids importing the OpenAI SDK and keeps the package framework-neutral.
    """
    card = card or getattr(fn, "__tool_card__", None)
    name = card.name if card else fn.__name__
    description = card.description if card else (fn.__doc__ or fn.__name__).strip()
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in sig.parameters.items():
        if param.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            continue
        properties[param_name] = _schema_for_annotation(param.annotation)
        if param.default is inspect._empty:
            required.append(param_name)
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def wrap_openai_tool_executor(
    control_plane: AgentControlPlane,
    *,
    agent_id: str,
    user_id: str | None = None,
    run_id: str | None = None,
    context: dict[str, Any] | None = None,
    idempotency_key_fn: Callable[[str, dict[str, Any]], str | None] | None = None,
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Return a small executor for OpenAI-style function calls.

    Usage in a model loop:
        execute = wrap_openai_tool_executor(cp, agent_id="support-agent")
        result = execute(call.name, json.loads(call.arguments))
    """

    def execute(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return control_plane.execute_tool(
            agent_id=agent_id,
            tool_name=tool_name,
            args=args,
            user_id=user_id,
            run_id=run_id,
            idempotency_key=idempotency_key_fn(tool_name, args) if idempotency_key_fn else None,
            context=context,
        )

    return execute
