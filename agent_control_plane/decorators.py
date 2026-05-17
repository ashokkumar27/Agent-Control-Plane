from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from .models import RiskTier, ToolCard, ToolType


def governed_tool(
    *,
    name: str | None = None,
    description: str | None = None,
    tool_type: ToolType | str = ToolType.READ_ONLY,
    risk_tier: RiskTier | str = RiskTier.LOW,
    side_effect: bool = False,
    data_access: list[str] | None = None,
    allowed_roles: list[str] | None = None,
    approval_rules: list[str] | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach a ToolCard to a Python function.

    The decorator does not enforce policy by itself. Register the decorated
    function with AgentControlPlane.register_decorated_tool(...), then execute it
    through AgentControlPlane.execute_tool(...).
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        card = ToolCard(
            name=name or fn.__name__,
            description=description or (fn.__doc__ or fn.__name__).strip(),
            tool_type=tool_type,
            risk_tier=risk_tier,
            side_effect=side_effect,
            data_access=data_access or [],
            allowed_roles=allowed_roles or [],
            approval_rules=approval_rules or [],
            tags=tags or [],
            metadata=metadata or {},
        )
        setattr(fn, "__tool_card__", card)

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        setattr(wrapper, "__tool_card__", card)
        return wrapper

    return decorator
