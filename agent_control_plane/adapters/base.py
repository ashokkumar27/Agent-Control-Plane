from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ToolCallEvent:
    agent_id: str
    tool_name: str
    args: dict[str, Any]
    run_id: str | None = None
    user_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


class RuntimeAdapter(Protocol):
    """Adapter interface for agent frameworks.

    Implement this once per agent runtime. The control plane should remain
    framework-agnostic and consume normalized tool-call events.
    """

    def on_tool_call_proposed(self, event: ToolCallEvent) -> dict[str, Any]: ...
