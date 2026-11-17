import json
import os
import re
import time
import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("HUB_TABLE_NAME", "serenity-ops-hub")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "preprod")
REGION = os.environ.get("AWS_REGION", "eu-west-3")
ORIGIN_SECRET = os.environ.get("ORIGIN_SECRET", "")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))

dynamodb = boto3.resource("dynamodb", region_name=REGION)
cw_client = boto3.client("cloudwatch", region_name=REGION)

_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_ARN_ACCOUNT_RE = re.compile(r"(arn:aws[a-zA-Z-]*:[a-zA-Z0-9-]+:[a-zA-Z0-9-]*:)(\d{12})(:)")
_SECRET_PATTERNS = [
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1[REDACTED_TOKEN]"),
]


def _mask_account_id(account_id: str) -> str:
    clean = (account_id or "").strip()
    if len(clean) >= 8:
        return "*" * (len(clean) - 4) + clean[-4:]
    return "****" if clean else ""


def _mask_email(email: str) -> str:
    raw = (email or "").strip()
    if "@" not in raw:
        return raw
    local, domain = raw.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[:1]}***"
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


def _redact_sensitive_text(value: str) -> str:
    if not value or not isinstance(value, str):
        return value
    redacted = _EMAIL_RE.sub(lambda m: _mask_email(m.group(0)), value)
    redacted = _ARN_ACCOUNT_RE.sub(
        lambda m: f"{m.group(1)}{_mask_account_id(m.group(2))}{m.group(3)}",
        redacted,
    )
    if ACCOUNT_ID and len(ACCOUNT_ID) >= 8:
        redacted = redacted.replace(ACCOUNT_ID, _mask_account_id(ACCOUNT_ID))
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _redact_value(val):
    if isinstance(val, str):
        return _redact_sensitive_text(val)
    if isinstance(val, dict):
        return {k: _redact_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_redact_value(item) for item in val]
    return val


def _resp(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
        "body": json.dumps(body, default=str),
    }


def _query_pk(table, pk_val: str, limit: int = 50, scan_forward: bool = False):
    try:
        res = table.query(
            KeyConditionExpression=Key("PK").eq(pk_val),
            Limit=limit,
            ScanIndexForward=scan_forward,
        )
        return res.get("Items", [])
    except Exception:
        return []


