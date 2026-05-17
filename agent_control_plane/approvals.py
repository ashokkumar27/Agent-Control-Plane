from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Protocol

from .models import ApprovalRequest, ToolCall, PolicyDecision, new_id, utc_now_iso


class ApprovalQueue(Protocol):
    def create(self, tool_call: ToolCall, decision: PolicyDecision) -> ApprovalRequest: ...
    def get(self, approval_id: str) -> ApprovalRequest: ...
    def list_pending(self) -> list[ApprovalRequest]: ...
    def approve(
        self,
        approval_id: str,
        *,
        approver_id: str,
        approver_role: str | None = None,
        modified_args: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> ApprovalRequest: ...
    def reject(
        self,
        approval_id: str,
        *,
        approver_id: str,
        approver_role: str | None = None,
        notes: str | None = None,
    ) -> ApprovalRequest: ...


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

    def approve(self, approval_id: str, *, approver_id: str, approver_role: str | None = None, modified_args: dict[str, Any] | None = None, notes: str | None = None) -> ApprovalRequest:
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


class SQLiteApprovalQueue:
    """SQLite-backed approval queue for durable pilot deployments.

    This keeps the same small interface as InMemoryApprovalQueue while making
    pending approvals survive process restarts.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_requests (
                    approval_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    tool_call_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    decided_at TEXT,
                    approver_id TEXT,
                    approver_role TEXT,
                    modified_args_json TEXT,
                    notes TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_approvals_status ON approval_requests(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_approvals_requested ON approval_requests(requested_at)")
            conn.commit()

    def create(self, tool_call: ToolCall, decision: PolicyDecision) -> ApprovalRequest:
        request = ApprovalRequest(
            approval_id=new_id("approval"),
            tool_call=tool_call,
            decision=decision,
            approver_role=decision.approver_role,
        )
        self._upsert(request)
        return request

    def get(self, approval_id: str) -> ApprovalRequest:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT approval_id, status, tool_call_json, decision_json, requested_at, decided_at,
                       approver_id, approver_role, modified_args_json, notes
                FROM approval_requests
                WHERE approval_id = ?
                """,
                (approval_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Approval request '{approval_id}' was not found")
        return self._row_to_request(row)

    def list_pending(self) -> list[ApprovalRequest]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT approval_id, status, tool_call_json, decision_json, requested_at, decided_at,
                       approver_id, approver_role, modified_args_json, notes
                FROM approval_requests
                WHERE status = 'pending'
                ORDER BY requested_at ASC, approval_id ASC
                """
            ).fetchall()
        return [self._row_to_request(row) for row in rows]

    def approve(
        self,
        approval_id: str,
        *,
        approver_id: str,
        approver_role: str | None = None,
        modified_args: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> ApprovalRequest:
        request = self.get(approval_id)
        if request.status != "pending":
            raise ValueError(f"Approval request '{approval_id}' is already {request.status}")
        request.approve(approver_id=approver_id, approver_role=approver_role, modified_args=modified_args, notes=notes)
        self._upsert(request)
        return request

    def reject(self, approval_id: str, *, approver_id: str, approver_role: str | None = None, notes: str | None = None) -> ApprovalRequest:
        request = self.get(approval_id)
        if request.status != "pending":
            raise ValueError(f"Approval request '{approval_id}' is already {request.status}")
        request.reject(approver_id=approver_id, approver_role=approver_role, notes=notes)
        self._upsert(request)
        return request

    def _upsert(self, request: ApprovalRequest) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO approval_requests
                (approval_id, status, tool_call_json, decision_json, requested_at, decided_at,
                 approver_id, approver_role, modified_args_json, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(approval_id) DO UPDATE SET
                    status = excluded.status,
                    tool_call_json = excluded.tool_call_json,
                    decision_json = excluded.decision_json,
                    requested_at = excluded.requested_at,
                    decided_at = excluded.decided_at,
                    approver_id = excluded.approver_id,
                    approver_role = excluded.approver_role,
                    modified_args_json = excluded.modified_args_json,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    request.approval_id,
                    request.status,
                    json.dumps(request.tool_call.to_dict(), sort_keys=True),
                    json.dumps(request.decision.to_dict(), sort_keys=True),
                    request.requested_at,
                    request.decided_at,
                    request.approver_id,
                    request.approver_role,
                    json.dumps(request.modified_args, sort_keys=True) if request.modified_args is not None else None,
                    request.notes,
                    utc_now_iso(),
                ),
            )
            conn.commit()

    def _row_to_request(self, row: tuple[Any, ...]) -> ApprovalRequest:
        tool_call = ToolCall(**json.loads(row[2]))
        decision = PolicyDecision(**json.loads(row[3]))
        return ApprovalRequest(
            approval_id=row[0],
            status=row[1],
            tool_call=tool_call,
            decision=decision,
            requested_at=row[4],
            decided_at=row[5],
            approver_id=row[6],
            approver_role=row[7],
            modified_args=json.loads(row[8]) if row[8] is not None else None,
            notes=row[9],
        )
