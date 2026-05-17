from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import DecisionType, PolicyRule

_OP_ALIASES = {
    "=": "eq",
    "==": "eq",
    "equals": "eq",
    "is": "eq",
    "!=": "neq",
    "not equals": "neq",
    ">": "gt",
    ">=": "gte",
    "<": "lt",
    "<=": "lte",
    "contains": "contains",
    "in": "in",
    "not in": "not_in",
    "exists": "exists",
    "matches": "regex",
}


@dataclass
class RuleBuilder:
    """Tiny fluent API for developers who do not want to hand-write JSON rules.

    Example:
        rule("Refunds above 50 require approval")            .when_tool("issue_refund")            .when_arg("amount", ">", 50)            .require_approval("support_manager")            .build()
    """

    description: str
    rule_id: str | None = None
    conditions: dict[str, Any] = field(default_factory=dict)
    controls: list[str] = field(default_factory=list)
    priority: int = 100
    reason: str | None = None

    def _op(self, operator: str) -> str:
        return _OP_ALIASES.get(operator.strip().lower(), operator)

    def when(self, path: str, operator: str, expected: Any) -> "RuleBuilder":
        self.conditions[path] = {self._op(operator): expected}
        return self

    def when_tool(self, tool_name: str) -> "RuleBuilder":
        return self.when("tool.name", "=", tool_name)

    def when_agent(self, agent_id: str) -> "RuleBuilder":
        return self.when("agent.agent_id", "=", agent_id)

    def when_arg(self, arg_name: str, operator: str, expected: Any) -> "RuleBuilder":
        return self.when(f"args.{arg_name}", operator, expected)

    def when_user(self, field_name: str, operator: str, expected: Any) -> "RuleBuilder":
        return self.when(f"user.{field_name}", operator, expected)

    def with_control(self, *controls: str) -> "RuleBuilder":
        self.controls.extend(controls)
        return self

    def because(self, reason: str) -> "RuleBuilder":
        self.reason = reason
        return self

    def _id(self) -> str:
        if self.rule_id:
            return self.rule_id
        base = "".join(ch.lower() if ch.isalnum() else "_" for ch in self.description).strip("_")
        while "__" in base:
            base = base.replace("__", "_")
        return base[:64] or "policy_rule"

    def allow(self) -> PolicyRule:
        return self._build(DecisionType.ALLOW)

    def deny(self) -> PolicyRule:
        return self._build(DecisionType.DENY)

    def require_approval(self, approver_role: str) -> PolicyRule:
        return self._build(DecisionType.REQUIRE_APPROVAL, approver_role=approver_role)

    def escalate(self, approver_role: str | None = None) -> PolicyRule:
        return self._build(DecisionType.ESCALATE, approver_role=approver_role)

    def _build(self, effect: DecisionType, approver_role: str | None = None) -> PolicyRule:
        return PolicyRule(
            rule_id=self._id(),
            description=self.description,
            effect=effect,
            when=dict(self.conditions),
            controls=list(dict.fromkeys(self.controls)),
            priority=self.priority,
            reason=self.reason,
            approver_role=approver_role,
        )


def rule(description: str, *, rule_id: str | None = None, priority: int = 100) -> RuleBuilder:
    return RuleBuilder(description=description, rule_id=rule_id, priority=priority)
