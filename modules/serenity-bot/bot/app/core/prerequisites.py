"""Startup prerequisite validation for IAM access, credentials, and enabled integrations."""

from datetime import datetime, timezone
import os
from typing import Any

import boto3
import requests

from app.config import settings
from app.core import hub
from app.core.utils.logging import get_logger, log_message
from app.core.utils.redaction import is_configured_secret, redact_secrets
from app.llm.providers import get_model_routing_chain

logger = get_logger("core.prerequisites")

HTTP_TIMEOUT_SECONDS = 5


def _make_check(name: str, enabled: bool, status: str, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "enabled": enabled,
        "status": status,
        "detail": redact_secrets(detail),
    }


def _check_slack(verify_live: bool) -> dict[str, Any]:
    if not is_configured_secret(settings.slack_bot_token) or not is_configured_secret(settings.slack_app_token):
        return _make_check(
            "slack",
            True,
            "ERROR",
            "Missing or placeholder SLACK_BOT_TOKEN / SLACK_APP_TOKEN.",
        )

    if not verify_live:
        return _make_check("slack", True, "OK", "Slack bot and app tokens configured.")

    try:
        resp = requests.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        data = resp.json() if resp.status_code == 200 else {}
        if resp.status_code == 200 and data.get("ok"):
            team = data.get("team", "unknown")
            return _make_check("slack", True, "OK", f"Authenticated to Slack workspace '{team}'.")
        err = data.get("error") or f"HTTP {resp.status_code}"
        return _make_check("slack", True, "ERROR", f"Slack auth.test failed: {err}.")
    except Exception as exc:
        return _make_check("slack", True, "ERROR", f"Slack connectivity check failed: {exc}")


def _check_aws_observability(verify_live: bool) -> dict[str, Any]:
    if not settings.aws_region:
        return _make_check("aws_observability", True, "ERROR", "AWS_REGION is not configured.")

    if not verify_live:
        return _make_check(
            "aws_observability",
            True,
            "OK",
            f"AWS region '{settings.aws_region}' configured (live IAM check skipped).",
        )

    try:
        sts = boto3.client("sts", region_name=settings.aws_region)
        identity = sts.get_caller_identity()
        account_id = identity.get("Account", "unknown")
        cw = boto3.client("cloudwatch", region_name=settings.aws_region)
        cw.describe_alarms(MaxRecords=1)
        return _make_check(
            "aws_observability",
            True,
            "OK",
            f"STS & CloudWatch observability read verified (account {account_id}, region {settings.aws_region}).",
        )
    except Exception as exc:
        return _make_check("aws_observability", True, "ERROR", f"AWS IAM observability check failed: {exc}")


def _check_llm_routing() -> dict[str, Any]:
    chain = get_model_routing_chain()
    if not chain:
        return _make_check(
            "llm_routing",
            True,
            "ERROR",
            f"No configured LLM provider available (primary='{settings.llm_primary_provider}').",
        )

    primary = chain[0]
    fallback_count = len(chain) - 1
    return _make_check(
        "llm_routing",
        True,
        "OK",
        f"Primary '{primary[0]}/{primary[1]}' ready ({fallback_count} fallback candidate(s)).",
    )


def _check_dynamodb_hub(verify_live: bool) -> dict[str, Any]:
    table_name = settings.dynamodb_table_name.strip()
    if not table_name:
        return _make_check("dynamodb_hub", False, "SKIPPED", "Standalone Slack-only mode (no hub table).")

    if not verify_live:
        return _make_check("dynamodb_hub", True, "OK", f"Hub table '{table_name}' configured.")

    try:
        client = boto3.client("dynamodb", region_name=settings.aws_region)
        resp = client.describe_table(TableName=table_name)
        table_status = (resp.get("Table") or {}).get("TableStatus", "UNKNOWN")
        return _make_check("dynamodb_hub", True, "OK", f"Table '{table_name}' reachable ({table_status}).")
    except Exception as exc:
        return _make_check("dynamodb_hub", True, "ERROR", f"DynamoDB Hub '{table_name}' check failed: {exc}")


def _check_gitlab(verify_live: bool) -> dict[str, Any]:
    if not settings.enable_gitlab:
        return _make_check("gitlab", False, "SKIPPED", "Integration disabled (ENABLE_GITLAB=false).")
    if not is_configured_secret(settings.gitlab_token):
        return _make_check("gitlab", True, "ERROR", "ENABLE_GITLAB=true but GITLAB_TOKEN is missing/placeholder.")
    if not verify_live:
        return _make_check("gitlab", True, "OK", f"GitLab token configured for '{settings.gitlab_url}'.")

    try:
        url = f"{settings.gitlab_url.rstrip('/')}/api/v4/user"
        resp = requests.get(url, headers={"PRIVATE-TOKEN": settings.gitlab_token}, timeout=HTTP_TIMEOUT_SECONDS)
        if resp.status_code == 200:
            user = resp.json().get("username", "unknown")
            return _make_check("gitlab", True, "OK", f"Authenticated to GitLab as '@{user}'.")
        return _make_check("gitlab", True, "ERROR", f"GitLab API check failed: HTTP {resp.status_code}.")
    except Exception as exc:
        return _make_check("gitlab", True, "ERROR", f"GitLab connectivity check failed: {exc}")


