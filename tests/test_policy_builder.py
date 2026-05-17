import unittest

from agent_control_plane import AgentCard, ToolCard, ToolCall, PolicyEngine, rule


class PolicyBuilderTests(unittest.TestCase):
    def test_builder_creates_approval_rule(self):
        policy = rule("Refunds above 50 require approval").when_tool("issue_refund").when_arg("amount", ">", 50).require_approval("manager")
        engine = PolicyEngine([policy])
        decision = engine.authorize(
            agent=AgentCard(agent_id="a", owner="o", purpose="test", allowed_tools=["issue_refund"]),
            tool=ToolCard(name="issue_refund", description="refund", tool_type="side_effecting", risk_tier="high"),
            tool_call=ToolCall(call_id="c", run_id="r", agent_id="a", user_id="u", tool_name="issue_refund", args={"amount": 100}),
        )
        self.assertTrue(decision.requires_approval)
        self.assertEqual(decision.approver_role, "manager")


if __name__ == "__main__":
    unittest.main()
