import functools
import json
import time
from typing import Any
import boto3
from langchain_core.tools import tool

from app.config import settings
from app.core.utils.logging import get_logger

logger = get_logger("integrations.aws")
MAX_PAYLOAD_SIZE = 35_000


def _safe_wrapper(fn):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logger.warning("AWS action '%s' failed: %s", fn.__name__, exc)
            return f"[Tool Error] {fn.__name__}: {exc}"
    return inner


@tool
@_safe_wrapper
def aws_cloudwatch_describe_alarms(state_value: str = "ALARM", alarm_name_prefix: str = "") -> str:
    """Lists CloudWatch alarms, optionally filtered by state (e.g., 'ALARM', 'OK', 'INSUFFICIENT_DATA') or prefix.
    
    Use this to see which alarms are currently firing across the AWS infrastructure.
    """
    client = boto3.client("cloudwatch", region_name=settings.aws_region)
    params: dict[str, Any] = {"MaxRecords": 25}
    if state_value in ("ALARM", "OK", "INSUFFICIENT_DATA"):
        params["StateValue"] = state_value
    if alarm_name_prefix:
        params["AlarmNamePrefix"] = alarm_name_prefix

    resp = client.describe_alarms(**params)
    metric_alarms = resp.get("MetricAlarms", [])
    if not metric_alarms:
        return f"No CloudWatch alarms found with state='{state_value}'."

    summaries = []
    for a in metric_alarms:
        name = a.get("AlarmName", "unknown")
        state = a.get("StateValue", "unknown")
        reason = a.get("StateReason", "")[:200]
        metric = f"{a.get('Namespace', '')}/{a.get('MetricName', '')}"
        summaries.append(f"• **`{name}`** [{state}] — Metric: `{metric}`\n  Reason: {reason}")

    return "\n".join(summaries)[:MAX_PAYLOAD_SIZE]


@tool
@_safe_wrapper
def aws_cloudwatch_get_metric_data(
    metric_name: str,
    namespace: str,
    dimensions: str = "{}",
    minutes_ago: int = 60,
    stat: str = "Average",
) -> str:
    """Fetches historical metric datapoints from CloudWatch (e.g. CPU, Error rates, DynamoDB throttling).
    
    Arguments:
    - metric_name: e.g. '5XXError', 'CPUUtilization', 'ConsumedReadCapacityUnits', 'ThrottledRequests'
    - namespace: e.g. 'AWS/ApiGateway', 'AWS/ECS', 'AWS/DynamoDB', 'AWS/Lambda'
    - dimensions: JSON string representing dimension key-values, e.g. '{"TableName": "challenge-monster-game-state"}'
    - minutes_ago: lookback period in minutes (default 60)
    - stat: 'Average', 'Sum', 'Maximum', 'Minimum', or 'SampleCount'
    """
    client = boto3.client("cloudwatch", region_name=settings.aws_region)
    end_time = int(time.time())
    start_time = end_time - (max(5, minutes_ago) * 60)

    dim_list = []
    if dimensions:
        try:
            parsed = json.loads(dimensions) if isinstance(dimensions, str) else dimensions
            dim_list = [{"Name": k, "Value": str(v)} for k, v in parsed.items()]
        except Exception:
            dim_list = []

    period = max(60, (minutes_ago * 60) // 10)
    resp = client.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "m1",
                "MetricStat": {
                    "Metric": {
                        "Namespace": namespace,
                        "MetricName": metric_name,
                        "Dimensions": dim_list,
                    },
                    "Period": period,
                    "Stat": stat,
                },
                "ReturnData": True,
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
    )

    results = resp.get("MetricDataResults", [])
    if not results or not results[0].get("Values"):
        return f"No datapoints returned for `{namespace}/{metric_name}` in the last {minutes_ago} minutes."

    values = results[0].get("Values", [])
    timestamps = [str(ts)[:19] for ts in results[0].get("Timestamps", [])]
    pairs = [f"{ts}: {val:.2f}" for ts, val in zip(timestamps, values)]
    return f"Metric `{namespace}/{metric_name}` ({stat}) last {minutes_ago}m:\n" + "\n".join(pairs[:15])


