import tempfile
import unittest
from pathlib import Path

from agent_control_plane import ControlPlaneProject, write_starter_project


class ProjectLoaderTests(unittest.TestCase):
    def test_load_starter_project_and_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            project = ControlPlaneProject.load(tmp)
            self.assertEqual(len(project.agents), 1)
            self.assertGreaterEqual(len(project.tools), 2)
            self.assertGreaterEqual(len(project.policies), 1)
            review = project.review_markdown()
            self.assertIn("Plain-language review", review)
            self.assertIn("customer_support_refund_agent", review)

    def test_simulation_requires_approval_for_large_refund(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            project = ControlPlaneProject.load(tmp)
            result = project.simulate(
                agent_id="customer_support_refund_agent",
                tool_name="issue_refund",
                args={"order_id": "A123", "amount": 280, "reason": "Damaged item"},
                user={"fraud_flag": False},
            )
            self.assertEqual(result["status"], "approval_required")


if __name__ == "__main__":
    unittest.main()
