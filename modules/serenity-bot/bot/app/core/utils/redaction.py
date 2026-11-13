"""LLMObs Secret & PII Redaction and Input Guardrails for Serenity-Ops.

Automatically scrubs credentials, API tokens, AWS keys, private keys, and sensitive
patterns before data is sent to LLMs, Slack threads, DynamoDB, or CloudWatch logs.
"""

import re
from typing import Any

# Placeholder values seeded by Terraform before manual secret population
PLACEHOLDER_SECRETS = frozenset({
    "",
    "to-fill-manually",
    "placeholder",
    "changeme",
    "none",
    "null",
})


def is_configured_secret(value: str | None) -> bool:
    """Returns True only if the secret string is non-empty and not a Terraform placeholder."""
    if not value:
        return False
    return value.strip().lower() not in PLACEHOLDER_SECRETS


# Compiled regex patterns for secret & credential scrubbing
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # PEM Private Keys
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # AWS Access Key ID (AKIA / ASIA / AROA / AIDA)
    (
        re.compile(r"\b(A(?:KIA|SIA|ROA|IDA)[0-9A-Z]{16})\b"),
        "[REDACTED_AWS_KEY]",
    ),
    # Slack Bot, User, App & Configuration Tokens
    (
        re.compile(r"\b(xox[baprs]-[0-9A-Za-z-]+|xapp-[0-9A-Za-z-]+)\b"),
        "[REDACTED_SLACK_TOKEN]",
    ),
    # GitLab Personal, Project, Group, Runner & Deploy Tokens
    (
        re.compile(r"\b(gl(?:pat|dt|rt|ptt|soat)-[0-9A-Za-z_\-]{10,})\b"),
        "[REDACTED_GITLAB_TOKEN]",
    ),
    # GitHub Classic & Fine-Grained Tokens
    (
        re.compile(r"\b(gh[pousr]_[0-9A-Za-z_]{16,}|github_pat_[0-9A-Za-z_]{16,})\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    # Google Cloud / Gemini API Keys
    (
        re.compile(r"\b(AIza[0-9A-Za-z_\-]{30,})\b"),
        "[REDACTED_GOOGLE_KEY]",
    ),
    # Anthropic & OpenAI API Keys
    (
        re.compile(r"\b(sk-ant-[0-9A-Za-z_\-]{15,}|sk-(?:proj-)?[0-9A-Za-z_\-]{20,})\b"),
        "[REDACTED_API_KEY]",
    ),
    # Authorization Bearer / Basic Headers
    (
        re.compile(r"(?i)\b(Bearer|Basic)\s+([A-Za-z0-9._~+/=-]{12,})"),
        r"\1 [REDACTED_TOKEN]",
    ),
    # URLs with embedded user:password@host credentials
    (
        re.compile(r"(https?://[^/\s:@]+):([^@\s/]{3,})@"),
        r"\1:[REDACTED_PASSWORD]@",
    ),
    # Explicit key=value or "key": "value" secret assignments
    (
        re.compile(
            r"(?i)\b(aws_secret_access_key|secret_access_key|password|passwd|client_secret|"
            r"api_key|apikey|dd_api_key|dd_app_key|datadog_api_key|datadog_app_key|"
            r"slack_bot_token|slack_app_token|gitlab_token|github_token|grafana_token|"
            r"gemini_apikey|anthropic_api_key|openai_api_key)"
            r'(\s*[:=]\s*["\']?)([^"\'\s,;}{]{6,})(["\']?)'
        ),
        r"\1\2[REDACTED_SECRET]\4",
    ),
]

_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Guardrail patterns against prompt injection / secret exfiltration attempts
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions"),
    re.compile(r"(?i)(?:print|dump|reveal|exfiltrate|output|show)\s+(?:all\s+)?(?:environment\s+variables|env\s+vars|secrets|api\s+keys|system\s+prompt)"),
    re.compile(r"(?i)bypass\s+human[\s-]*in[\s-]*the[\s-]*loop"),
]


def redact_secrets(text: str, redact_emails: bool = False) -> str:
    """Scrubs known secret patterns, tokens, and optionally email addresses from a string."""
    if not text or not isinstance(text, str):
        return text

    scrubbed = text
    for pattern, replacement in _SECRET_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)

    if redact_emails:
        scrubbed = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", scrubbed)

    return scrubbed


def redact_data(value: Any, redact_emails: bool = False) -> Any:
    """Recursively scrubs secrets from strings, lists, and dictionaries."""
    if isinstance(value, str):
        return redact_secrets(value, redact_emails=redact_emails)
    if isinstance(value, list):
        return [redact_data(item, redact_emails=redact_emails) for item in value]
    if isinstance(value, dict):
        return {k: redact_data(v, redact_emails=redact_emails) for k, v in value.items()}
    return value


def check_prompt_guardrails(user_query: str) -> tuple[bool, str]:
    """Checks incoming user/alert text for prompt-injection or credential-exfiltration attempts.

    Returns:
        (is_safe, reason_if_blocked)
    """
    if not user_query:
        return True, ""

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(user_query):
            return (
                False,
                "Request blocked by Serenity-Ops security guardrails (detected instruction override or credential exfiltration attempt).",
            )
    return True, ""
