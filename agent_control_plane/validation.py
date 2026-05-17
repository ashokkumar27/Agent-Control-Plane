from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .io import iter_config_files, read_structured_file
from .models import AgentCard, DecisionType, PolicyRule, RiskTier, ToolCard, ToolType
from .policy import SUPPORTED_POLICY_OPERATORS

SUPPORTED_POLICY_PATH_ROOTS = {"agent", "tool", "tool_call", "args", "context", "user", "resource"}


@dataclass(slots=True)
class ProjectValidationIssue:
    severity: str
    code: str
    message: str
    path: str | None = None
    location: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "location": self.location,
        }


@dataclass(slots=True)
class ProjectValidationReport:
    root: str
    issues: list[ProjectValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ProjectValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ProjectValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        return "valid" if self.valid else "invalid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "status": self.status,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Project validation: {self.status}",
            "",
            f"- Root: {self.root}",
            f"- Errors: {len(self.errors)}",
            f"- Warnings: {len(self.warnings)}",
        ]
        if not self.issues:
            lines.append("")
            lines.append("No validation issues found.")
            return "\n".join(lines)
        lines.append("")
        lines.append("## Issues")
        for issue in self.issues:
            scope = f" ({issue.path})" if issue.path else ""
            location = f" [{issue.location}]" if issue.location else ""
            lines.append(f"- **{issue.severity.upper()} {issue.code}**{scope}{location}: {issue.message}")
        return "\n".join(lines)


def validate_project(path: str | Path) -> ProjectValidationReport:
    root = Path(path).resolve()
    issues: list[ProjectValidationIssue] = []
    agents, agent_paths = _load_agents(root, issues)
    tools, tool_paths = _load_tools(root, issues)
    policies, policy_paths = _load_policies(root, issues)

    _validate_required_inventory(agents, tools, policies, issues)
    _validate_duplicates("agent", [a.agent_id for a in agents], agent_paths, issues)
    _validate_duplicates("tool", [t.name for t in tools], tool_paths, issues)
    _validate_duplicates("policy", [p.rule_id for p in policies], policy_paths, issues)
    _validate_agent_tool_references(agents, tools, agent_paths, issues)
    _validate_policy_rules(policies, policy_paths, issues)
    _validate_policy_references(policies, agents, tools, policy_paths, issues)
    _validate_high_impact_tools(tools, policies, tool_paths, issues)

    return ProjectValidationReport(root=str(root), issues=issues)


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _issue(
    issues: list[ProjectValidationIssue],
    severity: str,
    code: str,
    message: str,
    *,
    path: str | None = None,
    location: str | None = None,
) -> None:
    issues.append(ProjectValidationIssue(severity=severity, code=code, message=message, path=path, location=location))


def _read_mapping(root: Path, file: Path, issues: list[ProjectValidationIssue]) -> dict[str, Any] | None:
    rel = _rel(root, file)
    try:
        data = read_structured_file(file)
    except Exception as exc:  # noqa: BLE001 - config validation should report parse failures
        _issue(issues, "error", "invalid_config_file", f"Could not read structured file: {exc}", path=rel)
        return None
    if not isinstance(data, dict):
        _issue(issues, "error", "invalid_config_shape", "Expected a mapping/object at the top level.", path=rel)
        return None
    return data


def _load_agents(root: Path, issues: list[ProjectValidationIssue]) -> tuple[list[AgentCard], dict[str, str]]:
    agents: list[AgentCard] = []
    sources: dict[str, str] = {}
    for folder in ["agents", "agentcards"]:
        for file in iter_config_files(root / folder):
            rel = _rel(root, file)
            data = _read_mapping(root, file, issues)
            if data is None:
                continue
            try:
                agent = AgentCard(**data)
            except Exception as exc:  # noqa: BLE001 - validation should report model construction failures
                _issue(issues, "error", "invalid_agent_card", f"Invalid AgentCard: {exc}", path=rel)
                continue
            agents.append(agent)
            sources[agent.agent_id] = rel
    return agents, sources


def _load_tools(root: Path, issues: list[ProjectValidationIssue]) -> tuple[list[ToolCard], dict[str, str]]:
    tools: list[ToolCard] = []
    sources: dict[str, str] = {}
    for folder in ["tools", "toolcards"]:
        for file in iter_config_files(root / folder):
            rel = _rel(root, file)
            data = _read_mapping(root, file, issues)
            if data is None:
                continue
            try:
                tool = ToolCard(**data)
            except Exception as exc:  # noqa: BLE001
                _issue(issues, "error", "invalid_tool_card", f"Invalid ToolCard: {exc}", path=rel)
                continue
            tools.append(tool)
            sources[tool.name] = rel
    return tools, sources


