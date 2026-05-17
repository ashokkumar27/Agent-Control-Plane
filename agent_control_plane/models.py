from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionType(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    REDACT = "redact"
    SANDBOX_ONLY = "sandbox_only"
    READ_ONLY_ONLY = "read_only_only"
    ESCALATE = "escalate"


class ToolType(str, Enum):
    READ_ONLY = "read_only"
    SIDE_EFFECTING = "side_effecting"
    EXTERNAL_COMMUNICATION = "external_communication"
    CODE_EXECUTION = "code_execution"
    FILESYSTEM = "filesystem"
    DATABASE = "database"
    MCP = "mcp"
    OTHER = "other"


class DataClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PII = "pii"
    PCI = "pci"
    PHI = "phi"
    SECRETS = "secrets"


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return to_dict(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def to_dict(value: Any) -> dict[str, Any]:
    """Dataclass-safe dict conversion that emits enum values."""
    raw = asdict(value) if is_dataclass(value) else dict(value)
    return json.loads(json.dumps(raw, default=_json_default, sort_keys=True))


def stable_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class AgentCard:
    """Governance registration for an agent.

    This is the source of truth for ownership, purpose, allowed capabilities,
    risk tier, data handled, and human oversight obligations.
    """

    agent_id: str
    owner: str
    purpose: str
    risk_tier: RiskTier | str = RiskTier.MEDIUM
    framework: str | None = None
    model: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    prohibited_tools: list[str] = field(default_factory=list)
    data_processed: list[DataClass | str] = field(default_factory=list)
    affected_users: list[str] = field(default_factory=list)
    business_owner: str | None = None
    technical_owner: str | None = None
    human_oversight: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.risk_tier = RiskTier(self.risk_tier)
        self.data_processed = [DataClass(x) if x in DataClass._value2member_map_ else x for x in self.data_processed]

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass(slots=True)
class ToolCard:
    """Governance registration for a callable tool/capability."""

    name: str
    description: str
    tool_type: ToolType | str = ToolType.READ_ONLY
    risk_tier: RiskTier | str = RiskTier.LOW
    side_effect: bool = False
    data_access: list[DataClass | str] = field(default_factory=list)
    allowed_roles: list[str] = field(default_factory=list)
    approval_rules: list[str] = field(default_factory=list)
    resource_scope: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tool_type = ToolType(self.tool_type)
        self.risk_tier = RiskTier(self.risk_tier)
        self.data_access = [DataClass(x) if x in DataClass._value2member_map_ else x for x in self.data_access]
        if self.tool_type in {ToolType.SIDE_EFFECTING, ToolType.EXTERNAL_COMMUNICATION, ToolType.CODE_EXECUTION, ToolType.FILESYSTEM, ToolType.MCP}:
            self.side_effect = self.side_effect or self.tool_type != ToolType.READ_ONLY

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass(slots=True)
class ToolCall:
    call_id: str
    run_id: str
    agent_id: str
    user_id: str | None
    tool_name: str
    args: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass(slots=True)
class PolicyRule:
    rule_id: str
    effect: DecisionType | str
    description: str
    when: dict[str, Any] = field(default_factory=dict)
    priority: int = 100
    reason: str | None = None
    approver_role: str | None = None
    controls: list[str] = field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.effect = DecisionType(self.effect)

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass(slots=True)
class PolicyDecision:
    decision: DecisionType | str
    reason: str
    matched_rules: list[str] = field(default_factory=list)
    approver_role: str | None = None
    controls: list[str] = field(default_factory=list)
    redactions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    decision_id: str = field(default_factory=lambda: new_id("decision"))
    timestamp: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.decision = DecisionType(self.decision)

    @property
    def allowed(self) -> bool:
        return self.decision == DecisionType.ALLOW

    @property
    def denied(self) -> bool:
        return self.decision == DecisionType.DENY

    @property
    def requires_approval(self) -> bool:
        return self.decision == DecisionType.REQUIRE_APPROVAL

    def to_agent_message(self) -> dict[str, Any]:
        return {
            "status": self.decision.value,
            "decision_id": self.decision_id,
            "reason": self.reason,
            "matched_rules": self.matched_rules,
            "approver_role": self.approver_role,
        }

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass(slots=True)
class ApprovalRequest:
    approval_id: str
    tool_call: ToolCall
    decision: PolicyDecision
    status: str = "pending"
    requested_at: str = field(default_factory=utc_now_iso)
    decided_at: str | None = None
    approver_id: str | None = None
    approver_role: str | None = None
    modified_args: dict[str, Any] | None = None
    notes: str | None = None

    def approve(self, approver_id: str, approver_role: str | None = None, modified_args: dict[str, Any] | None = None, notes: str | None = None) -> None:
        self.status = "approved"
        self.decided_at = utc_now_iso()
        self.approver_id = approver_id
        self.approver_role = approver_role
        self.modified_args = modified_args
        self.notes = notes

    def reject(self, approver_id: str, approver_role: str | None = None, notes: str | None = None) -> None:
        self.status = "rejected"
        self.decided_at = utc_now_iso()
        self.approver_id = approver_id
        self.approver_role = approver_role
        self.notes = notes

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass(slots=True)
class EvidenceRecord:
    record_id: str
    run_id: str
    agent_id: str
    event_type: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=utc_now_iso)
    previous_hash: str | None = None
    evidence_hash: str | None = None

    def seal(self) -> "EvidenceRecord":
        data = {
            "record_id": self.record_id,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
        }
        self.evidence_hash = stable_hash(data)
        return self

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass(slots=True)
class IncidentRecord:
    incident_id: str
    run_id: str | None
    agent_id: str | None
    severity: RiskTier | str
    title: str
    description: str
    status: str = "open"
    created_at: str = field(default_factory=utc_now_iso)
    controls_triggered: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.severity = RiskTier(self.severity)

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)
