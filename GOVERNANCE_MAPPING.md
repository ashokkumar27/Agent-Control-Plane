# Governance Mapping

This project turns governance concepts into runtime controls and evidence.

## NIST AI RMF mapping

| NIST AI RMF function | Runtime implementation |
|---|---|
| Govern | AgentCard, ToolCard, ownership, human oversight rules, policy-as-code |
| Map | Use-case purpose, affected users, data processed, risk tier, tool inventory |
| Measure | Abuse-case packs, guardrail results, policy decisions, runtime monitoring hooks |
| Manage | Allow/deny/approval decisions, incident records, kill-switch extension points, evidence exports |

## EU AI Act readiness mapping

| Area | Runtime implementation |
|---|---|
| Risk management | Risk tiers, policy rules, control tags, evaluation scenarios |
| Data governance | Data classification on AgentCard and ToolCard |
| Technical documentation | Agent/tool inventory and governance evidence export |
| Record-keeping | Evidence ledger with hash-chained records |
| Transparency | Structured decisions with reasons and matched rules |
| Human oversight | Approval queue and approver role requirements |
| Robustness/cybersecurity | Default deny, least privilege, guardrails, tool allowlists, abuse tests |

## ISO/IEC 42001-style artifacts

| AI management artifact | Runtime artifact |
|---|---|
| AI system inventory | Agent registry |
| Risk and opportunity controls | Policy rules and risk classifier |
| Roles and accountability | AgentCard owner, business owner, technical owner |
| Operational controls | Tool gateway and approval workflow |
| Monitoring evidence | Ledger records and exported governance report |
| Continual improvement | Test results, incidents, policy changes, evaluation history |

## OWASP agentic AI security mapping

| Risk area | Runtime control |
|---|---|
| Goal hijack / prompt injection | Input guardrail hooks, policy cannot be overridden by prompt |
| Tool misuse | Tool-call authorization and argument policies |
| Identity and privilege abuse | Agent allowlists, prohibited tools, scoped capabilities |
| Supply chain / external tools | ToolCard registry and MCP gateway extension point |
| Unsafe code execution | Code execution tool classification and sandbox-only policies |
| Memory/context abuse | Context firewall extension point and evidence provenance |
| Excessive agency | Approval thresholds, max-run policies, kill-switch extension point |
| Sensitive data exposure | Data classification, redaction hooks, output guardrails |

## Important disclaimer

This framework is a technical control plane and evidence generator. It does not provide legal advice or guarantee regulatory compliance. Formal compliance requires legal, risk, security, privacy, and organizational governance review.
