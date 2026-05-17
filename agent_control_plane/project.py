from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .approvals import ApprovalQueue
from .idempotency import IdempotencyStore
from .io import iter_config_files, read_structured_file
from .ledger import AuditLedger
from .models import AgentCard, DecisionType, ToolCard, PolicyRule
from .policy import PolicyEngine
from .registries import AgentRegistry, ToolRegistry
from .gateway import AgentControlPlane
from .plain_language import describe_agent_for_humans
from .assessment import assess_agent_readiness, ReadinessReport


@dataclass
class ControlPlaneProject:
    """A human-friendly project folder containing agents, tools, and policies.

    Expected layout:
        agents/*.yaml
        tools/*.yaml
        policies/*.yaml
        risk_assessments/*.yaml  # optional
    """

    root: Path
    agents: list[AgentCard] = field(default_factory=list)
    tools: list[ToolCard] = field(default_factory=list)
    policies: list[PolicyRule] = field(default_factory=list)
    risk_assessments: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "ControlPlaneProject":
        root = Path(path).resolve()
        agents: list[AgentCard] = []
        tools: list[ToolCard] = []
        policies: list[PolicyRule] = []
        risk_assessments: list[dict[str, Any]] = []

        for folder in ["agents", "agentcards"]:
            for file in iter_config_files(root / folder):
                data = read_structured_file(file)
                agents.append(AgentCard(**data))

        for folder in ["tools", "toolcards"]:
            for file in iter_config_files(root / folder):
                data = read_structured_file(file)
                tools.append(ToolCard(**data))

        for file in iter_config_files(root / "policies"):
            data = read_structured_file(file)
            rules_data = data.get("rules", data.get("policies", data)) if isinstance(data, dict) else data
            for item in rules_data:
                policies.append(PolicyRule(**item))

        for file in iter_config_files(root / "risk_assessments"):
            risk_assessments.append(read_structured_file(file))

        return cls(root=root, agents=agents, tools=tools, policies=policies, risk_assessments=risk_assessments)

    def build_control_plane(
        self,
        handlers: dict[str, Callable[..., Any]] | None = None,
        *,
        approvals: ApprovalQueue | None = None,
        idempotency: IdempotencyStore | None = None,
        ledger: AuditLedger | None = None,
    ) -> AgentControlPlane:
        handlers = handlers or {}
        agent_registry = AgentRegistry()
        tool_registry = ToolRegistry()
        for agent in self.agents:
            agent_registry.register(agent)
        for tool in self.tools:
            tool_registry.register(tool, handlers.get(tool.name))
        return AgentControlPlane(
            agents=agent_registry,
            tools=tool_registry,
            policy_engine=PolicyEngine(self.policies),
            approvals=approvals,
            idempotency=idempotency,
            ledger=ledger,
        )

    def get_agent(self, agent_id: str | None = None) -> AgentCard:
        if agent_id:
            for agent in self.agents:
                if agent.agent_id == agent_id:
                    return agent
            raise KeyError(f"Agent not found: {agent_id}")
        if len(self.agents) == 1:
            return self.agents[0]
        raise ValueError("Multiple agents are present. Provide agent_id.")

    def tools_for_agent(self, agent: AgentCard) -> list[ToolCard]:
        by_name = {tool.name: tool for tool in self.tools}
        return [by_name[name] for name in agent.allowed_tools if name in by_name]

    def review_markdown(self, agent_id: str | None = None) -> str:
        agent = self.get_agent(agent_id)
        return describe_agent_for_humans(agent, self.tools, self.policies)

    def readiness_report(self, agent_id: str | None = None) -> ReadinessReport:
        agent = self.get_agent(agent_id)
        return assess_agent_readiness(agent, self.tools_for_agent(agent), self.policies)

    def simulate(
        self,
        *,
        agent_id: str,
        tool_name: str,
        args: dict[str, Any],
        user: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dry-run a tool call and return the policy outcome without execution."""
        plane = self.build_control_plane()
        simulation_context = dict(context or {})
        if user is not None:
            simulation_context["user"] = {**simulation_context.get("user", {}), **user}
        else:
            simulation_context.setdefault("user", {})
        call, decision = plane.propose_tool_call(
            agent_id=agent_id,
            tool_name=tool_name,
            args=args,
            user_id=simulation_context.get("user", {}).get("user_id"),
            context=simulation_context,
        )
        if decision.decision == DecisionType.ALLOW:
            status = "allowed"
            would_execute = True
        elif decision.decision == DecisionType.REQUIRE_APPROVAL:
            status = "approval_required"
            would_execute = False
        elif decision.decision == DecisionType.DENY:
            status = "denied"
            would_execute = False
        else:
            status = decision.decision.value
            would_execute = False
        return {
            "status": status,
            "simulated": True,
            "would_execute": would_execute,
            "reason": decision.reason,
            "approver_role": decision.approver_role,
            "tool_call": call.to_dict(),
            "decision": decision.to_dict(),
        }

    def inventory_summary(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "agents": [a.agent_id for a in self.agents],
            "tools": [t.name for t in self.tools],
            "policies": [p.rule_id for p in self.policies],
            "risk_assessments": [r.get("assessment_id") for r in self.risk_assessments if isinstance(r, dict)],
        }