def _get_live_state():
    table = dynamodb.Table(TABLE_NAME)

    mod_items = _query_pk(table, "SERENITY#MODULES", limit=50)
    installed_modules = ["serenity-core"]
    retention_days = RETENTION_DAYS

    for item in mod_items:
        sk = item.get("SK", "")
        status = item.get("status", "ACTIVE")
        mod_name = item.get("name") or sk.replace("MOD#", "")
        if status == "ACTIVE" and mod_name and mod_name not in installed_modules:
            installed_modules.append(mod_name)
        if item.get("retention_days"):
            try:
                retention_days = int(item["retention_days"])
            except Exception:
                pass

    ses_items = _query_pk(table, "MOD#serenity-ses", limit=50)
    ses_summary = {
        "dmarc": "valid",
        "spf": "valid",
        "dkim": "valid",
        "bounceRate": 0.0,
        "complaintRate": 0.0,
        "dedicatedIps": [],
    }
    email_events = []
    for item in ses_items:
        sk = item.get("SK", "")
        if sk == "STATE#SUMMARY":
            raw_ips = item.get("dedicatedIps") or item.get("dedicated_ips") or []
            if isinstance(raw_ips, str):
                try:
                    raw_ips = json.loads(raw_ips)
                except Exception:
                    raw_ips = []
            normalized_ips = []
            for idx, ip_entry in enumerate(raw_ips):
                if isinstance(ip_entry, dict):
                    normalized_ips.append({
                        "ip": ip_entry.get("ip") or ip_entry.get("pool") or f"Pool-{idx + 1}",
                        "warmup": int(ip_entry.get("warmup", 100)),
                        "status": ip_entry.get("status") or ip_entry.get("mode", "MANAGED"),
                    })
            ses_summary = {
                "dmarc": item.get("dmarc", "valid"),
                "spf": item.get("spf", "valid"),
                "dkim": item.get("dkim", "valid"),
                "bounceRate": float(item.get("bounceRate", item.get("bounce_rate", 0.0))),
                "complaintRate": float(item.get("complaintRate", item.get("complaint_rate", 0.0))),
                "dedicatedIps": normalized_ips,
            }
        elif sk.startswith("EVENT#"):
            diag = item.get("diagnosticCode") or item.get("smtp_code") or "SMTP Notification"
            evt_type = item.get("type", "HardBounce")
            if evt_type == "Bounce":
                evt_type = "HardBounce"
            raw_reason = item.get("reason") or f"Domain: {item.get('domain', 'unknown')} ({item.get('subType', 'General')})"
            email_events.append({
                "id": item.get("id", sk),
                "timestamp": item.get("timestamp", sk.replace("EVENT#", "")[:19]),
                "type": evt_type,
                "recipient": _mask_email(str(item.get("recipient", "unknown"))),
                "smtpCode": _redact_sensitive_text(str(diag)),
                "reason": _redact_sensitive_text(str(raw_reason)),
                "suggestedAction": _redact_sensitive_text(str(item.get("aiRecommendation") or "Add to SES Account Suppression List")),
                "actionStatus": item.get("actionStatus", "PENDING"),
            })

    cw_alarms = []
    try:
        paginator = (
            cw_client.DescribeAlarms(MaxRecords=50)
            if hasattr(cw_client, "DescribeAlarms")
            else cw_client.describe_alarms(MaxRecords=50)
        )
        for alarm in paginator.get("MetricAlarms", []):
            state_val = alarm.get("StateValue", "OK")
            mapped_state = (
                "ALARM"
                if state_val == "ALARM"
                else ("INSUFFICIENT_DATA" if state_val == "INSUFFICIENT_DATA" else "OK")
            )
            cw_alarms.append({
                "name": alarm.get("AlarmName", "alarm"),
                "namespace": alarm.get("Namespace", "AWS/Custom"),
                "metric": alarm.get("MetricName", "Metric"),
                "threshold": f"{alarm.get('ComparisonOperator', '>=')} {alarm.get('Threshold', '')}",
                "state": mapped_state,
                "updatedAt": str(alarm.get("StateUpdatedTimestamp", ""))[:19],
            })
    except Exception:
        pass

    ops_items = _query_pk(table, "SERENITY#OPS", limit=50)
    legacy_inc_items = _query_pk(table, "SERENITY#INCIDENTS", limit=50)
    inc_items = [
        it for it in ops_items if it.get("SK", "").startswith("INCIDENT#")
    ] + legacy_inc_items
    incidents = []
    for item in inc_items:
        raw_traces = item.get("mcpTraces") or item.get("mcp_traces") or []
        incidents.append({
            "id": item.get("id") or item.get("incident_id") or item.get("SK", ""),
            "timestamp": item.get("timestamp") or item.get("created_at", ""),
            "kind": item.get("kind", "ALERT"),
            "source": item.get("source", "Slack (@Serenity-Ops)"),
            "requester": _redact_sensitive_text(str(item.get("requester", ""))),
            "trigger": _redact_sensitive_text(str(item.get("trigger", ""))),
            "severity": item.get("severity", "INFO"),
            "mcpTraces": [_redact_sensitive_text(str(t)) for t in raw_traces],
            "rca": _redact_sensitive_text(str(item.get("rca", ""))),
            "proposedAction": _redact_value(item.get("proposedAction") or item.get("proposed_action")),
        })

    chat_items = _query_pk(table, "SERENITY#CHAT", limit=50, scan_forward=True)
    chat_messages = []
    for item in chat_items:
        chat_messages.append({
            "id": item.get("id", item.get("SK", "")),
            "sender": item.get("sender", "bot"),
            "author": item.get("author", "Serenity-Ops"),
            "channel": item.get("channel", "Web Console"),
            "timestamp": item.get("timestamp", ""),
            "text": _redact_sensitive_text(str(item.get("text", ""))),
            "toolsUsed": item.get("toolsUsed", []),
        })

    return {
        "mode": "live",
        "accountId": _mask_account_id(ACCOUNT_ID),
        "environment": ENVIRONMENT,
        "region": REGION,
        "hubTableName": TABLE_NAME,
        "retentionDays": retention_days,
        "installedModules": installed_modules,
        "sesSummary": ses_summary,
        "emailEvents": email_events,
        "cloudWatchAlarms": cw_alarms,
        "incidents": incidents,
        "chatMessages": chat_messages,
    }


def handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if ORIGIN_SECRET and headers.get("x-serenity-origin-secret") != ORIGIN_SECRET:
        return _resp(403, {"error": "Direct access forbidden"})

    raw_path = event.get("rawPath", "/api/state")
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

    if raw_path == "/api/state" and method == "GET":
        return _resp(200, _get_live_state())

    if raw_path == "/api/chat" and method == "POST":
        table = dynamodb.Table(TABLE_NAME)
        body = json.loads(event.get("body") or "{}")
        text = (body.get("text") or "").strip()
        if not text:
            return _resp(400, {"error": "Empty message"})
        now_ts = int(time.time() * 1000)
        ttl_val = int(time.time()) + (RETENTION_DAYS * 86400)
        time_str = time.strftime("%H:%M", time.gmtime())

        user_msg = {
            "PK": "SERENITY#CHAT",
            "SK": f"MSG#{now_ts}#1",
            "id": f"msg-u-{now_ts}",
            "sender": "user",
            "author": "Operator (Web Console)",
            "channel": "Web Console",
            "timestamp": time_str,
            "text": text,
            "ttl": ttl_val,
        }
        table.put_item(Item=user_msg)
        return _resp(200, {"ok": True, "message": user_msg})

    return _resp(404, {"error": f"Unknown route {method} {raw_path}"})
