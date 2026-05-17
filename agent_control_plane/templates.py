from __future__ import annotations

from pathlib import Path
from textwrap import dedent

STARTER_FILES: dict[str, str] = {
    "GOVERNANCE_README.md": """
    # Agent Control Plane Starter Project

    This folder is designed so governance teams and developers can work together.

    ## For governance / risk teams

    Start with these files:

    - `agents/customer_support_refund_agent.yaml` — what the agent is for, who owns it, and what tools it may use.
    - `tools/issue_refund.yaml` — what the tool does and why it is high impact.
    - `policies/refund_controls.yaml` — what is allowed, denied, or sent for approval.
    - `scenarios/refund_governance.yaml` — regression tests for expected policy and runtime behavior.
    - `risk_assessments/customer_support_refund_agent.yaml` — business-friendly review questions.

    You can run:

    ```bash
    agentctl validate .
    agentctl test .
    agentctl review .
    agentctl assess .
    agentctl simulate . --agent customer_support_refund_agent --tool issue_refund --args '{"order_id":"A123","amount":280,"reason":"Damaged item"}'
    agentctl portal .
    ```

    `agentctl validate` is the production gate. Treat validation errors as
    deployment blockers before running agents against real tools.

    `agentctl simulate` is a dry run. It returns the policy decision without
    calling the underlying tool handler.

    `agentctl test` is the scenario regression gate. Put the scenarios in CI so
    policy edits, approval changes, idempotency behavior, and audit logging do
    not drift silently.

    ## For developers

    Load this project in Python:

    ```python
    from agent_control_plane import ControlPlaneProject

    project = ControlPlaneProject.load(".")
    plane = project.build_control_plane(handlers={"issue_refund": issue_refund})
    ```
    """,
    "agents/customer_support_refund_agent.yaml": """
    agent_id: customer_support_refund_agent
    owner: support_operations
    business_owner: Head of Customer Support
    technical_owner: AI Platform Team
    framework: any_agent_framework
    model: your-model-name
    purpose: >
      Helps customer support agents investigate order problems and propose refunds
      or replacements. It may read order information and request refund actions,
      but it must not approve large refunds or override fraud controls by itself.
    risk_tier: high
    affected_users:
      - customers
      - support_agents
    data_processed:
      - pii
      - confidential
    allowed_tools:
      - get_order
      - issue_refund
    prohibited_tools:
      - delete_customer_account
      - modify_payment_method
    human_oversight:
      required_for:
        - refunds above autonomous limit
        - fraud flagged accounts
        - legal complaints
    tags:
      - customer_support
      - refunds
      - human_approval
    """,
    "tools/get_order.yaml": """
    name: get_order
    description: Read order status, item list, delivery state, and customer ID for one order.
    tool_type: read_only
    risk_tier: medium
    side_effect: false
    data_access:
      - pii
      - confidential
    allowed_roles:
      - support_agent
      - support_manager
    tags:
      - order_lookup
      - customer_data
    """,
    "tools/issue_refund.yaml": """
    name: issue_refund
    description: Issue a customer refund through the payment system.
    tool_type: side_effecting
    risk_tier: high
    side_effect: true
    data_access:
      - pii
      - pci
    allowed_roles:
      - support_agent
      - support_manager
      - finance_manager
    approval_rules:
      - Refunds above 50 require support manager approval.
      - Refunds above 500 require finance manager approval.
      - Fraud flagged accounts must be denied or escalated.
    tags:
      - payment
      - refund
      - high_impact_action
    """,
    "policies/refund_controls.yaml": """
    rules:
      - rule_id: deny_refund_for_fraud_flag
        effect: deny
        description: Block refunds for fraud-flagged accounts until a specialist reviews the case.
        reason: Customer account is fraud-flagged. Autonomous refund is not allowed.
        priority: 1000
        when:
          tool.name:
            eq: issue_refund
          user.fraud_flag:
            eq: true
        controls:
          - fraud_control
          - least_privilege
          - human_escalation

      - rule_id: require_support_manager_for_refund_above_50
        effect: require_approval
        description: Refunds above 50 require support manager approval.
        reason: Refund exceeds autonomous support threshold.
        approver_role: support_manager
        priority: 900
        when:
          tool.name:
            eq: issue_refund
          args.amount:
            gt: 50
        controls:
          - human_oversight
          - approval_threshold
          - record_keeping

      - rule_id: require_finance_manager_for_refund_above_500
        effect: require_approval
        description: Refunds above 500 require finance manager approval.
        reason: Refund exceeds finance escalation threshold.
        approver_role: finance_manager
        priority: 950
        when:
          tool.name:
            eq: issue_refund
          args.amount:
            gt: 500
        controls:
          - human_oversight
          - financial_control
          - record_keeping

      - rule_id: allow_small_refund
        effect: allow
        description: Small refunds may be issued automatically if no higher-risk rule matches.
        reason: Refund is within the autonomous approval limit.
        priority: 100
        when:
          tool.name:
            eq: issue_refund
          args.amount:
            lte: 50
        controls:
          - least_privilege
          - audit_logging

      - rule_id: allow_order_lookup
        effect: allow
        description: The support agent may read order information for support purposes.
        reason: Order lookup is allowed for this agent.
        priority: 100
        when:
          tool.name:
            eq: get_order
        controls:
          - minimum_necessary_access
          - audit_logging
          - privacy_control
    """,
    "scenarios/refund_governance.yaml": """
    scenarios:
      - name: small_refund_allowed
        mode: simulate
        agent_id: customer_support_refund_agent
        tool_name: issue_refund
        args:
          order_id: A123
          amount: 25
          reason: Late delivery
        user:
          fraud_flag: false
        expected:
          status: allowed
          matched_rules:
            includes:
              - allow_small_refund
          controls:
            includes:
              - audit_logging
              - least_privilege
          ledger_events:
            includes:
              - tool_call_proposed
          ledger_verifies: true

      - name: finance_refund_requires_finance_manager
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
          controls:
            includes:
              - financial_control
              - human_oversight
          ledger_events:
            includes:
              - tool_call_proposed
          ledger_verifies: true

      - name: fraud_flag_denied
        mode: simulate
        agent_id: customer_support_refund_agent
        tool_name: issue_refund
        args:
          order_id: A123
          amount: 25
          reason: Customer request
        user:
          fraud_flag: true
        expected:
          status: denied
          matched_rules:
            includes:
              - deny_refund_for_fraud_flag
          controls:
            includes:
              - fraud_control
              - human_escalation
          ledger_events:
            includes:
              - tool_call_proposed
          ledger_verifies: true

      - name: idempotent_refund_replays_without_double_execution
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
          order_id: A123
          amount: 25
          reason: Late delivery
        steps:
          - name: first_execution
            expected:
              status: success
              idempotency:
                replayed: false
              ledger_events:
                includes:
                  - idempotency_started
                  - tool_call_executed
                  - idempotency_completed
          - name: retry_same_request
            expected:
              status: success
              idempotency:
                replayed: true
              ledger_events:
                includes:
                  - idempotency_replayed
        expected:
          ledger_events:
            includes:
              - idempotency_started
              - idempotency_completed
              - idempotency_replayed
          ledger_verifies: true
    """,
    "risk_assessments/customer_support_refund_agent.yaml": """
    assessment_id: customer_support_refund_agent_initial_review
    agent_id: customer_support_refund_agent
    reviewer: Governance Team
    status: draft
    plain_language_questions:
      - What customer problem does this agent solve?
      - Could the agent cause financial loss if misused?
      - Could the agent expose personal data?
      - Which actions require a human approval?
      - Who is accountable if the agent makes a wrong recommendation?
      - Can we audit every refund request later?
    decisions_needed:
      - Confirm autonomous refund threshold.
      - Confirm escalation owner for fraud-flagged accounts.
      - Confirm data retention period for audit records.
    """,
    "examples/developer_example.py": """
    from agent_control_plane import ControlPlaneProject


    def get_order(order_id: str):
        return {"order_id": order_id, "status": "delivered", "customer_id": "C123"}


    def issue_refund(order_id: str, amount: float, reason: str):
        return {"refund_id": "RF-001", "order_id": order_id, "amount": amount, "reason": reason}


    project = ControlPlaneProject.load("..")
    plane = project.build_control_plane(handlers={
        "get_order": get_order,
        "issue_refund": issue_refund,
    })

    print(plane.execute_tool(
        agent_id="customer_support_refund_agent",
        tool_name="issue_refund",
        args={"order_id": "A123", "amount": 25, "reason": "Late delivery"},
        user_id="user_1",
        context={"user": {"fraud_flag": False}},
    ))

    print(plane.execute_tool(
        agent_id="customer_support_refund_agent",
        tool_name="issue_refund",
        args={"order_id": "A123", "amount": 280, "reason": "Damaged item"},
        user_id="user_1",
        context={"user": {"fraud_flag": False}},
    ))
    """,
}


def write_starter_project(path: str | Path, *, overwrite: bool = False) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    for relative, content in STARTER_FILES.items():
        target = path / relative
        if target.exists() and not overwrite:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dedent(content).strip() + "\n", encoding="utf-8")
    return path
