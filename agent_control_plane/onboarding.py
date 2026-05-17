from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import write_structured_file


def new_agent_intake_template() -> dict[str, Any]:
    return {
        "agent_id": "replace_with_agent_name",
        "owner": "team_or_department",
        "business_owner": "name_or_role",
        "technical_owner": "name_or_role",
        "purpose": "Explain in plain language what the agent should and should not do.",
        "risk_tier": "medium",
        "affected_users": ["employees", "customers"],
        "data_processed": ["internal"],
        "allowed_tools": [],
        "prohibited_tools": [],
        "human_oversight": {
            "required_for": ["high-impact decisions", "external communications", "sensitive data access"]
        },
    }


def new_tool_intake_template() -> dict[str, Any]:
    return {
        "name": "replace_with_tool_name",
        "description": "Explain what this tool does in plain language.",
        "tool_type": "read_only",
        "risk_tier": "low",
        "side_effect": False,
        "data_access": ["internal"],
        "allowed_roles": [],
        "approval_rules": [],
        "tags": [],
    }


def new_policy_template() -> dict[str, Any]:
    return {
        "rules": [
            {
                "rule_id": "require_approval_for_high_impact_action",
                "effect": "require_approval",
                "description": "Require a human approval before this high-impact tool is used.",
                "reason": "This action can affect users, money, data, or production systems.",
                "approver_role": "business_owner",
                "priority": 900,
                "when": {"tool.name": {"eq": "replace_with_tool_name"}},
                "controls": ["human_oversight", "record_keeping"],
            }
        ]
    }


def write_intake_templates(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    write_structured_file(path / "agent_intake_template.yaml", new_agent_intake_template())
    write_structured_file(path / "tool_intake_template.yaml", new_tool_intake_template())
    write_structured_file(path / "policy_template.yaml", new_policy_template())
    return path
