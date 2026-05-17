from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .models import AgentCard, ToolCard, PolicyRule, RiskTier, DecisionType


@dataclass
class Finding:
    severity: str
    title: str
    plain_language: str
    suggested_fix: str
    owner: str = "governance_team"

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "title": self.title,
            "plain_language": self.plain_language,
            "suggested_fix": self.suggested_fix,
            "owner": self.owner,
        }


@dataclass
class ReadinessReport:
    agent_id: str
    score: int
    status: str
    summary: str
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "score": self.score,
            "status": self.status,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Readiness report: {self.agent_id}",
            "",
            f"**Score:** {self.score}/100",
            f"**Status:** {self.status}",
            "",
            self.summary,
            "",
            "## Findings",
        ]
        if not self.findings:
            lines.append("No major findings detected by the starter assessment.")
        for item in self.findings:
            lines.extend([
                "",
                f"### {item.severity.upper()}: {item.title}",
                item.plain_language,
                f"**Suggested fix:** {item.suggested_fix}",
            ])
        return "\n".join(lines)


def _has_approval_rule_for_tool(tool: ToolCard, rules: Iterable[PolicyRule]) -> bool:
    for r in rules:
        if r.effect != DecisionType.REQUIRE_APPROVAL:
            continue
        tool_condition = r.when.get("tool.name") or r.when.get("tool_name")
        if isinstance(tool_condition, dict) and tool_condition.get("eq") == tool.name:
            return True
        if tool_condition == tool.name:
            return True
    return False


def _has_deny_rule(rules: Iterable[PolicyRule]) -> bool:
    return any(r.effect == DecisionType.DENY for r in rules)


def assess_agent_readiness(agent: AgentCard, tools: list[ToolCard], rules: list[PolicyRule]) -> ReadinessReport:
    """Starter readiness scoring designed for non-technical governance review.

    It intentionally uses plain language. This is not a legal compliance conclusion;
    it is a practical onboarding checklist.
    """
    findings: list[Finding] = []

    if not agent.business_owner:
        findings.append(Finding(
            severity="medium",
            title="Business owner is missing",
            plain_language="The agent does not clearly say who owns the business decision if something goes wrong.",
            suggested_fix="Add a named business owner or accountable team to the AgentCard.",
        ))
    if not agent.technical_owner:
        findings.append(Finding(
            severity="medium",
            title="Technical owner is missing",
            plain_language="The agent does not clearly say who is responsible for fixes, outages, and technical incidents.",
            suggested_fix="Add a named technical owner or platform team to the AgentCard.",
            owner="platform_team",
        ))
    if not agent.purpose or len(agent.purpose.strip()) < 20:
        findings.append(Finding(
            severity="medium",
            title="Purpose statement is too short",
            plain_language="Reviewers may not understand what the agent is meant to do or what it must not do.",
            suggested_fix="Write a one-paragraph purpose statement that includes allowed and disallowed uses.",
        ))
    if not agent.allowed_tools:
        findings.append(Finding(
            severity="high",
            title="No explicit tool allowlist",
            plain_language="Without a clear allowlist, the agent may receive broader tool access than intended.",
            suggested_fix="List every tool this agent is allowed to use.",
            owner="platform_team",
        ))

    high_risk_tools = [t for t in tools if t.risk_tier in {RiskTier.HIGH, RiskTier.CRITICAL} or t.side_effect]
    for tool in high_risk_tools:
        if not _has_approval_rule_for_tool(tool, rules):
            findings.append(Finding(
                severity="high",
                title=f"High-impact tool lacks an approval rule: {tool.name}",
                plain_language=f"The tool '{tool.name}' can affect real systems or sensitive decisions, but no human approval rule was found.",
                suggested_fix=f"Add a policy rule that requires approval before '{tool.name}' is used above a safe threshold.",
            ))

    if any(str(x).lower() in {"pii", "phi", "pci", "restricted", "secrets"} for x in agent.data_processed):
        has_data_control = any("redaction" in c or "data" in c or "privacy" in c for r in rules for c in r.controls)
        if not has_data_control:
            findings.append(Finding(
                severity="high",
                title="Sensitive data is listed but no data control was found",
                plain_language="The agent processes sensitive data, but policies do not mention privacy, redaction, or data minimization controls.",
                suggested_fix="Add output redaction, minimum-necessary access, and data handling policies.",
            ))

    if not _has_deny_rule(rules):
        findings.append(Finding(
            severity="medium",
            title="No deny rule found",
            plain_language="Approval rules are useful, but some actions should be blocked outright.",
            suggested_fix="Add at least one deny rule for prohibited tools, fraud flags, secrets, or disallowed data exports.",
        ))

    risk_penalty = {"low": 5, "medium": 10, "high": 15, "critical": 20}.get(agent.risk_tier.value, 10)
    penalty = risk_penalty + sum({"low": 3, "medium": 8, "high": 15, "critical": 25}.get(f.severity, 8) for f in findings)
    score = max(0, min(100, 100 - penalty))
    if score >= 85:
        status = "ready_for_pilot"
    elif score >= 70:
        status = "needs_minor_review"
    elif score >= 50:
        status = "needs_governance_review"
    else:
        status = "not_ready"
    summary = (
        "This report is a practical onboarding review, not a legal compliance certificate. "
        "It highlights missing ownership, tool approval, data handling, and blocking controls before production use."
    )
    return ReadinessReport(agent_id=agent.agent_id, score=score, status=status, summary=summary, findings=findings)
