from __future__ import annotations

from .models import ApprovalRequest, ToolCall, PolicyDecision, new_id


class InMemoryApprovalQueue:
    """Simple approval queue.

    Production implementations should back this with a durable database and
    connect it to Slack, Teams, Jira, ServiceNow, or an internal approval UI.
    """

    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}

    def create(self, tool_call: ToolCall, decision: PolicyDecision) -> ApprovalRequest:
        request = ApprovalRequest(
            approval_id=new_id("approval"),
            tool_call=tool_call,
            decision=decision,
            approver_role=decision.approver_role,
        )
        self._requests[request.approval_id] = request
        return request

    def get(self, approval_id: str) -> ApprovalRequest:
        try:
            return self._requests[approval_id]
        except KeyError as exc:
            raise KeyError(f"Approval request '{approval_id}' was not found") from exc

    def list_pending(self) -> list[ApprovalRequest]:
        return [req for req in self._requests.values() if req.status == "pending"]

    def approve(self, approval_id: str, *, approver_id: str, approver_role: str | None = None, modified_args: dict | None = None, notes: str | None = None) -> ApprovalRequest:
        request = self.get(approval_id)
        if request.status != "pending":
            raise ValueError(f"Approval request '{approval_id}' is already {request.status}")
        request.approve(approver_id=approver_id, approver_role=approver_role, modified_args=modified_args, notes=notes)
        return request

    def reject(self, approval_id: str, *, approver_id: str, approver_role: str | None = None, notes: str | None = None) -> ApprovalRequest:
        request = self.get(approval_id)
        if request.status != "pending":
            raise ValueError(f"Approval request '{approval_id}' is already {request.status}")
        request.reject(approver_id=approver_id, approver_role=approver_role, notes=notes)
        return request
