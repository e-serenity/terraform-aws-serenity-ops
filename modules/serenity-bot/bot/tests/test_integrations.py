import json
import logging
from app.config import settings
from app.core.utils.logging import JsonFormatter
from app.integrations import load_all_integration_tools
from app.integrations.alert_detector import is_inbound_alert, parse_inbound_alert
from app.integrations.datadog import enrich_mcp_config
from app.integrations.github import load_github_tools
from app.integrations.gitlab import load_gitlab_tools
from app.integrations.grafana import load_grafana_tools


def test_gitlab_tools_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "enable_gitlab", False)
    tools = load_gitlab_tools()
    assert tools == []


def test_gitlab_tools_enabled_without_token(monkeypatch):
    monkeypatch.setattr(settings, "enable_gitlab", True)
    monkeypatch.setattr(settings, "gitlab_token", "")
    tools = load_gitlab_tools()
    assert tools == []


def test_gitlab_tools_enabled_with_token(monkeypatch):
    monkeypatch.setattr(settings, "enable_gitlab", True)
    monkeypatch.setattr(settings, "gitlab_token", "glpat-fake-token")
    tools = load_gitlab_tools()
    assert len(tools) == 5
    tool_names = [t.name for t in tools]
    assert "gitlab_list_recent_mrs" in tool_names
    assert "gitlab_inspect_file" in tool_names


def test_github_tools_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "enable_github", False)
    tools = load_github_tools()
    assert tools == []


def test_github_tools_enabled_with_token(monkeypatch):
    monkeypatch.setattr(settings, "enable_github", True)
    monkeypatch.setattr(settings, "github_token", "ghp_fake_token")
    tools = load_github_tools()
    assert len(tools) == 3
    tool_names = [t.name for t in tools]
    assert "github_list_recent_prs" in tool_names
    assert "github_inspect_file" in tool_names


def test_grafana_tools_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "enable_grafana", False)
    tools = load_grafana_tools()
    assert tools == []


def test_grafana_tools_enabled_with_url(monkeypatch):
    monkeypatch.setattr(settings, "enable_grafana", True)
    monkeypatch.setattr(settings, "grafana_url", "https://grafana.internal.com")
    tools = load_grafana_tools()
    assert len(tools) == 2
    tool_names = [t.name for t in tools]
    assert "grafana_list_alerts" in tool_names
    assert "grafana_query_metric" in tool_names


def test_load_all_integration_tools(monkeypatch):
    monkeypatch.setattr(settings, "enable_gitlab", True)
    monkeypatch.setattr(settings, "gitlab_token", "glpat-fake")
    monkeypatch.setattr(settings, "enable_github", True)
    monkeypatch.setattr(settings, "github_token", "ghp_fake")
    monkeypatch.setattr(settings, "enable_grafana", False)

    all_tools = load_all_integration_tools()
    assert len(all_tools) == 8 + 5 + 3  # 8 AWS + 5 GitLab + 3 GitHub
    names = [t.name for t in all_tools]
    assert "aws_cloudwatch_describe_alarms" in names
    assert "aws_ecs_describe_services" in names
    assert "aws_rds_describe_db_instances" in names
    assert "aws_cloudtrail_lookup_events" in names
    assert "aws_dynamodb_describe_table" in names
    assert "aws_lambda_get_function" in names
    assert "gitlab_list_commits" in names
    assert "github_list_commits" in names