def _check_github(verify_live: bool) -> dict[str, Any]:
    if not settings.enable_github:
        return _make_check("github", False, "SKIPPED", "Integration disabled (ENABLE_GITHUB=false).")
    if not is_configured_secret(settings.github_token):
        return _make_check("github", True, "ERROR", "ENABLE_GITHUB=true but GITHUB_TOKEN is missing/placeholder.")
    if not verify_live:
        return _make_check("github", True, "OK", f"GitHub token configured for '{settings.github_url}'.")

    try:
        url = f"{settings.github_url.rstrip('/')}/rate_limit"
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            return _make_check("github", True, "OK", f"GitHub API token valid ({settings.github_url}).")
        return _make_check("github", True, "ERROR", f"GitHub API check failed: HTTP {resp.status_code}.")
    except Exception as exc:
        return _make_check("github", True, "ERROR", f"GitHub connectivity check failed: {exc}")


def _check_datadog(verify_live: bool) -> dict[str, Any]:
    if not settings.enable_datadog:
        return _make_check("datadog", False, "SKIPPED", "Integration disabled (ENABLE_DATADOG=false).")
    if not is_configured_secret(settings.datadog_api_key) or not is_configured_secret(settings.datadog_app_key):
        return _make_check(
            "datadog",
            True,
            "ERROR",
            "ENABLE_DATADOG=true but DATADOG_API_KEY / DATADOG_APP_KEY missing/placeholder.",
        )
    if not verify_live:
        return _make_check("datadog", True, "OK", "Datadog API and App keys configured.")

    dd_site = os.getenv("DD_SITE", "datadoghq.eu").strip() or "datadoghq.eu"
    try:
        resp = requests.get(
            f"https://api.{dd_site}/api/v1/validate",
            headers={
                "DD-API-KEY": settings.datadog_api_key,
                "DD-APPLICATION-KEY": settings.datadog_app_key,
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200 and resp.json().get("valid"):
            return _make_check("datadog", True, "OK", f"Datadog credentials valid ({dd_site}).")
        return _make_check("datadog", True, "ERROR", f"Datadog API validation failed: HTTP {resp.status_code}.")
    except Exception as exc:
        return _make_check("datadog", True, "ERROR", f"Datadog connectivity check failed: {exc}")


def _check_grafana(verify_live: bool) -> dict[str, Any]:
    if not settings.enable_grafana:
        return _make_check("grafana", False, "SKIPPED", "Integration disabled (ENABLE_GRAFANA=false).")
    if not settings.grafana_url:
        return _make_check("grafana", True, "ERROR", "ENABLE_GRAFANA=true but GRAFANA_URL is empty.")
    if not verify_live:
        return _make_check("grafana", True, "OK", f"Grafana URL configured ({settings.grafana_url}).")

    headers = {"Accept": "application/json"}
    if is_configured_secret(settings.grafana_token):
        headers["Authorization"] = f"Bearer {settings.grafana_token}"

    try:
        resp = requests.get(
            f"{settings.grafana_url.rstrip('/')}/api/health",
            headers=headers,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            return _make_check("grafana", True, "OK", f"Grafana health endpoint reachable ({settings.grafana_url}).")
        return _make_check("grafana", True, "ERROR", f"Grafana health check failed: HTTP {resp.status_code}.")
    except Exception as exc:
        return _make_check("grafana", True, "ERROR", f"Grafana connectivity check failed: {exc}")


def prerequisites_check(verify_live: bool = True, publish_hub: bool = True) -> dict[str, Any]:
    """Validates IAM permissions and API tokens at startup, logging and publishing results to serenity-ops-hub."""
    checks = [
        _check_slack(verify_live=verify_live),
        _check_aws_observability(verify_live=verify_live),
        _check_llm_routing(),
        _check_dynamodb_hub(verify_live=verify_live),
        _check_gitlab(verify_live=verify_live),
        _check_github(verify_live=verify_live),
        _check_datadog(verify_live=verify_live),
        _check_grafana(verify_live=verify_live),
    ]

    core_names = {"slack", "aws_observability", "llm_routing"}
    core_errors = [c for c in checks if c["name"] in core_names and c["status"] == "ERROR"]
    optional_errors = [c for c in checks if c["name"] not in core_names and c["enabled"] and c["status"] in ("ERROR", "WARN")]

    if core_errors:
        overall_status = "ERROR"
    elif optional_errors:
        overall_status = "DEGRADED"
    else:
        overall_status = "OK"

    report: dict[str, Any] = {
        "overall_status": overall_status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }

    log_level = "ERROR" if overall_status == "ERROR" else ("WARNING" if overall_status == "DEGRADED" else "INFO")
    log_message(
        f"Startup prerequisites check completed with status '{overall_status}'",
        level=log_level,
        extra={
            "overall_status": overall_status,
            "checks": {c["name"]: c["status"] for c in checks},
        },
    )
    for item in checks:
        if item["status"] in ("ERROR", "WARN"):
            logger.warning("Prerequisite '%s' [%s]: %s", item["name"], item["status"], item["detail"])

    if publish_hub:
        hub.record_prerequisites_status(report)

    return report
