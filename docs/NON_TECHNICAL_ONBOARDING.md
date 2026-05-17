# Non-technical onboarding guide

This guide is for AI governance, risk, compliance, legal, audit, and business teams.

You do not need to understand model internals to review an agent. You need to answer six questions:

1. What is the agent supposed to do?
2. Who owns it?
3. What tools can it use?
4. What data can it access?
5. What actions require human approval?
6. Can we prove what happened after the fact?

## Step 1: Create the starter project

```bash
agentctl init my_agent_project
```

## Step 2: Read the plain-language review

```bash
agentctl review my_agent_project
```

This explains the agent purpose, owners, allowed tools, controls, and governance questions.

## Step 3: Run readiness assessment

```bash
agentctl assess my_agent_project
```

The score is not a compliance certificate. It is a practical signal for missing ownership, approval, data, or deny controls.

## Step 4: Use the local portal

```bash
agentctl portal my_agent_project
```

Open the link in your browser. The portal shows a dashboard, plain-language review, and intake forms for agents and tools.

## Step 5: Decide approval rules

Common approval triggers:

- Money movement above a threshold
- External email or message
- Customer account changes
- Access to sensitive data
- Production code deployment
- Legal, financial, medical, HR, or safety-impacting output

## Step 6: Keep evidence

Every agent should have:

- AgentCard
- ToolCards
- Policies
- Risk assessment
- Approval records
- Audit logs
- Incident owner
- Review date
