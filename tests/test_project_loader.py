import tempfile
import unittest
from pathlib import Path

from agent_control_plane import ControlPlaneProject, SQLiteApprovalQueue, SQLiteIdempotencyStore, write_starter_project


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

    def test_build_control_plane_accepts_durable_approvals(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            project = ControlPlaneProject.load(tmp)
            approvals = SQLiteApprovalQueue(Path(tmp) / "approvals.db")
            plane = project.build_control_plane(approvals=approvals)

            result = plane.execute_tool(
                agent_id="customer_support_refund_agent",
                tool_name="issue_refund",
                args={"order_id": "A123", "amount": 280, "reason": "Damaged item"},
                context={"user": {"fraud_flag": False}},
            )

            self.assertEqual(result["status"], "approval_required")
            self.assertEqual(approvals.get(result["approval_id"]).status, "pending")

    def test_build_control_plane_accepts_idempotency_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            project = ControlPlaneProject.load(tmp)
            calls = {"count": 0}

            def issue_refund(order_id: str, amount: float, reason: str):
                calls["count"] += 1
                return {"refund_id": "RF1", "order_id": order_id, "amount": amount, "reason": reason}

            plane = project.build_control_plane(
                handlers={"issue_refund": issue_refund},
                idempotency=SQLiteIdempotencyStore(Path(tmp) / "idempotency.db"),
            )
            args = {"order_id": "A123", "amount": 25, "reason": "Late delivery"}

            first = plane.execute_tool(
                agent_id="customer_support_refund_agent",
                tool_name="issue_refund",
                args=args,
                idempotency_key="refund-A123",
                context={"user": {"fraud_flag": False}},
            )
            second = plane.execute_tool(
                agent_id="customer_support_refund_agent",
                tool_name="issue_refund",
                args=args,
                idempotency_key="refund-A123",
                context={"user": {"fraud_flag": False}},
            )

            self.assertEqual(first["status"], "success")
            self.assertTrue(second["idempotency"]["replayed"])
            self.assertEqual(calls["count"], 1)


if __name__ == "__main__":
    unittest.main()
