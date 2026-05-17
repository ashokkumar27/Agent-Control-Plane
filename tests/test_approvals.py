import tempfile
import unittest
from pathlib import Path

from agent_control_plane import InMemoryApprovalQueue, PolicyDecision, SQLiteApprovalQueue, ToolCall


class ApprovalTests(unittest.TestCase):
    def make_request(self, queue):
        call = ToolCall(call_id="c1", run_id="r1", agent_id="a1", user_id="u1", tool_name="t1", args={})
        decision = PolicyDecision(decision="require_approval", reason="needs approval", approver_role="manager")
        return queue.create(call, decision)

    def test_approval_lifecycle(self):
        queue = InMemoryApprovalQueue()
        approval = self.make_request(queue)
        self.assertEqual(approval.status, "pending")
        queue.approve(approval.approval_id, approver_id="m1")
        self.assertEqual(queue.get(approval.approval_id).status, "approved")

    def test_sqlite_persists_pending_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "approvals.db"
            queue = SQLiteApprovalQueue(db_path)
            approval = self.make_request(queue)

            restored = SQLiteApprovalQueue(db_path)
            pending = restored.list_pending()

            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].approval_id, approval.approval_id)
            self.assertEqual(restored.get(approval.approval_id).decision.approver_role, "manager")
            self.assertEqual(restored.get(approval.approval_id).tool_call.agent_id, "a1")

    def test_sqlite_approve_persists_decision_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "approvals.db"
            queue = SQLiteApprovalQueue(db_path)
            approval = self.make_request(queue)

            queue.approve(
                approval.approval_id,
                approver_id="m1",
                approver_role="manager",
                modified_args={"amount": 10},
                notes="reviewed",
            )
            restored = SQLiteApprovalQueue(db_path).get(approval.approval_id)

            self.assertEqual(restored.status, "approved")
            self.assertEqual(restored.approver_id, "m1")
            self.assertEqual(restored.approver_role, "manager")
            self.assertEqual(restored.modified_args, {"amount": 10})
            self.assertEqual(restored.notes, "reviewed")
            self.assertEqual(SQLiteApprovalQueue(db_path).list_pending(), [])

    def test_sqlite_reject_persists_and_blocks_duplicate_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "approvals.db"
            queue = SQLiteApprovalQueue(db_path)
            approval = self.make_request(queue)

            queue.reject(approval.approval_id, approver_id="m1", approver_role="manager", notes="bad request")
            restored_queue = SQLiteApprovalQueue(db_path)
            restored = restored_queue.get(approval.approval_id)

            self.assertEqual(restored.status, "rejected")
            self.assertEqual(restored.notes, "bad request")
            self.assertEqual(restored_queue.list_pending(), [])
            with self.assertRaises(ValueError):
                restored_queue.approve(approval.approval_id, approver_id="m2")

    def test_sqlite_missing_request_raises_key_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = SQLiteApprovalQueue(Path(tmp) / "approvals.db")
            with self.assertRaises(KeyError):
                queue.get("approval_missing")

if __name__ == "__main__":
    unittest.main()
