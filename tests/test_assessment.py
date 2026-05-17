import unittest

from agent_control_plane import AgentCard, ToolCard, assess_agent_readiness


class AssessmentTests(unittest.TestCase):
    def test_missing_approval_is_flagged(self):
        agent = AgentCard(agent_id="a", owner="o", purpose="Agent does a high impact thing", allowed_tools=["danger"])
        tool = ToolCard(name="danger", description="dangerous action", tool_type="side_effecting", risk_tier="high")
        report = assess_agent_readiness(agent, [tool], [])
        titles = [f.title for f in report.findings]
        self.assertTrue(any("approval" in t.lower() for t in titles))


if __name__ == "__main__":
    unittest.main()
