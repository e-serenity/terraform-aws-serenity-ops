"""Representative incident scenarios (including honest failure modes) for Serenity-Ops LLM evals."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IncidentScenario:
    id: str
    title: str
    category: str
    alert_event: dict[str, Any]
    telemetry: dict[str, str]
    simulated_rca_json: dict[str, Any]
    expected_keywords: list[str]
    forbidden_claims: list[str] = field(default_factory=list)
    expected_confidence: str = "HIGH"
    requires_hitl: bool = False
    expected_outcome: str = "PASS"  # "PASS" or "KNOWN_FAILURE"
    failure_note: str = ""


INCIDENT_SCENARIOS: list[IncidentScenario] = [
    IncidentScenario(
        id="ecs_oom_deploy_regression",
        title="ECS Task OOMKilled (Exit 137) after deployment",
        category="ECS / Compute",
        alert_event={
            "subtype": "bot_message",
            "bot_id": "B_CW",
            "text": "ALARM: [ALARM] prod-order-api-task-stops in EU (Paris)",
            "attachments": [
                {
                    "text": (
                        "AlarmName: prod-order-api-task-stops\n"
                        "New State Value: ALARM\n"
                        "Namespace: AWS/ECS ServiceName=order-api ClusterName=prod-ecs"
                    )
                }
            ],
        },
        telemetry={
            "aws_ecs_describe_services": (
                "ECS Service order-api: running=1/desired=2, Deployment order-api:42 IN_PROGRESS. "
                "Event: task stopped with OutOfMemoryError (ExitCode 137)."
            ),
            "aws_cloudwatch_get_log_events": (
                "[1700000100] ERROR MemoryError: unable to allocate 512 MiB buffer in worker_cache\n"
                "Traceback (most recent call last):\n"
                "  File 'cache.py', line 88, in preload\n"
                "MemoryError: heap limit exceeded"
            ),
            "gitlab_list_commits": "Commit 9a4f21c by @alice: 'feat(cache): preload full catalog in memory'",
        },
        simulated_rca_json={
            "scope": "order-api (ECS)",
            "summary": "ECS tasks crashing with ExitCode 137 (OutOfMemoryError) after commit 9a4f21c",
            "severity": "CRITICAL",
            "diagnostic": (
                "ECS service order-api tasks are terminating with OutOfMemoryError (ExitCode 137) "
                "during deployment of task definition order-api:42. CloudWatch logs show MemoryError "
                "in cache.py introduced by GitLab commit 9a4f21c."
            ),
            "key_evidence": [
                "aws_ecs_describe_services: running=1/2, task stopped OutOfMemoryError (ExitCode 137)",
                "aws_cloudwatch_get_log_events: MemoryError in cache.py line 88",
                "gitlab_list_commits: 9a4f21c preloaded full catalog in memory",
            ],
            "root_cause_confidence": "HIGH",
            "next_steps": [
                "Revert commit 9a4f21c or roll back ECS service to task definition order-api:41",
                "Increase ECS task memory limit above 1024 MiB if full preload is required",
            ],
            "tools_invoked": [
                "aws_ecs_describe_services",
                "aws_cloudwatch_get_log_events",
                "gitlab_list_commits",
            ],
        },
        expected_keywords=["OutOfMemory", "137", "9a4f21c", "MemoryError"],
        expected_confidence="HIGH",
        expected_outcome="PASS",
    ),
    IncidentScenario(
        id="rds_connection_pool_exhaustion",
        title="API 5XX spike caused by RDS max_connections exhaustion",
        category="RDS / Database",
        alert_event={
            "subtype": "bot_message",
            "bot_id": "B_CW",
            "text": "ALARM: prod-api-5xx-errors-spike",
            "attachments": [{"text": "Metric AWS/ApiGateway 5XXError > 5%"}],
        },
        telemetry={
            "aws_cloudwatch_get_metric_data": "AWS/ApiGateway 5XXError peaked at 18.4% in last 15m",
            "aws_cloudwatch_get_log_events": "FATAL: remaining connection slots are reserved for non-replication superuser connections",
            "aws_rds_describe_db_instances": "prod-postgres [available] db.t4g.medium Multi-AZ=True",
        },
        simulated_rca_json={
            "scope": "prod-postgres / API Gateway",
            "summary": "API 5XX spike triggered by PostgreSQL connection slot exhaustion",
            "severity": "HIGH",
            "diagnostic": (
                "The 18.4% 5XXError spike on API Gateway is caused by PostgreSQL rejecting new "
                "connections on prod-postgres with 'remaining connection slots are reserved'."
            ),
            "key_evidence": [
                "aws_cloudwatch_get_metric_data: 5XXError reached 18.4%",
                "aws_cloudwatch_get_log_events: FATAL remaining connection slots are reserved",
                "aws_rds_describe_db_instances: prod-postgres db.t4g.medium",
            ],
            "root_cause_confidence": "HIGH",
            "next_steps": [
                "Enable RDS Proxy or lower per-task SQLAlchemy pool_size",
            ],
            "tools_invoked": [
                "aws_cloudwatch_get_metric_data",
                "aws_cloudwatch_get_log_events",
                "aws_rds_describe_db_instances",
            ],
        },
        expected_keywords=["connection slots", "prod-postgres", "18.4%"],
        expected_confidence="HIGH",
        expected_outcome="PASS",
    ),
    IncidentScenario(
        id="ses_hard_bounce_hitl",
        title="SES HardBounce spike staging Human-in-the-Loop suppression",
        category="SES / Deliverability (HITL)",
        alert_event={
            "subtype": "bot_message",
            "bot_id": "B_CW",
            "text": "ALARM: ses-bounce-rate-elevated (> 5%)",
            "attachments": [{"text": "Recipient bad@invalid-domain.example SMTP 550 5.1.1"}],
        },
        telemetry={
            "aws_cloudwatch_get_log_events": "HardBounce recipient=bad@invalid-domain.example smtp=550 5.1.1 User Unknown",
            "ses_suppress_destination": "PENDING_APPROVAL: action_id=act-123 queued for human approval",
        },
        simulated_rca_json={
            "scope": "serenity-ses",
            "summary": "Elevated SES bounce rate from repeated 550 5.1.1 hard bounces; quarantine pending approval",
            "severity": "HIGH",
            "diagnostic": (
                "Repeated deliveries to bad@invalid-domain.example returned SMTP 550 5.1.1 (User Unknown), "
                "pushing the SES bounce rate above threshold. Quarantining via serenity-agent-ses has been "
                "staged in PENDING_APPROVAL and requires human confirmation."
            ),
            "key_evidence": [
                "aws_cloudwatch_get_log_events: HardBounce bad@invalid-domain.example (550 5.1.1)",
                "ses_suppress_destination: staged PENDING_APPROVAL",
            ],
            "root_cause_confidence": "HIGH",
            "next_steps": [
                "Click Approve in Slack or Web Console to add bad@invalid-domain.example to SES Suppression List",
            ],
            "tools_invoked": ["aws_cloudwatch_get_log_events", "ses_suppress_destination"],
        },
        expected_keywords=["550 5.1.1", "pending", "approval"],
        forbidden_claims=["successfully added to suppression list", "executed automatically"],
        expected_confidence="HIGH",
        requires_hitl=True,
        expected_outcome="PASS",
    ),
    IncidentScenario(
        id="cloudtrail_iam_regression",
        title="Lambda AccessDenied traced to CloudTrail PutRolePolicy change",
        category="IAM / CloudTrail",
        alert_event={
            "subtype": "bot_message",
            "bot_id": "B_CW",
            "text": "ALARM: billing-lambda-errors > 10",
            "attachments": [{"text": "Function prod-billing-sync failing with AccessDeniedException"}],
        },
        telemetry={
            "aws_cloudtrail_lookup_events": "PutRolePolicy on billing-lambda-role by ci-deployer at 14:12Z",
            "aws_lambda_get_function": "prod-billing-sync python3.12 Memory=256MB LastModified=14:10Z",
            "aws_cloudwatch_get_log_events": "botocore.exceptions.ClientError: AccessDeniedException on dynamodb:PutItem",
        },
        simulated_rca_json={
            "scope": "prod-billing-sync (Lambda)",
            "summary": "Lambda AccessDeniedException triggered by PutRolePolicy change from ci-deployer",
            "severity": "HIGH",
            "diagnostic": (
                "Function prod-billing-sync began throwing AccessDeniedException on dynamodb:PutItem "
                "immediately after ci-deployer executed PutRolePolicy on billing-lambda-role at 14:12Z."
            ),
            "key_evidence": [
                "aws_cloudtrail_lookup_events: PutRolePolicy by ci-deployer at 14:12Z",
                "aws_cloudwatch_get_log_events: ClientError AccessDeniedException dynamodb:PutItem",
                "aws_lambda_get_function: prod-billing-sync python3.12",
            ],
            "root_cause_confidence": "HIGH",
            "next_steps": [
                "Inspect recent IAM policy diff deployed by ci-deployer and restore dynamodb:PutItem",
            ],
            "tools_invoked": [
                "aws_cloudtrail_lookup_events",
                "aws_cloudwatch_get_log_events",
                "aws_lambda_get_function",
            ],
        },
        expected_keywords=["PutRolePolicy", "ci-deployer", "AccessDeniedException"],
        expected_confidence="HIGH",
        expected_outcome="PASS",
    ),
    IncidentScenario(
        id="dynamodb_provisioned_throttling",
        title="DynamoDB WriteThrottleEvents on Provisioned Table",
        category="DynamoDB / Capacity",
        alert_event={
            "subtype": "bot_message",
            "bot_id": "B_CW",
            "text": "ALARM: orders-table-throttled-requests",
            "attachments": [{"text": "AWS/DynamoDB ThrottledRequests > 0 TableName=orders-table"}],
        },
        telemetry={
            "aws_dynamodb_describe_table": "orders-table ACTIVE BillingMode=PROVISIONED RCU=10 WCU=10",
            "aws_cloudwatch_get_metric_data": "AWS/DynamoDB ThrottledRequests Sum=412 in last 30m",
        },
        simulated_rca_json={
            "scope": "orders-table (DynamoDB)",
            "summary": "412 throttled requests due to low PROVISIONED capacity (RCU=10, WCU=10)",
            "severity": "HIGH",
            "diagnostic": (
                "Table orders-table is running in PROVISIONED billing mode with only 10 RCU and 10 WCU, "
                "causing 412 ThrottledRequests over the last 30 minutes during traffic burst."
            ),
            "key_evidence": [
                "aws_dynamodb_describe_table: PROVISIONED RCU=10, WCU=10",
                "aws_cloudwatch_get_metric_data: ThrottledRequests Sum=412",
            ],
            "root_cause_confidence": "HIGH",
            "next_steps": [
                "Switch orders-table to PAY_PER_REQUEST (On-Demand) or enable DynamoDB Auto Scaling",
            ],
            "tools_invoked": ["aws_dynamodb_describe_table", "aws_cloudwatch_get_metric_data"],
        },
        expected_keywords=["PROVISIONED", "WCU=10", "412"],
        expected_confidence="HIGH",
        expected_outcome="PASS",
    ),
    IncidentScenario(
        id="midstream_traceback_under_log_truncation",
        title="Redis ConnectionRefusedError preserved mid-stream inside >35KB logs",
        category="Log Truncation / Resilience",
        alert_event={
            "subtype": "bot_message",
            "bot_id": "B_CW",
            "text": "ALARM: checkout-api-latency-p99 > 2000ms",
            "attachments": [{"text": "LogGroup /aws/ecs/prod-checkout-api"}],
        },
        telemetry={
            "aws_cloudwatch_get_log_events": "Traceback ... ConnectionRefusedError: [Errno 111] redis:6379",
        },
        simulated_rca_json={
            "scope": "checkout-api (ECS / Redis)",
            "summary": "Latency spike caused by ConnectionRefusedError to Redis (redis:6379)",
            "severity": "HIGH",
            "diagnostic": (
                "Smart log truncation preserved the mid-stream traceback showing ConnectionRefusedError "
                "against redis:6379 amidst noisy INFO heartbeats, explaining the checkout latency spike."
            ),
            "key_evidence": [
                "aws_cloudwatch_get_log_events: ConnectionRefusedError [Errno 111] redis:6379",
            ],
            "root_cause_confidence": "HIGH",
            "next_steps": [
                "Check ElastiCache/Redis node health and ECS security group egress rules on port 6379",
            ],
            "tools_invoked": ["aws_cloudwatch_get_log_events"],
        },
        expected_keywords=["ConnectionRefusedError", "redis:6379"],
        expected_confidence="HIGH",
        expected_outcome="PASS",
    ),
    IncidentScenario(
        id="missing_log_group_low_confidence",
        title="[Honest Failure] Missing Log Group & Empty Metrics -> Unresolved RCA",
        category="Failure Case / Missing Telemetry",
        alert_event={
            "subtype": "bot_message",
            "bot_id": "B_CW",
            "text": "ALARM: unknown-worker-timeout",
            "attachments": [{"text": "Generic timeout alert without log_group or cluster metadata"}],
        },
        telemetry={
            "aws_cloudwatch_get_log_events": "[Tool Error] ResourceNotFoundException: The specified log group does not exist.",
            "aws_cloudwatch_get_metric_data": "No datapoints returned.",
        },
        simulated_rca_json={
            "scope": "unknown-worker",
            "summary": "Insufficient telemetry to determine root cause for worker timeout",
            "severity": "MEDIUM",
            "diagnostic": (
                "Unable to identify the root cause because the inferred CloudWatch log group returned "
                "ResourceNotFoundException and no metric datapoints were found. Operator input is needed "
                "to map the service in application_context."
            ),
            "key_evidence": [
                "aws_cloudwatch_get_log_events: ResourceNotFoundException (log group missing)",
                "aws_cloudwatch_get_metric_data: No datapoints returned",
            ],
            "root_cause_confidence": "LOW",
            "next_steps": [
                "Register unknown-worker and its log_group in Terraform application_context",
            ],
            "tools_invoked": ["aws_cloudwatch_get_log_events", "aws_cloudwatch_get_metric_data"],
        },
        expected_keywords=["ResourceNotFoundException", "insufficient"],
        expected_confidence="LOW",
        expected_outcome="KNOWN_FAILURE",
        failure_note="Unresolvable without application_context mapping; agent must abstain with LOW confidence instead of hallucinating.",
    ),
    IncidentScenario(
        id="misleading_commit_vs_external_tls_outage",
        title="[Honest Failure] Spurious correlation with benign README commit during external TLS expiry",
        category="Failure Case / False Attribution",
        alert_event={
            "subtype": "bot_message",
            "bot_id": "B_CW",
            "text": "ALARM: payment-webhook-502-spike",
            "attachments": [{"text": "502 Bad Gateway on payment-api"}],
        },
        telemetry={
            "aws_cloudwatch_get_log_events": "ERROR upstream returned 502 Bad Gateway",
            "github_list_commits": "Commit b77c102 2m ago by @bob: 'docs: update README badges'",
        },
        simulated_rca_json={
            "scope": "payment-api",
            "summary": "502 Bad Gateway spike potentially linked to recent commit b77c102",
            "severity": "HIGH",
            "diagnostic": (
                "payment-api began returning 502 Bad Gateway errors shortly after GitHub commit b77c102 "
                "was merged. Logs only report generic 502 responses without TLS handshake diagnostics."
            ),
            "key_evidence": [
                "aws_cloudwatch_get_log_events: ERROR upstream returned 502 Bad Gateway",
                "github_list_commits: b77c102 2m ago",
            ],
            "root_cause_confidence": "MEDIUM",
            "next_steps": [
                "Inspect commit b77c102 and upstream gateway connectivity",
            ],
            "tools_invoked": ["aws_cloudwatch_get_log_events", "github_list_commits"],
        },
        expected_keywords=["TLS certificate expired", "upstream certificate"],
        expected_confidence="HIGH",
        expected_outcome="KNOWN_FAILURE",
        failure_note="Without upstream TLS handshake logs, temporal proximity to a benign README commit causes false attribution.",
    ),
]
