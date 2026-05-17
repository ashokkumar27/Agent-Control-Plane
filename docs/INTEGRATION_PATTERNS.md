# Integration patterns

## 1. SDK mode

Best for pilots and internal development. Import the package and wrap tools directly.

## 2. Central API mode

Best for enterprise production. Agent services call a centralized policy API before tool execution.

## 3. Sidecar mode

Best for Kubernetes and high-throughput systems. A local sidecar enforces cached policies and streams audit events.

## 4. MCP gateway mode

Best when tools are exposed through MCP-style servers. The gateway controls tool visibility, argument policy, approval, and result redaction.

## Migration approach

1. Observe-only mode: log what agents are doing.
2. Enforce obvious deny rules.
3. Add approval rules for high-impact actions.
4. Move credentials behind the tool gateway.
5. Add deployment gates and recurring reviews.
