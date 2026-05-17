from __future__ import annotations

from typing import Any, Callable

from agent_control_plane.gateway import AgentControlPlane


class LangGraphToolMiddleware:
    """Thin LangGraph-style middleware adapter.

    This file intentionally avoids importing LangGraph so the core package can
    be installed without framework dependencies. Use it as a template around
    a LangGraph ToolNode or custom node.
    """

    def __init__(
        self,
        control_plane: AgentControlPlane,
        *,
        agent_id: str,
        user_id: str | None = None,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        self.control_plane = control_plane
        self.agent_id = agent_id
        self.user_id = user_id
        self.run_id = run_id
        self.idempotency_key = idempotency_key
        self.context = context

    def wrap_tool(self, tool_name: str, handler: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
        if self.control_plane.tools.exists(tool_name):
            self.control_plane.tools.bind_handler(tool_name, handler)

        def governed_handler(**kwargs: Any) -> dict[str, Any]:
            return self.control_plane.execute_tool(
                agent_id=self.agent_id,
                tool_name=tool_name,
                args=kwargs,
                user_id=self.user_id,
                run_id=self.run_id,
                idempotency_key=self.idempotency_key,
                context=self.context,
            )

        return governed_handler
