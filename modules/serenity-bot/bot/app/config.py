import json
import os
from dataclasses import dataclass, field
from typing import Any


def _as_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    environment: str = os.getenv("ENVIRONMENT", "preprod")
    aws_region: str = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "eu-west-3"))
    health_port: int = int(os.getenv("HEALTH_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Slack Credentials
    slack_bot_token: str = os.getenv("SLACK_BOT_TOKEN", "")
    slack_app_token: str = os.getenv("SLACK_APP_TOKEN", "")

    # LLM Settings (Unified Multi-Provider Routing with AWS Bedrock default & Fallback)
    claude_model: str = os.getenv("CLAUDE_MODEL", "global.anthropic.claude-sonnet-4-6")
    gemini_api_key: str = os.getenv("GEMINI_APIKEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    gemini_fallback_model: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    llm_primary_provider: str = os.getenv("LLM_PRIMARY_PROVIDER", "bedrock")
    llm_primary_model: str = os.getenv("LLM_PRIMARY_MODEL", "")
    llm_fallback_provider: str = os.getenv("LLM_FALLBACK_PROVIDER", "gemini")
    llm_fallback_model: str = os.getenv("LLM_FALLBACK_MODEL", "")

    # Agentic Guardrails, Token Budget & Circuit Breaker
    max_token_budget: int = int(os.getenv("MAX_TOKEN_BUDGET", "32000"))
    max_tool_iterations: int = int(os.getenv("MAX_TOOL_ITERATIONS", "12"))
    enable_pii_redaction: bool = _as_bool(os.getenv("ENABLE_PII_REDACTION"), default=True)

    # DynamoDB Hub (serenity-ops-hub)
    dynamodb_table_name: str = os.getenv("DYNAMODB_TABLE_NAME", "")
    history_retention_days: int = int(os.getenv("HISTORY_RETENTION_DAYS", "90"))

    # Integrations: Datadog
    enable_datadog: bool = _as_bool(os.getenv("ENABLE_DATADOG"))
    datadog_api_key: str = os.getenv("DATADOG_API_KEY", "")
    datadog_app_key: str = os.getenv("DATADOG_APP_KEY", "")
    datadog_bot_ids: set[str] = field(
        default_factory=lambda: {b.strip() for b in os.getenv("DATADOG_BOT_IDS", "").split(",") if b.strip()}
    )

    # Integrations: GitLab
    enable_gitlab: bool = _as_bool(os.getenv("ENABLE_GITLAB"))
    gitlab_token: str = os.getenv("GITLAB_TOKEN", "")
    gitlab_url: str = os.getenv("GITLAB_URL", "https://gitlab.com")
    gitlab_allowed_namespace: str = os.getenv("GITLAB_ALLOWED_NAMESPACE", "").strip()

    # Integrations: GitHub
    enable_github: bool = _as_bool(os.getenv("ENABLE_GITHUB"))
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_url: str = os.getenv("GITHUB_URL", "https://api.github.com")
    github_allowed_owner: str = os.getenv("GITHUB_ALLOWED_OWNER", "").strip()

    # Integrations: Grafana / Prometheus Alertmanager
    enable_grafana: bool = _as_bool(os.getenv("ENABLE_GRAFANA"))
    grafana_url: str = os.getenv("GRAFANA_URL", "").rstrip("/")
    grafana_token: str = os.getenv("GRAFANA_TOKEN", "")

    # MCP Dynamic Configuration
    mcp_servers_raw: str = os.getenv("MCP_SERVERS_CONFIG", "{}")

    # Custom Application & Architecture Context
    application_context_raw: str = os.getenv("APPLICATION_CONTEXT", "{}")

    @property
    def effective_primary_model(self) -> str:
        if self.llm_primary_model and self.llm_primary_model.strip():
            return self.llm_primary_model.strip()
        return self.claude_model

    @property
    def effective_fallback_model(self) -> str:
        if self.llm_fallback_model and self.llm_fallback_model.strip():
            return self.llm_fallback_model.strip()
        return self.gemini_model

    @property
    def mcp_servers_config(self) -> dict[str, Any]:
        try:
            return json.loads(self.mcp_servers_raw)
        except Exception:
            return {}

    @property
    def application_context(self) -> dict[str, Any]:
        try:
            return json.loads(self.application_context_raw)
        except Exception:
            return {}


settings = Settings()
