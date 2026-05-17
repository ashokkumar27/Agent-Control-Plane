import unittest

from agent_control_plane import AgentCard, AgentControlPlane, PolicyEngine, PolicyRule, ToolCard


def refund_tool(order_id: str, amount: float, reason: str):
    return {"refund_id": "RF1", "order_id": order_id, "amount": amount, "reason": reason}


class GatewayTests(unittest.TestCase):
    def setUp(self):
        rules = [
            PolicyRule(
                rule_id="approval_above_50",
                effect="require_approval",
                description="approval",
                approver_role="manager",
                when={"tool.name": {"eq": "issue_refund"}, "args.amount": {"gt": 50}},
            ),
            PolicyRule(
                rule_id="allow_under_50",
                effect="allow",
                description="allow",
                when={"tool.name": {"eq": "issue_refund"}, "args.amount": {"lte": 50}},
            ),
        ]
        self.cp = AgentControlPlane(policy_engine=PolicyEngine(rules))
        self.cp.register_agent(AgentCard(agent_id="a1", owner="test", purpose="test", allowed_tools=["issue_refund"]))
        self.cp.register_tool(ToolCard(name="issue_refund", description="refund", tool_type="side_effecting"), refund_tool)

    def test_execute_allowed_tool(self):
        result = self.cp.execute_tool(
            agent_id="a1",
            tool_name="issue_refund",
            args={"order_id": "A1", "amount": 10, "reason": "late"},
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["output"]["amount"], 10)

    def test_approval_required_and_resume(self):
        result = self.cp.execute_tool(
            agent_id="a1",
            tool_name="issue_refund",
            args={"order_id": "A1", "amount": 100, "reason": "damaged"},
        )
        self.assertEqual(result["status"], "approval_required")
        approval_id = result["approval_id"]
        resumed = self.cp.approve_and_execute(approval_id, approver_id="m1", approver_role="manager", modified_args={"order_id": "A1", "amount": 80, "reason": "approved"})
        self.assertEqual(resumed["status"], "success")
        self.assertEqual(resumed["output"]["amount"], 80)

    def test_evidence_written(self):
        self.cp.execute_tool(agent_id="a1", tool_name="issue_refund", args={"order_id": "A1", "amount": 10, "reason": "late"})
        records = self.cp.ledger.list_records()
        self.assertGreaterEqual(len(records), 3)
        self.assertTrue(all(record.evidence_hash for record in records))


if __name__ == "__main__":
    unittest.main()
