from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class GuardrailResult:
    passed: bool
    controls_triggered: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    redacted_text: str | None = None


class BasicGuardrails:
    """Small deterministic guardrail pack.

    These are intentionally conservative starter checks. They are not a full
    security system, but they provide hooks and examples for a production-grade
    guardrail service.
    """

    prompt_injection_patterns = [
        r"ignore (all )?(previous|prior) instructions",
        r"developer message",
        r"system prompt",
        r"reveal.*(secret|credential|api key|system prompt)",
        r"bypass.*(policy|guardrail|approval)",
        r"act as.*(admin|root|sudo)",
    ]
    pii_patterns = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "phone_like": r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)",
        "card_like": r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)",
    }

    def check_input(self, text: str) -> GuardrailResult:
        findings: list[str] = []
        controls: list[str] = []
        for pattern in self.prompt_injection_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                findings.append(f"Matched prompt-injection pattern: {pattern}")
                controls.append("prompt_injection_detection")
        return GuardrailResult(passed=not findings, controls_triggered=controls, findings=findings)

    def redact_pii(self, text: str) -> GuardrailResult:
        redacted = text
        controls: list[str] = []
        findings: list[str] = []
        for name, pattern in self.pii_patterns.items():
            if re.search(pattern, redacted):
                findings.append(f"Detected {name}")
                controls.append("pii_redaction")
                redacted = re.sub(pattern, f"[{name.upper()}_REDACTED]", redacted)
        return GuardrailResult(passed=True, controls_triggered=controls, findings=findings, redacted_text=redacted)
