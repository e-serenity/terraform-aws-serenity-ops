from botocore.exceptions import ClientError

from app.config import settings
from app.core import hub
from app.core.prerequisites import prerequisites_check


def test_prerequisites_check_all_ok_and_publishes_hub(monkeypatch):
    monkeypatch.setattr(settings, "slack_bot_token", "xoxb-1234567890-valid")
    monkeypatch.setattr(settings, "slack_app_token", "xapp-1-valid-token")
    monkeypatch.setattr(settings, "llm_primary_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_primary_model", "eu.anthropic.claude-sonnet-4-6")
    monkeypatch.setattr(settings, "dynamodb_table_name", "serenity-ops-hub")
    monkeypatch.setattr(settings, "enable_gitlab", True)
    monkeypatch.setattr(settings, "gitlab_token", "glpat-validtoken12345")
    monkeypatch.setattr(settings, "enable_github", False)
    monkeypatch.setattr(settings, "enable_datadog", False)
    monkeypatch.setattr(settings, "enable_grafana", False)

    class FakeSTS:
        def get_caller_identity(self):
            return {"Account": "123456789012"}

    class FakeCW:
        def describe_alarms(self, MaxRecords=1):
            return {"MetricAlarms": []}

    class FakeDDB:
        def describe_table(self, TableName):
            return {"Table": {"TableName": TableName, "TableStatus": "ACTIVE"}}

    def fake_boto3_client(service, **kwargs):
        if service == "sts":
            return FakeSTS()
        if service == "cloudwatch":
            return FakeCW()
        if service == "dynamodb":
            return FakeDDB()
        raise ValueError(f"Unexpected service: {service}")

    class FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fake_post(url, **kwargs):
        return FakeResp(200, {"ok": True, "team": "e-serenity"})

    def fake_get(url, **kwargs):
        if "/api/v4/user" in url:
            return FakeResp(200, {"username": "serenity-bot"})
        return FakeResp(404, {})

    recorded_reports = []
    monkeypatch.setattr("app.core.prerequisites.boto3.client", fake_boto3_client)
    monkeypatch.setattr("app.core.prerequisites.requests.post", fake_post)
    monkeypatch.setattr("app.core.prerequisites.requests.get", fake_get)
    monkeypatch.setattr(hub, "record_prerequisites_status", lambda r: recorded_reports.append(r) or True)

    report = prerequisites_check(verify_live=True, publish_hub=True)
    assert report["overall_status"] == "OK"
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["slack"]["status"] == "OK"
    assert by_name["aws_observability"]["status"] == "OK"
    assert by_name["llm_routing"]["status"] == "OK"
    assert by_name["dynamodb_hub"]["status"] == "OK"
    assert by_name["gitlab"]["status"] == "OK"
    assert by_name["github"]["status"] == "SKIPPED"
    assert len(recorded_reports) == 1


def test_prerequisites_check_detects_iam_denied_and_degraded_integration(monkeypatch):
    monkeypatch.setattr(settings, "slack_bot_token", "xoxb-1234567890-valid")
    monkeypatch.setattr(settings, "slack_app_token", "xapp-1-valid-token")
    monkeypatch.setattr(settings, "llm_primary_provider", "bedrock")
    monkeypatch.setattr(settings, "dynamodb_table_name", "")
    monkeypatch.setattr(settings, "enable_gitlab", False)
    monkeypatch.setattr(settings, "enable_github", True)
    monkeypatch.setattr(settings, "github_token", "to-fill-manually")
    monkeypatch.setattr(settings, "enable_datadog", False)
    monkeypatch.setattr(settings, "enable_grafana", False)

    class FakeSTS:
        def get_caller_identity(self):
            return {"Account": "123456789012"}

    class FakeCW:
        def describe_alarms(self, MaxRecords=1):
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Not authorized for cloudwatch:DescribeAlarms"}},
                "DescribeAlarms",
            )

    monkeypatch.setattr(
        "app.core.prerequisites.boto3.client",
        lambda service, **kwargs: FakeSTS() if service == "sts" else FakeCW(),
    )

    class FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True, "team": "e-serenity"}

    monkeypatch.setattr("app.core.prerequisites.requests.post", lambda *a, **kw: FakeResp())

    report = prerequisites_check(verify_live=True, publish_hub=False)
    assert report["overall_status"] == "ERROR"
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["aws_observability"]["status"] == "ERROR"
    assert "AccessDenied" in by_name["aws_observability"]["detail"]
    assert by_name["github"]["status"] == "ERROR"
    assert by_name["dynamodb_hub"]["status"] == "SKIPPED"


def test_prerequisites_check_degraded_when_only_optional_integration_fails(monkeypatch):
    monkeypatch.setattr(settings, "slack_bot_token", "xoxb-1234567890-valid")
    monkeypatch.setattr(settings, "slack_app_token", "xapp-1-valid-token")
    monkeypatch.setattr(settings, "llm_primary_provider", "bedrock")
    monkeypatch.setattr(settings, "dynamodb_table_name", "")
    monkeypatch.setattr(settings, "enable_gitlab", False)
    monkeypatch.setattr(settings, "enable_github", False)
    monkeypatch.setattr(settings, "enable_datadog", True)
    monkeypatch.setattr(settings, "datadog_api_key", "to-fill-manually")
    monkeypatch.setattr(settings, "datadog_app_key", "to-fill-manually")
    monkeypatch.setattr(settings, "enable_grafana", False)

    report = prerequisites_check(verify_live=False, publish_hub=False)
    assert report["overall_status"] == "DEGRADED"
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["datadog"]["status"] == "ERROR"
    assert by_name["slack"]["status"] == "OK"


def test_hub_record_prerequisites_status(monkeypatch):
    stored = {}

    class FakeTable:
        def put_item(self, Item):
            stored["item"] = Item

    monkeypatch.setattr(hub, "_get_table", lambda: FakeTable())
    monkeypatch.setattr(hub, "TABLE_NAME", "serenity-ops-hub")

    ok = hub.record_prerequisites_status(
        {
            "overall_status": "OK",
            "checked_at": "2026-11-13T19:00:00+00:00",
            "checks": [{"name": "slack", "enabled": True, "status": "OK", "detail": "ok"}],
        }
    )
    assert ok is True
    assert stored["item"]["PK"] == "MOD#serenity-bot"
    assert stored["item"]["SK"] == "STATE#PREREQUISITES"
    assert stored["item"]["overall_status"] == "OK"