def test_aws_ecs_rds_cloudtrail_tools_mocked(monkeypatch):
    import boto3
    from app.integrations.aws import (
        aws_cloudtrail_lookup_events,
        aws_ecs_describe_services,
        aws_rds_describe_db_instances,
    )

    class FakeECSClient:
        def describe_services(self, cluster, services):
            return {
                "services": [
                    {
                        "serviceName": "order-api",
                        "status": "ACTIVE",
                        "desiredCount": 2,
                        "runningCount": 1,
                        "pendingCount": 1,
                        "taskDefinition": "arn:aws:ecs:eu-west-3:123:task-definition/order-api:42",
                        "deployments": [
                            {
                                "status": "PRIMARY",
                                "rolloutState": "IN_PROGRESS",
                                "taskDefinition": "arn:aws:ecs:eu-west-3:123:task-definition/order-api:42",
                                "runningCount": 1,
                                "desiredCount": 2,
                            }
                        ],
                        "events": [
                            {"createdAt": "2026-11-12 14:00:00", "message": "service order-api has started 1 tasks"}
                        ],
                    }
                ]
            }

    class FakeRDSClient:
        def describe_db_instances(self, **kwargs):
            return {
                "DBInstances": [
                    {
                        "DBInstanceIdentifier": "prod-postgres",
                        "DBInstanceStatus": "available",
                        "Engine": "postgres",
                        "EngineVersion": "16.3",
                        "DBInstanceClass": "db.t4g.medium",
                        "MultiAZ": True,
                        "AllocatedStorage": 100,
                        "Endpoint": {"Address": "prod-postgres.abc.eu-west-3.rds.amazonaws.com"},
                    }
                ]
            }

        def describe_events(self, **kwargs):
            return {
                "Events": [
                    {
                        "Date": "2026-11-12 13:55:00",
                        "SourceIdentifier": "prod-postgres",
                        "Message": "Multi-AZ instance failover completed.",
                    }
                ]
            }

    class FakeCloudTrailClient:
        def lookup_events(self, **kwargs):
            return {
                "Events": [
                    {
                        "EventTime": "2026-11-12 13:50:00",
                        "EventName": "UpdateService",
                        "EventSource": "ecs.amazonaws.com",
                        "Username": "ci-deployer",
                        "Resources": [{"ResourceType": "AWS::ECS::Service", "ResourceName": "order-api"}],
                        "CloudTrailEvent": json.dumps({"eventName": "UpdateService"}),
                    }
                ]
            }

    def fake_boto3_client(service_name, **kwargs):
        if service_name == "ecs":
            return FakeECSClient()
        if service_name == "rds":
            return FakeRDSClient()
        if service_name == "cloudtrail":
            return FakeCloudTrailClient()
        raise ValueError(f"Unexpected service: {service_name}")

    monkeypatch.setattr(boto3, "client", fake_boto3_client)

    ecs_out = aws_ecs_describe_services.invoke({"cluster_name": "prod-cluster", "service_names": "order-api"})
    assert "order-api:42" in ecs_out
    assert "IN_PROGRESS" in ecs_out

    rds_out = aws_rds_describe_db_instances.invoke({"db_instance_identifier": "prod-postgres"})
    assert "prod-postgres" in rds_out
    assert "Multi-AZ instance failover completed" in rds_out

    ct_out = aws_cloudtrail_lookup_events.invoke({"lookup_attribute_key": "EventName", "lookup_attribute_value": "UpdateService"})
    assert "UpdateService" in ct_out
    assert "ci-deployer" in ct_out


def test_aws_lambda_get_function_uses_configuration_only(monkeypatch):
    import boto3
    from app.integrations.aws import aws_lambda_get_function

    class FakeLambdaClient:
        def get_function_configuration(self, FunctionName):
            return {
                "FunctionName": FunctionName,
                "Runtime": "python3.12",
                "MemorySize": 256,
                "Timeout": 30,
                "LastModified": "2026-11-13T18:00:00.000+0000",
                "Environment": {"Variables": {"ENVIRONMENT": "preprod", "LOG_LEVEL": "INFO"}},
            }

        def get_function(self, FunctionName):
            raise AssertionError("get_function (code access) must not be called; use get_function_configuration")

    monkeypatch.setattr(boto3, "client", lambda service_name, **kwargs: FakeLambdaClient())

    out = aws_lambda_get_function.invoke({"function_name": "serenity-api"})
    assert "serenity-api" in out
    assert "python3.12" in out
    assert "256 MB" in out
    assert "ENVIRONMENT, LOG_LEVEL" in out


def test_alert_detector_ignore_recovery():
    recovery_event = {
        "subtype": "bot_message",
        "bot_id": "B12345",
        "text": "CRITICAL: Service high latency",
        "attachments": [{"text": "Recovered: latency back to normal"}],
    }
    assert is_inbound_alert(recovery_event) is False
    assert parse_inbound_alert(recovery_event) is None


def test_alert_detector_active_alert():
    alert_event = {
        "subtype": "bot_message",
        "bot_id": "B12345",
        "text": "ALARM: High 5XX error rate on API Gateway",
        "attachments": [{"text": "Triggered: threshold > 5%"}],
    }
    assert is_inbound_alert(alert_event) is True
    parsed = parse_inbound_alert(alert_event)
    assert parsed is not None
    assert parsed.is_alert is True
    assert parsed.source == "aws_cloudwatch"
    assert parsed.severity == "HIGH"


def test_alert_detector_cloudwatch_platform_alarm():
    platform_alarm_event = {
        "subtype": "bot_message",
        "bot_id": "B99999",
        "text": ":rotating_light: alarm: [ALARM] CloudWatch Alarm firing on Serenity-Ops Platform",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Alarm Name: serenity-bot-preprod-ecs-high-cpu"},
            }
        ],
    }
    parsed = parse_inbound_alert(platform_alarm_event)
    assert parsed is not None
    assert parsed.source == "aws_cloudwatch"
    assert parsed.severity == "CRITICAL"


