from __future__ import annotations

from typing import Any, Callable

from agent_control_plane.gateway import AgentControlPlane


class LangGraphToolMiddleware:
    """Thin LangGraph-style middleware adapter.

    This file intentionally avoids importing LangGraph so the core package can
    be installed without framework dependencies. Use it as a template around
    a LangGraph ToolNode or custom node.
    """

    def __init__(self, control_plane: AgentControlPlane, *, agent_id: str):
        self.control_plane = control_plane
        self.agent_id = agent_id

    def wrap_tool(self, tool_name: str, handler: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
        def governed_handler(**kwargs: Any) -> dict[str, Any]:
            # Register the actual callable in the control plane separately.
            return self.control_plane.execute_tool(agent_id=self.agent_id, tool_name=tool_name, args=kwargs)

        return governed_handler