@tool
@_safe_wrapper
def aws_cloudwatch_get_log_events(log_group_name: str, filter_pattern: str = "", limit: int = 20) -> str:
    """Queries CloudWatch Logs for recent log events or error traces matching a filter pattern.
    
    Arguments:
    - log_group_name: Name of the CloudWatch log group (e.g. '/aws/lambda/my-func' or '/aws/ecs/my-svc')
    - filter_pattern: CloudWatch filter pattern, e.g. 'ERROR', 'Exception', '500'
    - limit: maximum number of events to return (max 50)
    """
    client = boto3.client("logs", region_name=settings.aws_region)
    clean_limit = min(50, max(5, limit))

    params: dict[str, Any] = {
        "logGroupName": log_group_name,
        "limit": clean_limit,
        "interleaved": True,
    }
    if filter_pattern:
        params["filterPattern"] = filter_pattern

    resp = client.filter_log_events(**params)
    events = resp.get("events", [])
    if not events:
        return f"No log events found in `{log_group_name}` matching pattern '{filter_pattern}'."

    lines = []
    for ev in events:
        msg = (ev.get("message") or "").strip()
        lines.append(f"[{ev.get('timestamp')}] {msg}")

    return f"Logs from `{log_group_name}`:\n" + "\n".join(lines)[:MAX_PAYLOAD_SIZE]


@tool
@_safe_wrapper
def aws_dynamodb_describe_table(table_name: str) -> str:
    """Retrieves Amazon DynamoDB table configuration, billing mode, capacity units (RCU/WCU), and status.
    
    Use this tool when investigating database latency, throttling, or capacity issues.
    """
    client = boto3.client("dynamodb", region_name=settings.aws_region)
    resp = client.describe_table(TableName=table_name)
    tbl = resp.get("Table", {})
    if not tbl:
        return f"Table `{table_name}` not found."

    status = tbl.get("TableStatus", "UNKNOWN")
    billing = tbl.get("BillingModeSummary", {}).get("BillingMode") or "PROVISIONED"
    item_count = tbl.get("ItemCount", 0)
    size_bytes = tbl.get("TableSizeBytes", 0)
    size_mb = size_bytes / (1024 * 1024)

    provisioned = tbl.get("ProvisionedThroughput", {})
    rcu = provisioned.get("ReadCapacityUnits", 0)
    wcu = provisioned.get("WriteCapacityUnits", 0)

    gsi_lines = []
    for gsi in tbl.get("GlobalSecondaryIndexes", []):
        g_name = gsi.get("IndexName")
        g_status = gsi.get("IndexStatus")
        g_tp = gsi.get("ProvisionedThroughput", {})
        gsi_lines.append(f"  • GSI `{g_name}` [{g_status}] — RCU: {g_tp.get('ReadCapacityUnits', 0)}, WCU: {g_tp.get('WriteCapacityUnits', 0)}")

    result = [
        f"**DynamoDB Table: `{table_name}`**",
        f"• Status: `{status}`",
        f"• Billing Mode: `{billing}`",
        f"• Provisioned Throughput: RCU={rcu}, WCU={wcu}",
        f"• Items: {item_count} (~{size_mb:.2f} MB)",
    ]
    if gsi_lines:
        result.append("• Global Secondary Indexes:\n" + "\n".join(gsi_lines))

    return "\n".join(result)


@tool
@_safe_wrapper
def aws_lambda_get_function(function_name: str) -> str:
    """Inspects AWS Lambda function configuration (runtime, memory, timeout, environment variable keys).
    
    Use this tool when investigating serverless backend errors or latency timeouts.
    """
    client = boto3.client("lambda", region_name=settings.aws_region)
    resp = client.get_function(FunctionName=function_name)
    cfg = resp.get("Configuration", {})
    if not cfg:
        return f"Lambda function `{function_name}` not found."

    name = cfg.get("FunctionName")
    runtime = cfg.get("Runtime", "unknown")
    memory = cfg.get("MemorySize", 0)
    timeout = cfg.get("Timeout", 0)
    last_modified = cfg.get("LastModified", "")
    env_keys = list((cfg.get("Environment", {}).get("Variables") or {}).keys())

    return (
        f"**AWS Lambda: `{name}`**\n"
        f"• Runtime: `{runtime}`\n"
        f"• Memory: {memory} MB | Timeout: {timeout}s\n"
        f"• Last Modified: {last_modified}\n"
        f"• Environment Variable Keys: {', '.join(env_keys) if env_keys else 'None'}"
    )


