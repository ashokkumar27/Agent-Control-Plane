import unittest

from agent_control_plane import InMemoryApprovalQueue, PolicyDecision, ToolCall


class ApprovalTests(unittest.TestCase):
    def test_approval_lifecycle(self):
        queue = InMemoryApprovalQueue()
        call = ToolCall(call_id="c1", run_id="r1", agent_id="a1", user_id="u1", tool_name="t1", args={})
        decision = PolicyDecision(decision="require_approval", reason="needs approval", approver_role="manager")
        approval = queue.create(call, decision)
        self.assertEqual(approval.status, "pending")
        queue.approve(approval.approval_id, approver_id="m1")
        self.assertEqual(queue.get(approval.approval_id).status, "approved")


if __name__ == "__main__":
    unittest.main()
