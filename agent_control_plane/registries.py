from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import AgentCard, ToolCard


class AgentRegistry:
    """In-memory agent registry.

    Replace this with a database-backed registry in production. The interface is
    deliberately small so the backing store can be swapped easily.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentCard] = {}

    def register(self, agent: AgentCard) -> None:
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> AgentCard:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"Agent '{agent_id}' is not registered") from exc

    def list(self) -> list[AgentCard]:
        return list(self._agents.values())

    def exists(self, agent_id: str) -> bool:
        return agent_id in self._agents


class ToolRegistry:
    """In-memory tool registry with callable binding."""

    def __init__(self) -> None:
        self._cards: dict[str, ToolCard] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, card: ToolCard, handler: Callable[..., Any] | None = None) -> None:
        self._cards[card.name] = card
        if handler is not None:
            self._handlers[card.name] = handler

    def bind_handler(self, tool_name: str, handler: Callable[..., Any]) -> None:
        if tool_name not in self._cards:
            raise KeyError(f"Tool card '{tool_name}' must be registered before binding a handler")
        self._handlers[tool_name] = handler

    def get_card(self, tool_name: str) -> ToolCard:
        try:
            return self._cards[tool_name]
        except KeyError as exc:
            raise KeyError(f"Tool '{tool_name}' is not registered") from exc

    def get_handler(self, tool_name: str) -> Callable[..., Any]:
        try:
            return self._handlers[tool_name]
        except KeyError as exc:
            raise KeyError(f"Tool '{tool_name}' has no executable handler") from exc

    def list_cards(self) -> list[ToolCard]:
        return list(self._cards.values())

    def exists(self, tool_name: str) -> bool:
        return tool_name in self._cards
