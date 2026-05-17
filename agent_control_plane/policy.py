from __future__ import annotations

import json
import operator
import re
from pathlib import Path
from typing import Any, Iterable

from .models import AgentCard, DecisionType, PolicyDecision, PolicyRule, ToolCall, ToolCard


_MISSING = object()


def _get_path(obj: Any, path: str) -> Any:
    """Resolve dotted paths over dicts/dataclasses/objects.

    Examples:
        args.amount
        agent.risk_tier
        tool.side_effect
        context.user.fraud_flag
    """
    current = obj
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part, _MISSING)
        else:
            current = getattr(current, part, _MISSING)
        if current is _MISSING:
            return _MISSING
    if hasattr(current, "value"):
        return current.value
    return current


def _as_scalar(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _contains(haystack: Any, needle: Any) -> bool:
    haystack = _as_scalar(haystack)
    needle = _as_scalar(needle)
    if haystack is _MISSING or haystack is None:
        return False
    if isinstance(haystack, str):
        return str(needle) in haystack
    try:
        return needle in haystack
    except TypeError:
        return False


_OPERATORS = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "contains": _contains,
    "exists": lambda value, expected: (value is not _MISSING) is bool(expected),
    "is_true": lambda value, expected: bool(value) is bool(expected),
    "in": lambda value, expected: _as_scalar(value) in [_as_scalar(x) for x in expected],
    "not_in": lambda value, expected: _as_scalar(value) not in [_as_scalar(x) for x in expected],
    "regex": lambda value, expected: bool(re.search(str(expected), str(value or ""), flags=re.IGNORECASE)),
}


class PolicyEngine:
    """Deterministic policy engine for agent tool calls.

    This engine intentionally does not use an LLM. The model may propose actions,
    but policy decisions should be deterministic, testable, and auditable.
    """

    def __init__(self, rules: Iterable[PolicyRule] | None = None, default_decision: DecisionType | str = DecisionType.DENY):
        self.rules: list[PolicyRule] = list(rules or [])
        self.default_decision = DecisionType(default_decision)

    def add_rule(self, rule: PolicyRule) -> None:
        self.rules.append(rule)

    def load_rules(self, rules: Iterable[PolicyRule]) -> None:
        self.rules.extend(rules)

    def authorize(self, *, agent: AgentCard, tool: ToolCard, tool_call: ToolCall) -> PolicyDecision:
        """Return a policy decision for a proposed tool call."""
        world = {
            "agent": agent,
            "tool": tool,
            "tool_call": tool_call,
            "args": tool_call.args,
            "context": tool_call.context,
            "user": tool_call.context.get("user", {}),
            "resource": tool.resource_scope,
        }

        # Hard baseline controls that do not require policy authoring.
        if tool.name in agent.prohibited_tools:
            return PolicyDecision(
                decision=DecisionType.DENY,
                reason=f"Tool '{tool.name}' is explicitly prohibited for agent '{agent.agent_id}'.",
                matched_rules=["baseline:agent_prohibited_tools"],
                controls=["least_privilege", "agent_registry"],
            )

        if agent.allowed_tools and tool.name not in agent.allowed_tools:
            return PolicyDecision(
                decision=DecisionType.DENY,
                reason=f"Tool '{tool.name}' is not in the agent's allowed tool list.",
                matched_rules=["baseline:agent_allowed_tools"],
                controls=["least_privilege", "tool_allowlist"],
            )

        matching = [rule for rule in self.rules if rule.enabled and self._matches(rule, world)]

        input_guardrail = tool_call.context.get("guardrails", {}).get("input", {})
        if input_guardrail and input_guardrail.get("passed") is False and tool.side_effect:
            matching.append(
                PolicyRule(
                    rule_id="baseline:prompt_injection_side_effect_escalation",
                    effect=DecisionType.REQUIRE_APPROVAL,
                    priority=1000,
                    description="Prompt-injection-like input was detected before a side-effecting tool call.",
                    reason="Input guardrail triggered before side-effecting action; human review is required.",
                    approver_role="security_or_business_owner",
                    controls=list(input_guardrail.get("controls_triggered", [])) + ["human_oversight"],
                )
            )

        if not matching:
            return PolicyDecision(
                decision=self.default_decision,
                reason=f"No policy matched. Default decision is {self.default_decision.value}.",
                matched_rules=["default"],
                controls=["default_deny"],
            )

        # Deterministic precedence. Deny wins over approval. Approval wins over allow.
        precedence = {
            DecisionType.DENY: 100,
            DecisionType.REQUIRE_APPROVAL: 90,
            DecisionType.ESCALATE: 80,
            DecisionType.SANDBOX_ONLY: 70,
            DecisionType.READ_ONLY_ONLY: 60,
            DecisionType.REDACT: 50,
            DecisionType.ALLOW: 10,
        }
        matching.sort(key=lambda r: (precedence.get(r.effect, 0), r.priority), reverse=True)
        winner = matching[0]
        controls = sorted({control for rule in matching for control in rule.controls})
        return PolicyDecision(
            decision=winner.effect,
            reason=winner.reason or winner.description,
            matched_rules=[rule.rule_id for rule in matching],
            approver_role=winner.approver_role,
            controls=controls,
            metadata={"winning_rule": winner.rule_id},
        )

    def _matches(self, rule: PolicyRule, world: dict[str, Any]) -> bool:
        for path, expression in rule.when.items():
            value = _get_path(world, path)
            if not self._eval_expression(value, expression):
                return False
        return True

    def _eval_expression(self, value: Any, expression: Any) -> bool:
        if not isinstance(expression, dict):
            return _as_scalar(value) == _as_scalar(expression)

        for op_name, expected in expression.items():
            if op_name == "any":
                return any(self._eval_expression(value, branch) for branch in expected)
            if op_name == "all":
                return all(self._eval_expression(value, branch) for branch in expected)
            fn = _OPERATORS.get(op_name)
            if fn is None:
                raise ValueError(f"Unsupported policy operator: {op_name}")
            try:
                if not fn(value, expected):
                    return False
            except TypeError:
                return False
        return True


def load_policy_file(path: str | Path) -> list[PolicyRule]:
    """Load a policy file in JSON or YAML format.

    YAML support is optional. Install with: pip install agent-control-plane[yaml]
    """
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("YAML policy files require PyYAML. Install: pip install agent-control-plane[yaml]") from exc
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)

    rules_data = data.get("rules", data.get("policies", data))
    if not isinstance(rules_data, list):
        raise ValueError("Policy file must contain a list or an object with 'rules'/'policies'.")
    return [PolicyRule(**rule) for rule in rules_data]
