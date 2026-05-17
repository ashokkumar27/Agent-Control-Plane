from __future__ import annotations

from .models import DataClass, RiskTier, ToolCard, ToolType


class StaticRiskClassifier:
    """Rule-based risk classifier for initial tool/agent inventory.

    Production systems can replace this with a richer assessment workflow, but
    keep the output deterministic and explainable for governance purposes.
    """

    restricted_data = {DataClass.PII, DataClass.PCI, DataClass.PHI, DataClass.SECRETS, DataClass.RESTRICTED}

    def classify_tool(self, tool: ToolCard) -> RiskTier:
        if tool.tool_type in {ToolType.CODE_EXECUTION, ToolType.FILESYSTEM}:
            return RiskTier.CRITICAL
        if tool.tool_type in {ToolType.SIDE_EFFECTING, ToolType.EXTERNAL_COMMUNICATION, ToolType.MCP}:
            if any(x in self.restricted_data or str(x) in {d.value for d in self.restricted_data} for x in tool.data_access):
                return RiskTier.HIGH
            return RiskTier.MEDIUM
        if any(x in self.restricted_data or str(x) in {d.value for d in self.restricted_data} for x in tool.data_access):
            return RiskTier.MEDIUM
        return RiskTier.LOW
