from __future__ import annotations

from .models import AgentCard, ToolCard, PolicyRule, DecisionType
from .assessment import assess_agent_readiness


def _risk_label(value: object) -> str:
    return getattr(value, "value", value).__str__().replace("_", " ").title()


def describe_agent_for_humans(agent: AgentCard, tools: list[ToolCard], rules: list[PolicyRule]) -> str:
    """Create a plain-English introduction for governance and business reviewers."""
    tool_by_name = {t.name: t for t in tools}
    allowed = [tool_by_name[name] for name in agent.allowed_tools if name in tool_by_name]
    missing_tools = [name for name in agent.allowed_tools if name not in tool_by_name]
    report = assess_agent_readiness(agent, allowed, rules)

    lines: list[str] = []
    lines.append(f"# Plain-language review: {agent.agent_id}")
    lines.append("")
    lines.append("## What this agent is for")
    lines.append(agent.purpose or "No purpose has been provided yet.")
    lines.append("")
    lines.append("## Who is accountable")
    lines.append(f"- Business owner: {agent.business_owner or 'Not provided'}")
    lines.append(f"- Technical owner: {agent.technical_owner or 'Not provided'}")
    lines.append(f"- Overall risk tier: {_risk_label(agent.risk_tier)}")
    lines.append("")
    lines.append("## What it can do")
    if allowed:
        for tool in allowed:
            effect = "can change real systems" if tool.side_effect else "read-only or low-impact"
            lines.append(f"- **{tool.name}**: {tool.description} ({_risk_label(tool.risk_tier)}, {effect})")
    else:
        lines.append("No tools are currently listed as allowed.")
    if missing_tools:
        lines.append("")
        lines.append("Tools listed in the agent allowlist but not found in the tool catalog:")
        for name in missing_tools:
            lines.append(f"- {name}")
    lines.append("")
    lines.append("## What controls are in place")
    if rules:
        for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
            action = {
                DecisionType.ALLOW: "Allow",
                DecisionType.DENY: "Deny",
                DecisionType.REQUIRE_APPROVAL: "Require approval",
                DecisionType.ESCALATE: "Escalate",
                DecisionType.REDACT: "Redact",
                DecisionType.SANDBOX_ONLY: "Sandbox only",
                DecisionType.READ_ONLY_ONLY: "Read-only only",
            }.get(rule.effect, str(rule.effect))
            approver = f" by {rule.approver_role}" if rule.approver_role else ""
            lines.append(f"- **{action}{approver}**: {rule.description}")
    else:
        lines.append("No policies were found. This should be reviewed before production use.")
    lines.append("")
    lines.append("## Readiness summary")
    lines.append(f"- Score: {report.score}/100")
    lines.append(f"- Status: {report.status.replace('_', ' ')}")
    if report.findings:
        lines.append("")
        lines.append("## Questions for the governance team")
        for finding in report.findings:
            lines.append(f"- {finding.title}: {finding.suggested_fix}")
    return "\n".join(lines)