@tool
@_safe_wrapper
def aws_ecs_describe_services(cluster_name: str, service_names: str = "") -> str:
    """Inspects AWS ECS services in a cluster: running vs desired task counts, deployments, and recent service events.

    Arguments:
    - cluster_name: Name or ARN of the ECS cluster.
    - service_names: Optional comma-separated list of ECS service names. Leave empty to auto-discover up to 10 services in the cluster.
    """
    client = boto3.client("ecs", region_name=settings.aws_region)
    if service_names.strip():
        svc_list = [s.strip() for s in service_names.split(",") if s.strip()][:10]
    else:
        listed = client.list_services(cluster=cluster_name, maxResults=10)
        svc_list = listed.get("serviceArns", [])

    if not svc_list:
        return f"No ECS services found in cluster `{cluster_name}`."

    resp = client.describe_services(cluster=cluster_name, services=svc_list)
    services = resp.get("services", [])
    if not services:
        return f"Could not describe ECS services `{svc_list}` in cluster `{cluster_name}`."

    blocks: list[str] = []
    for svc in services:
        name = svc.get("serviceName", "unknown")
        status = svc.get("status", "UNKNOWN")
        desired = svc.get("desiredCount", 0)
        running = svc.get("runningCount", 0)
        pending = svc.get("pendingCount", 0)
        task_def = (svc.get("taskDefinition") or "").split("/")[-1]

        dep_lines = []
        for dep in svc.get("deployments", [])[:3]:
            d_status = dep.get("status", "")
            rollout = dep.get("rolloutState", "N/A")
            d_tdef = (dep.get("taskDefinition") or "").split("/")[-1]
            dep_lines.append(f"  • Deployment [{d_status}] `{d_tdef}` — Rollout: `{rollout}` (Running: {dep.get('runningCount', 0)}/{dep.get('desiredCount', 0)})")

        ev_lines = []
        for ev in svc.get("events", [])[:5]:
            ts = str(ev.get("createdAt", ""))[:19]
            msg = (ev.get("message") or "").strip()
            ev_lines.append(f"  • [{ts}] {msg}")

        section = [
            f"**ECS Service: `{name}`** (Cluster: `{cluster_name}`)",
            f"• Status: `{status}` | Tasks: `{running}` running / `{desired}` desired (`{pending}` pending) | TaskDef: `{task_def}`",
        ]
        if dep_lines:
            section.append("• Deployments:\n" + "\n".join(dep_lines))
        if ev_lines:
            section.append("• Recent Events:\n" + "\n".join(ev_lines))
        blocks.append("\n".join(section))

    return "\n\n".join(blocks)[:MAX_PAYLOAD_SIZE]


