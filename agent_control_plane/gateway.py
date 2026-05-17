from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .approvals import ApprovalQueue, InMemoryApprovalQueue
from .guardrails import BasicGuardrails
from .idempotency import IdempotencyStore, InMemoryIdempotencyStore, tool_call_fingerprint
from .ledger import AuditLedger, InMemoryAuditLedger
from .models import AgentCard, DecisionType, PolicyDecision, ToolCall, ToolCard, new_id
from .policy import PolicyEngine
from .registries import AgentRegistry, ToolRegistry


class AgentControlPlane:
    """Framework-agnostic governance runtime.

    Main entry point:
        - register agents and tools
        - intercept proposed tool calls
        - enforce deterministic policy
        - create human approval requests
        - execute allowed tools
        - append evidence records
    """

    def __init__(
        self,
        *,
        agents: AgentRegistry | None = None,
        tools: ToolRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        approvals: ApprovalQueue | None = None,
        idempotency: IdempotencyStore | None = None,
        ledger: AuditLedger | None = None,
        guardrails: BasicGuardrails | None = None,
    ) -> None:
        self.agents = agents or AgentRegistry()
        self.tools = tools or ToolRegistry()
        self.policy_engine = policy_engine or PolicyEngine()
        self.approvals = approvals or InMemoryApprovalQueue()
        self.idempotency = idempotency or InMemoryIdempotencyStore()
        self.ledger = ledger or InMemoryAuditLedger()
        self.guardrails = guardrails or BasicGuardrails()

    def register_agent(self, agent: AgentCard) -> None:
        self.agents.register(agent)
        self.ledger.append(
            run_id="registry",
            agent_id=agent.agent_id,
            event_type="agent_registered",
            payload={"agent": agent.to_dict()},
        )

    def register_tool(self, card: ToolCard, handler: Callable[..., Any] | None = None) -> None:
        self.tools.register(card, handler)
        self.ledger.append(
            run_id="registry",
            agent_id="system",
            event_type="tool_registered",
            payload={"tool": card.to_dict()},
        )

    def register_decorated_tool(self, fn: Callable[..., Any]) -> None:
        card = getattr(fn, "__tool_card__", None)
        if card is None:
            raise ValueError("Function is missing __tool_card__. Use @governed_tool(...).")
        self.register_tool(card, fn)

    def propose_tool_call(
        self,
        *,
        agent_id: str,
        tool_name: str,
        args: dict[str, Any],
        user_id: str | None = None,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[ToolCall, PolicyDecision]:
        """Authorize a tool call without executing it."""
        run_id = run_id or new_id("run")
        context = dict(context or {})
        input_text = context.get("input")
        if self.guardrails is not None and isinstance(input_text, str):
            input_guardrail = self.guardrails.check_input(input_text)
            context.setdefault("guardrails", {})["input"] = {
                "passed": input_guardrail.passed,
                "controls_triggered": input_guardrail.controls_triggered,
                "findings": input_guardrail.findings,
            }
        agent = self.agents.get(agent_id)
        tool = self.tools.get_card(tool_name)
        call = ToolCall(
            call_id=new_id("call"),
            run_id=run_id,
            agent_id=agent_id,
            user_id=user_id,
            tool_name=tool_name,
            args=args,
            idempotency_key=idempotency_key,
            context=context,
        )
        decision = self.policy_engine.authorize(agent=agent, tool=tool, tool_call=call)
        self.ledger.append(
            run_id=run_id,
            agent_id=agent_id,
            event_type="tool_call_proposed",
            payload={"tool_call": call.to_dict(), "policy_decision": decision.to_dict()},
        )
        return call, decision

    def execute_tool(
        self,
        *,
        agent_id: str,
        tool_name: str,
        args: dict[str, Any],
        user_id: str | None = None,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Authorize and execute a tool call if allowed.

        Return shape is intentionally JSON-like so it can be handed directly
        back to an LLM tool-calling loop.
        """
        call, decision = self.propose_tool_call(
            agent_id=agent_id,
            tool_name=tool_name,
            args=args,
            user_id=user_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            context=context,
        )

        if decision.denied:
            result = {"status": "denied", "reason": decision.reason, "decision": decision.to_dict()}
            self.ledger.append(run_id=call.run_id, agent_id=agent_id, event_type="tool_call_denied", payload=result)
            return result

        if decision.requires_approval:
            approval = self.approvals.create(call, decision)
            result = {
                "status": "approval_required",
                "approval_id": approval.approval_id,
                "reason": decision.reason,
                "approver_role": decision.approver_role,
                "decision": decision.to_dict(),
            }
            self.ledger.append(run_id=call.run_id, agent_id=agent_id, event_type="approval_requested", payload=approval.to_dict())
            return result

        if decision.decision != DecisionType.ALLOW:
            result = {"status": decision.decision.value, "reason": decision.reason, "decision": decision.to_dict()}
            self.ledger.append(run_id=call.run_id, agent_id=agent_id, event_type="tool_call_controlled", payload=result)
            return result

        return self._execute_authorized_call(call=call, decision=decision)

    def guarded_callable(
        self,
        *,
        agent_id: str,
        tool_name: str,
        user_id: str | None = None,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        """Return a developer-friendly callable that routes through the control plane.

        Example:
            refund = plane.guarded_callable(agent_id="support_agent", tool_name="issue_refund")
            result = refund(order_id="A123", amount=25, reason="late delivery")
        """
        def _wrapped(**kwargs: Any) -> dict[str, Any]:
            return self.execute_tool(
                agent_id=agent_id,
                tool_name=tool_name,
                args=kwargs,
                user_id=user_id,
                run_id=run_id,
                idempotency_key=idempotency_key,
                context=context,
            )
        return _wrapped

    def approve_and_execute(
        self,
        approval_id: str,
        *,
        approver_id: str,
        approver_role: str | None = None,
        modified_args: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Approve a pending request and execute the underlying tool."""
        approval = self.approvals.approve(
            approval_id,
            approver_id=approver_id,
            approver_role=approver_role,
            modified_args=modified_args,
            notes=notes,
        )
        call = approval.tool_call
        if modified_args is not None:
            call.args = modified_args
        if idempotency_key is not None:
            call.idempotency_key = idempotency_key
        self.ledger.append(
            run_id=call.run_id,
            agent_id=call.agent_id,
            event_type="approval_approved",
            payload=approval.to_dict(),
        )

        # Re-authorize the final arguments after approval. This prevents a risky
        # pattern where an approver changes arguments into a higher-risk action
        # than the original request, such as support approval for a finance-level
        # refund. A matching approval role can satisfy a require_approval result;
        # a deny result always blocks execution.
        agent = self.agents.get(call.agent_id)
        tool = self.tools.get_card(call.tool_name)
        final_decision = self.policy_engine.authorize(agent=agent, tool=tool, tool_call=call)
        if final_decision.denied:
            result = {"status": "denied", "reason": final_decision.reason, "decision": final_decision.to_dict()}
            self.ledger.append(run_id=call.run_id, agent_id=call.agent_id, event_type="approved_tool_call_denied_on_recheck", payload=result)
            return result
        if final_decision.requires_approval and final_decision.approver_role and final_decision.approver_role != approver_role:
            new_approval = self.approvals.create(call, final_decision)
            result = {
                "status": "approval_required",
                "approval_id": new_approval.approval_id,
                "reason": final_decision.reason,
                "approver_role": final_decision.approver_role,
                "decision": final_decision.to_dict(),
            }
            self.ledger.append(run_id=call.run_id, agent_id=call.agent_id, event_type="approval_recheck_requires_higher_approval", payload=result)
            return result

        approval_decision = PolicyDecision(
            decision=DecisionType.ALLOW,
            reason=f"Approved by {approver_id}",
            matched_rules=final_decision.matched_rules,
            controls=sorted(set(final_decision.controls + ["human_approval"])),
            metadata={"approval_id": approval.approval_id, "satisfied_policy_decision": final_decision.decision_id},
        )
        return self._execute_authorized_call(call=call, decision=approval_decision)

    def reject_approval(
        self,
        approval_id: str,
        *,
        approver_id: str,
        approver_role: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        approval = self.approvals.reject(
            approval_id,
            approver_id=approver_id,
            approver_role=approver_role,
            notes=notes,
        )
        self.ledger.append(
            run_id=approval.tool_call.run_id,
            agent_id=approval.tool_call.agent_id,
            event_type="approval_rejected",
            payload=approval.to_dict(),
        )
        return {"status": "rejected", "approval_id": approval_id, "notes": notes}

    def _execute_authorized_call(self, *, call: ToolCall, decision: PolicyDecision) -> dict[str, Any]:
        if call.idempotency_key:
            request_hash = tool_call_fingerprint(
                agent_id=call.agent_id,
                user_id=call.user_id,
                tool_name=call.tool_name,
                args=call.args,
            )
            record, started = self.idempotency.start(call.idempotency_key, request_hash)
            if not started:
                if record.request_hash != request_hash:
                    result = {
                        "status": "idempotency_conflict",
                        "reason": "Idempotency key was already used for a different request.",
                        "idempotency": {"key": call.idempotency_key, "replayed": False},
                        "decision": decision.to_dict(),
                        "call_id": call.call_id,
                    }
                    self.ledger.append(
                        run_id=call.run_id,
                        agent_id=call.agent_id,
                        event_type="idempotency_conflict",
                        payload={"tool_call": call.to_dict(), "result": result, "existing_record": record.to_dict()},
                    )
                    return result
                if record.status == "completed" and record.result is not None:
                    result = dict(record.result)
                    result["idempotency"] = {"key": call.idempotency_key, "replayed": True}
                    self.ledger.append(
                        run_id=call.run_id,
                        agent_id=call.agent_id,
                        event_type="idempotency_replayed",
                        payload={"tool_call": call.to_dict(), "result": result},
                    )
                    return result
                result = {
                    "status": "idempotency_in_progress",
                    "reason": "Idempotency key is already being processed.",
                    "idempotency": {"key": call.idempotency_key, "replayed": False},
                    "decision": decision.to_dict(),
                    "call_id": call.call_id,
                }
                self.ledger.append(
                    run_id=call.run_id,
                    agent_id=call.agent_id,
                    event_type="idempotency_in_progress",
                    payload={"tool_call": call.to_dict(), "result": result, "existing_record": record.to_dict()},
                )
                return result

            self.ledger.append(
                run_id=call.run_id,
                agent_id=call.agent_id,
                event_type="idempotency_started",
                payload={"tool_call": call.to_dict(), "idempotency_record": record.to_dict()},
            )
            result = self._execute_once(call=call, decision=decision)
            result["idempotency"] = {"key": call.idempotency_key, "replayed": False}
            completed = self.idempotency.complete(call.idempotency_key, request_hash, result)
            self.ledger.append(
                run_id=call.run_id,
                agent_id=call.agent_id,
                event_type="idempotency_completed",
                payload={"tool_call": call.to_dict(), "result": result, "idempotency_record": completed.to_dict()},
            )
            return result

        return self._execute_once(call=call, decision=decision)

    def _execute_once(self, *, call: ToolCall, decision: PolicyDecision) -> dict[str, Any]:
        try:
            handler = self.tools.get_handler(call.tool_name)
            output = handler(**call.args)
            result = {"status": "success", "output": output, "decision": decision.to_dict(), "call_id": call.call_id}
            self.ledger.append(
                run_id=call.run_id,
                agent_id=call.agent_id,
                event_type="tool_call_executed",
                payload={"tool_call": call.to_dict(), "result": result},
            )
            return result
        except Exception as exc:  # noqa: BLE001 - tool errors must be captured for audit
            result = {"status": "tool_error", "error": str(exc), "decision": decision.to_dict(), "call_id": call.call_id}
            self.ledger.append(
                run_id=call.run_id,
                agent_id=call.agent_id,
                event_type="tool_call_error",
                payload={"tool_call": call.to_dict(), "result": result},
            )
            return result