def _load_policies(root: Path, issues: list[ProjectValidationIssue]) -> tuple[list[PolicyRule], dict[str, str]]:
    rules: list[PolicyRule] = []
    sources: dict[str, str] = {}
    for file in iter_config_files(root / "policies"):
        rel = _rel(root, file)
        data = _read_mapping(root, file, issues)
        if data is None:
            continue
        rules_data = data.get("rules", data.get("policies", data))
        if not isinstance(rules_data, list):
            _issue(issues, "error", "invalid_policy_file", "Policy file must contain a list or a rules/policies list.", path=rel)
            continue
        for index, item in enumerate(rules_data):
            location = f"rules[{index}]"
            if not isinstance(item, dict):
                _issue(issues, "error", "invalid_policy_rule", "Policy rule must be a mapping/object.", path=rel, location=location)
                continue
            try:
                rule = PolicyRule(**item)
            except Exception as exc:  # noqa: BLE001
                _issue(issues, "error", "invalid_policy_rule", f"Invalid PolicyRule: {exc}", path=rel, location=location)
                continue
            rules.append(rule)
            sources[rule.rule_id] = rel
    return rules, sources


def _validate_required_inventory(
    agents: list[AgentCard],
    tools: list[ToolCard],
    policies: list[PolicyRule],
    issues: list[ProjectValidationIssue],
) -> None:
    if not agents:
        _issue(issues, "error", "missing_agents", "Project must define at least one agent.")
    if not tools:
        _issue(issues, "error", "missing_tools", "Project must define at least one tool.")
    if not policies:
        _issue(issues, "error", "missing_policies", "Project must define at least one policy rule.")


