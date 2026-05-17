"""Customer support demo for Agent Control Plane.

Run from the repository root:
    python examples/customer_support_agent.py

This simulates what a tool-calling LLM would do. The model can propose tool
calls in any order, but the control plane governs whether those calls execute.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_control_plane import (
    AgentCard,
    AgentControlPlane,
    PolicyEngine,
    ToolCard,
    ToolType,
    governed_tool,
    load_policy_file,
)
from agent_control_plane.exporters import GovernanceEvidenceExporter
from agent_control_plane.testing import evaluate_policy_controls


@governed_tool(
    name="get_order",
    description="Read order status, items, delivery status, and customer metadata.",
    tool_type=ToolType.READ_ONLY,
    risk_tier="medium",
    data_access=["pii", "confidential"],
)
def get_order(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "status": "delivered_late",
        "items": [
            {"id": "phone", "delivered": True},
            {"id": "charger", "delivered": False},
        ],
        "customer_id": "C88",
    }


@governed_tool(
    name="issue_refund",
    description="Issue a customer refund through the payments system.",
    tool_type=ToolType.SIDE_EFFECTING,
    risk_tier="high",
    side_effect=True,
    data_access=["pii", "pci", "confidential"],
)
def issue_refund(order_id: str, amount: float, reason: str) -> dict:
    # Real implementation would call a payment provider. This demo returns a stub.
    return {"refund_id": "RF-DEMO-001", "order_id": order_id, "amount": amount, "reason": reason}


def load_control_plane() -> AgentControlPlane:
    agent = AgentCard(**json.loads((ROOT / "examples/agentcards/customer_support_agent.json").read_text()))
    issue_refund_card = ToolCard(**json.loads((ROOT / "examples/toolcards/issue_refund.json").read_text()))
    get_order_card = ToolCard(**json.loads((ROOT / "examples/toolcards/get_order.json").read_text()))
    rules = load_policy_file(ROOT / "examples/policies/refund_policy.json")

    cp = AgentControlPlane(policy_engine=PolicyEngine(rules=rules))
    cp.register_agent(agent)
    cp.register_tool(get_order_card, get_order)
    cp.register_tool(issue_refund_card, issue_refund)
    return cp


def main() -> None:
    cp = load_control_plane()
    agent_id = "customer-support-refund-agent"
    run_id = "demo-run-001"

    print("\n1) Read-only lookup: allowed")
    print(json.dumps(cp.execute_tool(agent_id=agent_id, tool_name="get_order", args={"order_id": "A123"}, run_id=run_id), indent=2))

    print("\n2) Low-value refund: allowed")
    print(json.dumps(cp.execute_tool(
        agent_id=agent_id,
        tool_name="issue_refund",
        args={"order_id": "A123", "amount": 10, "reason": "Late delivery credit"},
        context={"user": {"fraud_flag": False}},
        run_id=run_id,
    ), indent=2))

    print("\n3) High-value refund: approval required")
    high_value = cp.execute_tool(
        agent_id=agent_id,
        tool_name="issue_refund",
        args={"order_id": "A123", "amount": 280, "reason": "Damaged item"},
        context={"user": {"fraud_flag": False}},
        run_id=run_id,
    )
    print(json.dumps(high_value, indent=2))

    print("\n4) Manager approves with modified lower amount; gateway executes")
    print(json.dumps(cp.approve_and_execute(
        high_value["approval_id"],
        approver_id="manager_88",
        approver_role="support_manager",
        modified_args={"order_id": "A123", "amount": 200, "reason": "Approved damaged item refund"},
        notes="Evidence reviewed.",
    ), indent=2))

    print("\n5) Fraud-flagged account: denied")
    print(json.dumps(cp.execute_tool(
        agent_id=agent_id,
        tool_name="issue_refund",
        args={"order_id": "A123", "amount": 10, "reason": "Small refund"},
        context={"user": {"fraud_flag": True}},
        run_id=run_id,
    ), indent=2))

    print("\n6) Starter OWASP-style abuse pack")
    print(json.dumps(evaluate_policy_controls(cp, agent_id=agent_id), indent=2))

    report_path = ROOT / "tmp" / "governance_evidence_demo.json"
    GovernanceEvidenceExporter(cp).write_json(report_path, run_id=run_id)
    print(f"\nGovernance evidence written to: {report_path}")


if __name__ == "__main__":
    main()
