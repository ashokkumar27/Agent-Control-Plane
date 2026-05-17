from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_control_plane.gateway import AgentControlPlane


class GovernanceEvidenceExporter:
    """Export structured evidence for governance review.

    The exports are not a legal certification. They are structured artifacts
    that help governance, security, risk, compliance, and audit teams review how
    an agent was controlled at runtime.
    """

    def __init__(self, control_plane: AgentControlPlane):
        self.control_plane = control_plane

    def build_report(self, *, run_id: str | None = None) -> dict[str, Any]:
        records = [record.to_dict() for record in self.control_plane.ledger.list_records(run_id=run_id)]
        agents = [agent.to_dict() for agent in self.control_plane.agents.list()]
        tools = [tool.to_dict() for tool in self.control_plane.tools.list_cards()]
        return {
            "schema_version": "0.1",
            "scope": {"run_id": run_id or "all"},
            "governance_alignment": {
                "nist_ai_rmf": ["govern", "map", "measure", "manage"],
                "eu_ai_act_readiness": ["risk_management", "technical_documentation", "record_keeping", "human_oversight", "robustness_cybersecurity"],
                "iso_iec_42001": ["ai_management_system", "risk_and_opportunity_controls", "continual_improvement_evidence"],
                "owasp_agentic_ai": ["tool_misuse", "identity_privilege", "memory_context", "human_approval", "monitoring"],
            },
            "inventory": {"agents": agents, "tools": tools},
            "evidence_records": records,
        }

    def write_json(self, path: str | Path, *, run_id: str | None = None) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.build_report(run_id=run_id), indent=2, sort_keys=True), encoding="utf-8")
        return path