def _validate_duplicates(
    kind: str,
    values: list[str],
    sources: dict[str, str],
    issues: list[ProjectValidationIssue],
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    for value in sorted(duplicates):
        _issue(issues, "error", f"duplicate_{kind}", f"Duplicate {kind} identifier: {value}", path=sources.get(value))


def _validate_agent_tool_references(
    agents: list[AgentCard],
    tools: list[ToolCard],
    sources: dict[str, str],
    issues: list[ProjectValidationIssue],
) -> None:
    tool_names = {tool.name for tool in tools}
    for agent in agents:
        allowed = set(agent.allowed_tools)
        prohibited = set(agent.prohibited_tools)
        for tool_name in sorted(allowed - tool_names):
            _issue(
                issues,
                "error",
                "unknown_allowed_tool",
                f"Agent '{agent.agent_id}' allows unknown tool '{tool_name}'.",
                path=sources.get(agent.agent_id),
                location="allowed_tools",
            )
        overlap = allowed & prohibited
        for tool_name in sorted(overlap):
            _issue(
                issues,
                "error",
                "conflicting_tool_access",
                f"Agent '{agent.agent_id}' both allows and prohibits tool '{tool_name}'.",
                path=sources.get(agent.agent_id),
            )
        if not agent.allowed_tools:
            _issue(
                issues,
                "warning",
                "empty_allowed_tools",
                f"Agent '{agent.agent_id}' has no explicit tool allowlist. Runtime default-deny still applies.",
                path=sources.get(agent.agent_id),
                location="allowed_tools",
            )


def _validate_policy_rules(
    rules: list[PolicyRule],
    sources: dict[str, str],
    issues: list[ProjectValidationIssue],
) -> None:
    for rule in rules:
        source = sources.get(rule.rule_id)
        if not isinstance(rule.when, dict):
            _issue(issues, "error", "invalid_policy_when", f"Policy '{rule.rule_id}' has a non-object when clause.", path=source)
            continue
        if rule.effect == DecisionType.REQUIRE_APPROVAL and not rule.approver_role:
            _issue(
                issues,
                "error",
                "missing_approver_role",
                f"Approval policy '{rule.rule_id}' must name an approver_role.",
                path=source,
            )
        for policy_path, expression in rule.when.items():
            if not isinstance(policy_path, str) or not policy_path:
                _issue(issues, "error", "invalid_policy_path", f"Policy '{rule.rule_id}' has an empty or non-string path.", path=source)
                continue
            root = policy_path.split(".", 1)[0]
            if root not in SUPPORTED_POLICY_PATH_ROOTS:
                _issue(
                    issues,
                    "error",
                    "unsupported_policy_path",
                    f"Policy '{rule.rule_id}' uses unsupported path root '{root}'.",
                    path=source,
                    location=policy_path,
                )
            _validate_expression(rule.rule_id, expression, issues, source, policy_path)


def _validate_policy_references(
    rules: list[PolicyRule],
    agents: list[AgentCard],
    tools: list[ToolCard],
    sources: dict[str, str],
    issues: list[ProjectValidationIssue],
) -> None:
    agent_ids = {agent.agent_id for agent in agents}
    tool_names = {tool.name for tool in tools}
    for rule in rules:
        when = rule.when if isinstance(rule.when, dict) else {}
        source = sources.get(rule.rule_id)
        for path in ["tool.name", "tool_name"]:
            for tool_name in _condition_values(when.get(path)):
                if tool_name not in tool_names:
                    _issue(
                        issues,
                        "error",
                        "unknown_policy_tool",
                        f"Policy '{rule.rule_id}' references unknown tool '{tool_name}'.",
                        path=source,
                        location=path,
                    )
        for path in ["agent.agent_id", "agent_id"]:
            for agent_id in _condition_values(when.get(path)):
                if agent_id not in agent_ids:
                    _issue(
                        issues,
                        "error",
                        "unknown_policy_agent",
                        f"Policy '{rule.rule_id}' references unknown agent '{agent_id}'.",
                        path=source,
                        location=path,
                    )


def _validate_expression(
    rule_id: str,
    expression: Any,
    issues: list[ProjectValidationIssue],
    source: str | None,
    location: str,
) -> None:
    if not isinstance(expression, dict):
        return
    for op_name, expected in expression.items():
        if op_name not in SUPPORTED_POLICY_OPERATORS:
            _issue(
                issues,
                "error",
                "unsupported_policy_operator",
                f"Policy '{rule_id}' uses unsupported operator '{op_name}'.",
                path=source,
                location=location,
            )
            continue
        if op_name in {"any", "all"}:
            if not isinstance(expected, list):
                _issue(
                    issues,
                    "error",
                    "invalid_policy_operator_value",
                    f"Policy '{rule_id}' operator '{op_name}' expects a list.",
                    path=source,
                    location=location,
                )
                continue
            for branch in expected:
                _validate_expression(rule_id, branch, issues, source, location)
        elif op_name in {"in", "not_in"} and not isinstance(expected, list):
            _issue(
                issues,
                "error",
                "invalid_policy_operator_value",
                f"Policy '{rule_id}' operator '{op_name}' expects a list.",
                path=source,
                location=location,
            )


def _validate_high_impact_tools(
    tools: list[ToolCard],
    rules: list[PolicyRule],
    sources: dict[str, str],
    issues: list[ProjectValidationIssue],
) -> None:
    for tool in tools:
        high_impact = tool.side_effect or tool.risk_tier in {RiskTier.HIGH, RiskTier.CRITICAL}
        if not high_impact:
            continue
        if _has_blocking_or_approval_coverage(tool, rules):
            continue
        _issue(
            issues,
            "error",
            "high_impact_tool_uncontrolled",
            f"High-impact tool '{tool.name}' needs at least one deny or approval policy.",
            path=sources.get(tool.name),
        )


def _has_blocking_or_approval_coverage(tool: ToolCard, rules: list[PolicyRule]) -> bool:
    for rule in rules:
        if not rule.enabled or rule.effect not in {DecisionType.DENY, DecisionType.REQUIRE_APPROVAL}:
            continue
        if _rule_targets_tool(rule, tool):
            return True
    return False


def _condition_values(condition: Any) -> list[Any]:
    if condition is None:
        return []
    if isinstance(condition, dict):
        if "eq" in condition:
            return [condition["eq"]]
        expected = condition.get("in")
        if isinstance(expected, list):
            return list(expected)
        return []
    return [condition]


def _rule_targets_tool(rule: PolicyRule, tool: ToolCard) -> bool:
    when = rule.when if isinstance(rule.when, dict) else {}
    for path in ["tool.name", "tool_name"]:
        condition = when.get(path)
        if _condition_matches_value(condition, tool.name):
            return True
    if _condition_matches_value(when.get("tool.side_effect"), True):
        return True
    risk_condition = when.get("tool.risk_tier")
    if _condition_matches_value(risk_condition, tool.risk_tier.value):
        return True
    if isinstance(risk_condition, dict):
        expected = risk_condition.get("in")
        if isinstance(expected, list) and tool.risk_tier.value in expected:
            return True
    if tool.tool_type in {ToolType.SIDE_EFFECTING, ToolType.EXTERNAL_COMMUNICATION, ToolType.CODE_EXECUTION, ToolType.FILESYSTEM, ToolType.MCP}:
        if _condition_matches_value(when.get("tool.tool_type"), tool.tool_type.value):
            return True
    return False


def _condition_matches_value(condition: Any, value: Any) -> bool:
    if condition == value:
        return True
    if isinstance(condition, dict):
        if condition.get("eq") == value:
            return True
        expected = condition.get("in")
        if isinstance(expected, list) and value in expected:
            return True
    return False
