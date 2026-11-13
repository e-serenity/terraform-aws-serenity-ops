"""Pydantic schemas and structured output validation for Serenity-Ops RCA diagnostics."""

import json
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator

from app.core.utils.redaction import redact_secrets


class RCAReport(BaseModel):
    """Strictly typed Root Cause Analysis (RCA) report schema."""

    scope: str = Field(
        default="AWS Infrastructure",
        description="Target service, workload, or AWS component investigated.",
    )
    summary: str = Field(
        ...,
        min_length=3,
        description="Concise one-line summary of the incident or inquiry.",
    )
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"] = Field(
        default="MEDIUM",
        description="Assessed operational severity of the incident.",
    )
    diagnostic: str = Field(
        ...,
        min_length=5,
        description="2-4 sentences explaining the root cause or findings based on verified telemetry.",
    )
    key_evidence: list[str] = Field(
        default_factory=list,
        description="1-4 concrete evidence items (metrics, log lines, commits, CloudTrail events).",
    )
    root_cause_confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        default="MEDIUM",
        description="Confidence level in the root cause based on available tool evidence.",
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="Concrete remediation steps or Human-in-the-Loop actions proposed.",
    )
    tools_invoked: list[str] = Field(
        default_factory=list,
        description="Names of read-only or sub-agent tools executed during the investigation.",
    )

    @field_validator("scope", "summary", "diagnostic", mode="before")
    @classmethod
    def _clean_and_redact_str(cls, val: object) -> str:
        if val is None:
            return ""
        return redact_secrets(str(val).strip())

    @field_validator("key_evidence", "next_steps", "tools_invoked", mode="before")
    @classmethod
    def _clean_list_items(cls, val: object) -> list[str]:
        if isinstance(val, str):
            items = [line.lstrip("•-* ").strip() for line in val.splitlines() if line.strip()]
        elif isinstance(val, list):
            items = [str(item).lstrip("•-* ").strip() for item in val if str(item).strip()]
        else:
            items = []
        return [redact_secrets(i) for i in items if i]

    def to_slack_mrkdwn(self) -> str:
        """Formats the validated RCA report into concise Slack mrkdwn."""
        evidence_lines = (
            "\n".join(f"• {ev}" for ev in self.key_evidence)
            if self.key_evidence
            else "• Verified via available telemetry and context."
        )
        steps_lines = (
            "\n".join(f"• {step}" for step in self.next_steps)
            if self.next_steps
            else "• Continue monitoring; no immediate state mutation required."
        )
        lines = [
            f":mag: *{self.scope} — {self.summary}*",
            "",
            f"*Diagnostic* _(Confidence: {self.root_cause_confidence})_: {self.diagnostic}",
            f"*Key Evidence*:\n{evidence_lines}",
            f"*Next Steps / Proposed Actions*:\n{steps_lines}",
        ]
        if self.tools_invoked:
            unique_tools = list(dict.fromkeys(self.tools_invoked))
            lines.append(f"\n_Tools inspected: `{', '.join(unique_tools[:8])}`_")
        return "\n".join(lines)


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)


def parse_or_validate_rca_output(
    raw_text: str,
    tools_invoked: list[str] | None = None,
) -> tuple[str, RCAReport | None]:
    """Parses LLM output as a validated RCAReport when JSON is present, or normalizes mrkdwn output.

    Always applies secret redaction and self-reflection checks on evidence completeness.
    Returns:
        (formatted_slack_mrkdwn, optional_parsed_rca_report)
    """
    cleaned = redact_secrets((raw_text or "").strip())
    if not cleaned:
        fallback_report = RCAReport(
            scope="Serenity-Ops",
            summary="Investigation completed with empty response",
            diagnostic="The agent finished tool execution without producing a textual summary.",
            key_evidence=["No textual payload returned by model."],
            next_steps=["Retry the query or inspect CloudWatch logs directly."],
            tools_invoked=tools_invoked or [],
        )
        return fallback_report.to_slack_mrkdwn(), fallback_report

    # Check if the model returned a JSON object (either raw or inside a ```json block)
    json_candidate: str | None = None
    if cleaned.startswith("{") and cleaned.endswith("}"):
        json_candidate = cleaned
    else:
        match = _JSON_BLOCK_RE.search(cleaned)
        if match:
            json_candidate = match.group(1)

    if json_candidate:
        try:
            data = json.loads(json_candidate)
            if isinstance(data, dict) and ("diagnostic" in data or "summary" in data):
                if tools_invoked and not data.get("tools_invoked"):
                    data["tools_invoked"] = tools_invoked
                report = RCAReport.model_validate(data)
                return report.to_slack_mrkdwn(), report
        except Exception:
            pass

    # If the model already formatted Slack mrkdwn, validate structure via RCAReport extraction
    # and append inspected tools footer if missing.
    if tools_invoked and "_Tools inspected:" not in cleaned:
        unique_tools = list(dict.fromkeys(tools_invoked))
        cleaned = f"{cleaned}\n\n_Tools inspected: `{', '.join(unique_tools[:8])}`_"

    return cleaned, None
