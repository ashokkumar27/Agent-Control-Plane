# Production readiness roadmap

The current v2 package is a stronger starter framework. For enterprise production, evolve it into a service-based control plane.

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

- Low-risk read-only actions may use cached policy.
- High-risk actions should fail closed.
- Sensitive data exports should fail closed.
- Production deployments should fail closed.

## What this v2 is

A developer-friendly and governance-friendly reference implementation.

## What it is not yet

A complete enterprise SaaS, a legal compliance certificate, or a replacement for formal risk assessment.
