import unittest

from agent_control_plane import AgentCard, PolicyEngine, PolicyRule, ToolCall, ToolCard


class PolicyEngineTests(unittest.TestCase):
    def setUp(self):
        self.agent = AgentCard(
            agent_id="a1",
            owner="test",
            purpose="test",
            allowed_tools=["issue_refund"],
        )
        self.tool = ToolCard(
            name="issue_refund",
            description="refund",
            tool_type="side_effecting",
            side_effect=True,
        )
        self.engine = PolicyEngine([
            PolicyRule(
                rule_id="deny_fraud",
                effect="deny",
                priority=300,
                description="deny fraud",
                when={"tool.name": {"eq": "issue_refund"}, "user.fraud_flag": {"eq": True}},
                controls=["fraud_control"],
            ),
            PolicyRule(
                rule_id="approval_above_50",
                effect="require_approval",
                priority=200,
                description="approval",
                approver_role="manager",
                when={"tool.name": {"eq": "issue_refund"}, "args.amount": {"gt": 50}},
                controls=["human_oversight"],
            ),
            PolicyRule(
                rule_id="allow_under_50",
                effect="allow",
                priority=100,
                description="allow low",
                when={"tool.name": {"eq": "issue_refund"}, "args.amount": {"lte": 50}},
                controls=["least_privilege"],
            ),
        ])

    def decision_for(self, amount, fraud=False):
        call = ToolCall(
            call_id="c1",
            run_id="r1",
            agent_id="a1",
            user_id="u1",
            tool_name="issue_refund",
            args={"amount": amount},
            context={"user": {"fraud_flag": fraud}},
        )
        return self.engine.authorize(agent=self.agent, tool=self.tool, tool_call=call)

    def test_allow_low_value_refund(self):
        decision = self.decision_for(10)
        self.assertEqual(decision.decision.value, "allow")

    def test_require_approval_above_threshold(self):
        decision = self.decision_for(100)
        self.assertEqual(decision.decision.value, "require_approval")
        self.assertEqual(decision.approver_role, "manager")

    def test_deny_wins_over_allow(self):
        decision = self.decision_for(10, fraud=True)
        self.assertEqual(decision.decision.value, "deny")
        self.assertIn("deny_fraud", decision.matched_rules)

    def test_agent_allowlist_baseline(self):
        other_tool = ToolCard(name="delete_customer", description="bad", tool_type="side_effecting")
        call = ToolCall(call_id="c1", run_id="r1", agent_id="a1", user_id="u1", tool_name="delete_customer", args={})
        decision = self.engine.authorize(agent=self.agent, tool=other_tool, tool_call=call)
        self.assertEqual(decision.decision.value, "deny")
        self.assertIn("baseline:agent_allowed_tools", decision.matched_rules)


if __name__ == "__main__":
    unittest.main()