def test_alert_detector_grafana_alert():
    grafana_event = {
        "subtype": "bot_message",
        "bot_id": "B88888",
        "username": "Grafana Alertmanager",
        "text": "[FIRING:1] HighMemoryUsage env:prod service:backend-api",
    }
    parsed = parse_inbound_alert(grafana_event)
    assert parsed is not None
    assert parsed.source == "grafana_alertmanager"
    assert parsed.environment == "prod"
    assert parsed.service == "backend-api"


def test_alert_detector_datadog_alert(monkeypatch):
    monkeypatch.setattr(settings, "enable_datadog", True)
    datadog_event = {
        "subtype": "bot_message",
        "bot_id": "B77777",
        "username": "Datadog",
        "text": "[Triggered] Latency > 500ms on production cluster",
    }
    parsed = parse_inbound_alert(datadog_event)
    assert parsed is not None
    assert parsed.source == "datadog"


def test_alert_detector_ignore_self_diagnostic():
    self_event = {
        "subtype": "bot_message",
        "bot_id": "B99999",
        "text": ":mag: *Serenity-Ops* is investigating this alert (AWS CLOUDWATCH)…",
    }
    assert is_inbound_alert(self_event) is False


def test_datadog_mcp_enrichment(monkeypatch):
    monkeypatch.setattr(settings, "enable_datadog", True)
    monkeypatch.setattr(settings, "datadog_api_key", "fake-api-key")
    monkeypatch.setattr(settings, "datadog_app_key", "fake-app-key")

    base_config = {"datadog": {"transport": "sse", "url": "https://mcp.datadoghq.com"}}
    enriched = enrich_mcp_config(base_config)
    assert enriched["datadog"]["headers"]["DATADOG_API_KEY"] == "fake-api-key"
    assert enriched["datadog"]["headers"]["DD_APPLICATION_KEY"] == "fake-app-key"


def test_json_formatter():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="serenity.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=10,
        msg="Test warning message",
        args=(),
        exc_info=None,
    )
    record.custom_field = "extra_value"

    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert parsed["level"] == "WARNING"
    assert parsed["logger"] == "serenity.test"
    assert parsed["message"] == "Test warning message"
    assert parsed["custom_field"] == "extra_value"
    assert "timestamp" in parsed


def test_alert_detector_matches_known_services():
    alert_event = {
        "subtype": "bot_message",
        "bot_id": "B12345",
        "text": "ALARM: High memory usage in container order-api task",
    }
    parsed = parse_inbound_alert(alert_event, known_services=["order-api", "payment-processor"])
    assert parsed is not None
    assert parsed.service == "order-api"


def test_context_hub_and_tools(monkeypatch):
    from app.integrations.context_hub import (
        get_known_service_names,
        load_context_tools,
        lookup_workload_architecture,
    )

    sample_context = {
        "organization_name": "Acme Corp",
        "business_domain": "e-commerce",
        "architecture_summary": "Preprod environment",
        "services": [
            {
                "name": "order-api",
                "description": "Public ordering API",
                "criticality": "HIGH",
                "tech_stack": "Node.js / Express",
                "repository": "acme/order-api",
                "log_group": "/aws/ecs/preprod-order-api",
            },
            {
                "name": "payment-processor",
                "description": "Worker consuming SQS payment jobs",
                "criticality": "CRITICAL",
                "tech_stack": "Python / FastAPI",
                "repository": "acme/payment-processor",
                "log_group": "/aws/ecs/preprod-payment-processor",
            },
        ],
        "runbooks": {
            "Aurora CPU": "https://wiki.acme.com/runbooks/aurora",
        },
    }
    monkeypatch.setattr(settings, "application_context_raw", json.dumps(sample_context))

    assert get_known_service_names() == ["order-api", "payment-processor"]

    tools = load_context_tools()
    assert len(tools) == 1
    assert tools[0].name == "lookup_workload_architecture"

    # Query overview
    overview = lookup_workload_architecture.invoke({"service_or_keyword": ""})
    assert "Acme Corp" in overview
    assert "order-api" in overview

    # Query specific service
    svc_info = lookup_workload_architecture.invoke({"service_or_keyword": "payment-processor"})
    assert "CRITICAL" in svc_info
    assert "acme/payment-processor" in svc_info
    assert "/aws/ecs/preprod-payment-processor" in svc_info

    # Query runbook
    rb_info = lookup_workload_architecture.invoke({"service_or_keyword": "aurora"})
    assert "https://wiki.acme.com/runbooks/aurora" in rb_info

