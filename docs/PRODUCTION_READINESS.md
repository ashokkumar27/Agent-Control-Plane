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

## Required production components

- Central API service
- OIDC / SSO authentication
- RBAC and ABAC authorization
- Postgres-backed registries
- Durable approval workflow
- Immutable audit store
- SIEM / SOC export
- OpenTelemetry tracing
- Policy versioning and rollback
- Idempotency keys for every tool call
- Sidecar or gateway deployment mode
- DLP and result redaction
- Incident response and kill switch

## Fail behavior

- Invalid project configuration should fail before runtime.
- Low-risk read-only actions may use cached policy.
- High-risk actions should fail closed.
- Sensitive data exports should fail closed.
- Production deployments should fail closed.

## What this v2 is

A developer-friendly and governance-friendly reference implementation.

## What it is not yet

A complete enterprise SaaS, a legal compliance certificate, or a replacement for formal risk assessment.
