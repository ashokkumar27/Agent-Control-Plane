# Scenario Testing

`agentctl test` is the project-level regression gate for governance behavior.
Run it after `agentctl validate` and before deployment:

```bash
agentctl validate sample_project
agentctl test sample_project
agentctl test sample_project --json
```

Scenarios live in `<project>/scenarios` as YAML or JSON. They are meant to be
checked into the same repository as the agent cards, tool cards, and policies.

## What To Cover

Start with the behavior that must not drift:

- Read-only tools are allowed only when expected.
- Side-effecting tools route to approval at the right threshold.
- Deny rules win over allow rules.
- Guardrail findings escalate before side effects.
- Stable idempotency keys replay without double execution.
- Reused idempotency keys with changed arguments are blocked.
- Approval rechecks prevent modified arguments from increasing risk silently.
- Tool errors are logged and replayed for idempotent retries.
- Expected audit events are written.
- The audit ledger verifies after each scenario.

## Scenario Shape

Use `mode: simulate` for policy-only checks:

```yaml
name: large_refund_requires_finance_manager
mode: simulate
agent_id: customer_support_refund_agent
tool_name: issue_refund
args:
  order_id: A123
  amount: 600
  reason: Major loss
user:
  fraud_flag: false
expected:
  status: approval_required
  approver_role: finance_manager
  matched_rules:
    includes:
      - require_finance_manager_for_refund_above_500
  ledger_events:
    includes:
      - tool_call_proposed
  ledger_verifies: true
```

Use `mode: execute` and `steps` for runtime behavior with mocked handlers:

```yaml
name: idempotent_refund_replays_without_double_execution
mode: execute
agent_id: customer_support_refund_agent
tool_name: issue_refund
idempotency_key: refund:A123:25
args:
  order_id: A123
  amount: 25
  reason: Late delivery
user:
  fraud_flag: false
mock_output:
  refund_id: RF-SCENARIO-001
steps:
  - name: first_execution
    expected:
      status: success
      idempotency:
        replayed: false
  - name: retry_same_request
    expected:
      status: success
      idempotency:
        replayed: true
expected:
  ledger_events:
    includes:
      - idempotency_started
      - idempotency_completed
      - idempotency_replayed
  ledger_verifies: true
```

Supported expectation fields are `status`, `approver_role`, `matched_rules`,
`controls`, `ledger_events`, `idempotency`, `output`, and `ledger_verifies`.
Collection fields support `includes`, `excludes`, and `equals`.
