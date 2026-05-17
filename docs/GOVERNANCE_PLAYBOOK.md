# Governance playbook

The control plane turns governance into operational controls.

## Minimum production gate

Before a production agent is approved, require:

- AgentCard exists
- Business owner exists
- Technical owner exists
- ToolCards exist for every tool
- Sensitive data is identified
- High-impact tools have approval policies
- Prohibited actions have deny policies
- Audit logging is enabled
- Incident owner is assigned
- Abuse-case tests are defined

## Common risk tiers

- Low: read-only information assistant using public or internal data.
- Medium: reads customer or internal operational data but does not change systems.
- High: can send external messages, change records, issue refunds, or access sensitive data.
- Critical: can affect safety, rights, finance, production infrastructure, legal decisions, or regulated processes.

## Standard policy decisions

- Allow: safe to execute.
- Deny: must not execute.
- Require approval: pause until a human approves.
- Escalate: route to specialist.
- Redact: remove sensitive fields.
- Sandbox only: run only in isolated environment.
- Read-only only: do not permit mutation.