@tool
@_safe_wrapper
def aws_rds_describe_db_instances(db_instance_identifier: str = "", minutes_ago: int = 120) -> str:
    """Inspects Amazon RDS database instances (status, engine, class, Multi-AZ, storage) and recent operational events.

    Arguments:
    - db_instance_identifier: Optional RDS DB instance identifier. Leave empty to list up to 10 instances in the region.
    - minutes_ago: Lookback window in minutes for recent RDS events (failovers, reboots, maintenance). Default 120.
    """
    client = boto3.client("rds", region_name=settings.aws_region)
    params: dict[str, Any] = {}
    if db_instance_identifier.strip():
        params["DBInstanceIdentifier"] = db_instance_identifier.strip()
    else:
        params["MaxRecords"] = 20

    resp = client.describe_db_instances(**params)
    instances = resp.get("DBInstances", [])[:10]
    if not instances:
        return "No RDS DB instances found."

    lines: list[str] = []
    for db in instances:
        ident = db.get("DBInstanceIdentifier", "unknown")
        status = db.get("DBInstanceStatus", "unknown")
        engine = f"{db.get('Engine', '')} {db.get('EngineVersion', '')}".strip()
        db_class = db.get("DBInstanceClass", "unknown")
        multi_az = db.get("MultiAZ", False)
        storage = db.get("AllocatedStorage", 0)
        endpoint = (db.get("Endpoint") or {}).get("Address", "N/A")
        lines.append(
            f"**RDS Instance: `{ident}`** [{status}]\n"
            f"• Engine: `{engine}` | Class: `{db_class}` | Storage: {storage} GB | Multi-AZ: `{multi_az}`\n"
            f"• Endpoint: `{endpoint}`"
        )

    event_params: dict[str, Any] = {
        "Duration": max(5, min(10080, minutes_ago)),
        "SourceType": "db-instance",
    }
    if db_instance_identifier.strip():
        event_params["SourceIdentifier"] = db_instance_identifier.strip()

    ev_resp = client.describe_events(**event_params)
    events = ev_resp.get("Events", [])[:10]
    if events:
        ev_lines = [f"• [{str(e.get('Date', ''))[:19]}] `{e.get('SourceIdentifier', '')}`: {e.get('Message', '')}" for e in events]
        lines.append("**Recent RDS Events:**\n" + "\n".join(ev_lines))

    return "\n\n".join(lines)[:MAX_PAYLOAD_SIZE]


@tool
@_safe_wrapper
def aws_cloudtrail_lookup_events(
    lookup_attribute_key: str = "",
    lookup_attribute_value: str = "",
    max_results: int = 15,
) -> str:
    """Queries AWS CloudTrail management events to audit recent infrastructure changes, IAM actions, or API errors.

    Arguments:
    - lookup_attribute_key: Optional filter key: 'EventName', 'ResourceName', 'ResourceType', 'Username', or 'EventSource'.
    - lookup_attribute_value: Value matching lookup_attribute_key (e.g. 'UpdateService', 'PutMetricAlarm', 'ecs.amazonaws.com').
    - max_results: Maximum number of events to return (default 15, max 30).
    """
    client = boto3.client("cloudtrail", region_name=settings.aws_region)
    clean_max = min(30, max(1, max_results))
    params: dict[str, Any] = {"MaxResults": clean_max}

    valid_keys = {"EventId", "EventName", "ReadOnly", "Username", "ResourceType", "ResourceName", "EventSource", "AccessKeyId"}
    if lookup_attribute_key in valid_keys and lookup_attribute_value.strip():
        params["LookupAttributes"] = [
            {"AttributeKey": lookup_attribute_key, "AttributeValue": lookup_attribute_value.strip()}
        ]

    resp = client.lookup_events(**params)
    events = resp.get("Events", [])
    if not events:
        return "No matching CloudTrail events found."

    lines: list[str] = []
    for ev in events:
        ts = str(ev.get("EventTime", ""))[:19]
        name = ev.get("EventName", "unknown")
        source = ev.get("EventSource", "")
        user = ev.get("Username", "unknown")
        resources = [f"{r.get('ResourceType', '')}:{r.get('ResourceName', '')}" for r in ev.get("Resources", [])[:3]]
        res_str = f" | Resources: `{', '.join(resources)}`" if resources else ""

        error_str = ""
        raw_cloudtrail = ev.get("CloudTrailEvent")
        if raw_cloudtrail:
            try:
                parsed_ev = json.loads(raw_cloudtrail)
                if err_code := parsed_ev.get("errorCode"):
                    error_str = f" ⚠️ Error: `{err_code}`"
            except Exception:
                pass

        lines.append(f"• [{ts}] **`{name}`** (`{source}`) by `{user}`{res_str}{error_str}")

    return "Recent CloudTrail Events:\n" + "\n".join(lines)[:MAX_PAYLOAD_SIZE]


def load_aws_tools() -> list[Any]:
    """Returns the suite of read-only AWS inspection tools."""
    return [
        aws_cloudwatch_describe_alarms,
        aws_cloudwatch_get_metric_data,
        aws_cloudwatch_get_log_events,
        aws_ecs_describe_services,
        aws_rds_describe_db_instances,
        aws_cloudtrail_lookup_events,
        aws_dynamodb_describe_table,
        aws_lambda_get_function,
    ]
