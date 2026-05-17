# Production readiness roadmap

The current v2 package is a stronger starter framework. The first production-grade focus is a small fail-closed validation gate before adding service complexity.

## Current production gate

Run validation before review, simulation, or deployment:

```bash
agentctl validate sample_project
agentctl validate sample_project --json
```

Validation currently checks:

- Project files parse into known AgentCard, ToolCard, and PolicyRule shapes.
- Agent, tool, and policy rule identifiers are unique.
- Agent allowlists only reference registered tools.
- A tool cannot be both allowed and prohibited for the same agent.
- Policy rules that target specific agents or tools reference registered IDs.
- Policy paths use supported roots such as `agent`, `tool`, `args`, `user`, and `context`.
- Policy expressions use supported deterministic operators.
- Approval policies name an `approver_role`.
- High-impact tools require at least one deny or approval policy.

Treat validation errors as deployment blockers.

## Current durable runtime option

Use `SQLiteApprovalQueue` and `SQLiteIdempotencyStore` for pilot deployments
where approvals and retry records must survive process restarts:

```python
from agent_control_plane import (
    ControlPlaneProject,
    SQLiteApprovalQueue,
    SQLiteAuditLedger,
    SQLiteIdempotencyStore,
)

project = ControlPlaneProject.load("my_agent_project")
plane = project.build_control_plane(
    handlers={"issue_refund": issue_refund},
    approvals=SQLiteApprovalQueue("var/agent-control-plane/approvals.db"),
    ledger=SQLiteAuditLedger("var/agent-control-plane/audit.db"),
    idempotency=SQLiteIdempotencyStore("var/agent-control-plane/idempotency.db"),
)
```

SQLite approvals persist the approval request, original tool call, policy
decision, status, approver metadata, notes, modified arguments, and timestamps.
SQLite idempotency records persist a stable key, request fingerprint, terminal
result, and timestamps so retries do not double-execute side-effecting tools.
SQLite audit records are append-only and hash-chained. Call
`plane.ledger.verify()` during tests, deployment checks, or export jobs to detect
missing, reordered, or tampered records before relying on the evidence package.
For enterprise deployments, replace the same `ApprovalQueue` and
`IdempotencyStore` protocols, plus the `AuditLedger` protocol, with
Postgres-backed implementations integrated with SSO, your approval UI, and
observability stack.

Runtime audit coverage includes agent/tool registration, tool proposals, policy
outcomes, approval requests, approval decisions, approval rechecks, allowed
executions, tool errors, and all idempotency states: started, completed,
replayed, conflicted, and in-progress.

## Required production components

- Central API service
- OIDC / SSO authentication
- RBAC and ABAC authorization
- Postgres-backed registries
- Enterprise approval workflow
- Immutable audit store
- SIEM / SOC export
- OpenTelemetry tracing
- Policy versioning and rollback
- Idempotency keys for every side-effecting tool call
- Sidecar or gateway deployment mode
- DLP and result redaction
- Incident response and kill switch

## Fail behavior

- Invalid project configuration should fail before runtime.
- Low-risk read-only actions may use cached policy.
- High-risk actions should fail closed.
- Side-effecting retries should provide idempotency keys.
- Sensitive data exports should fail closed.
- Production deployments should fail closed.

## What this v2 is

A developer-friendly and governance-friendly reference implementation.

## What it is not yet

A complete enterprise SaaS, a legal compliance certificate, or a replacement for formal risk assessment.
