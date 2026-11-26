import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request
import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("HUB_TABLE_NAME", "serenity-ops-hub")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "preprod")
REGION = os.environ.get("AWS_REGION", "eu-west-3")
ORIGIN_SECRET = os.environ.get("ORIGIN_SECRET", "")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))
AUTH_MODE = os.environ.get("AUTH_MODE", "none").strip().lower()
AUTH_CONFIG_BUCKET = os.environ.get("AUTH_CONFIG_BUCKET", "").strip()
AUTH_CONFIG_KEY = os.environ.get("AUTH_CONFIG_KEY", "_internal/auth-config.json").strip()

dynamodb = boto3.resource("dynamodb", region_name=REGION)
cw_client = boto3.client("cloudwatch", region_name=REGION)
sts_client = boto3.client("sts", region_name=REGION)
s3_client = boto3.client("s3", region_name=REGION)

_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+*-])([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_ARN_ACCOUNT_RE = re.compile(r"(arn:aws[a-zA-Z-]*:[a-zA-Z0-9-]+:[a-zA-Z0-9-]*:)(\d{12})(:)")
_SECRET_PATTERNS = [
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1[REDACTED_TOKEN]"),
]

# RFC 8017 Section 9.2 DER DigestInfo prefixes for RSASSA-PKCS1-v1_5
_RSA_ALG_SPECS = {
    "RS256": (hashlib.sha256, bytes.fromhex("3031300d060960864801650304020105000420")),
    "RS384": (hashlib.sha384, bytes.fromhex("3041300d060960864801650304020205000430")),
    "RS512": (hashlib.sha512, bytes.fromhex("3051300d060960864801650304020305000440")),
}

_AUTH_CONFIG_CACHE: dict = {"value": None, "expires_at": 0.0}
_OIDC_DISCOVERY_CACHE: dict = {}
_JWKS_CACHE: dict = {}

_AUTH_CONFIG_TTL_SECONDS = 60
_OIDC_CACHE_TTL_SECONDS = 3600
_JWKS_MIN_REFRESH_INTERVAL = 60
_JWT_CLOCK_SKEW_SECONDS = 30
_MAX_CHAT_LENGTH = 4000


class AuthError(Exception):
    """Raised when JWT authentication or authorization fails."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _b64url_decode(segment: str) -> bytes:
    if not isinstance(segment, str):
        raise AuthError("Invalid base64url segment")
    padded = segment + "=" * ((4 - len(segment) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise AuthError("Malformed base64url encoding") from exc


def _http_get_json(url: str, timeout: int = 5) -> dict:
    if not url.startswith("https://"):
        raise AuthError("OIDC endpoints must use HTTPS")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "serenity-ops-api/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise AuthError(f"Failed to contact OIDC provider: {exc.reason}", status_code=503) from exc
    except Exception as exc:
        raise AuthError("Invalid JSON received from OIDC provider", status_code=503) from exc


def _get_oidc_discovery(issuer: str) -> dict:
    normalized = issuer.rstrip("/")
    now = time.time()
    cached = _OIDC_DISCOVERY_CACHE.get(normalized)
    if cached and cached["expires_at"] > now:
        return cached["value"]

    doc = _http_get_json(f"{normalized}/.well-known/openid-configuration")
    _OIDC_DISCOVERY_CACHE[normalized] = {"value": doc, "expires_at": now + _OIDC_CACHE_TTL_SECONDS}
    return doc


def _get_jwks(issuer: str, force_refresh: bool = False) -> list:
    normalized = issuer.rstrip("/")
    now = time.time()
    cached = _JWKS_CACHE.get(normalized)
    if cached and not force_refresh and cached["expires_at"] > now:
        return cached["keys"]
    if cached and force_refresh and (now - cached["fetched_at"]) < _JWKS_MIN_REFRESH_INTERVAL:
        return cached["keys"]

    jwks_uri = ""
    try:
        discovery = _get_oidc_discovery(normalized)
        jwks_uri = discovery.get("jwks_uri", "")
    except AuthError:
        jwks_uri = f"{normalized}/.well-known/jwks.json"

    if not jwks_uri:
        jwks_uri = f"{normalized}/.well-known/jwks.json"

    jwks_doc = _http_get_json(jwks_uri)
    keys = jwks_doc.get("keys")
    if not isinstance(keys, list):
        raise AuthError("OIDC JWKS document missing 'keys' list", status_code=503)

    _JWKS_CACHE[normalized] = {
        "keys": keys,
        "fetched_at": now,
        "expires_at": now + _OIDC_CACHE_TTL_SECONDS,
    }
    return keys


def _load_auth_config() -> dict:
    """Loads OIDC/Cognito authentication configuration from S3 (cached in memory)."""
    if AUTH_MODE == "none":
        return {"enabled": False, "mode": "none"}

    now = time.time()
    if _AUTH_CONFIG_CACHE["value"] is not None and _AUTH_CONFIG_CACHE["expires_at"] > now:
        return _AUTH_CONFIG_CACHE["value"]

    config = None
    if AUTH_CONFIG_BUCKET and AUTH_CONFIG_KEY:
        try:
            obj = s3_client.get_object(Bucket=AUTH_CONFIG_BUCKET, Key=AUTH_CONFIG_KEY)
            config = json.loads(obj["Body"].read().decode("utf-8"))
        except Exception as exc:
            raise AuthError(f"Authentication configuration unavailable: {exc}", status_code=503) from exc

    if config is None:
        return {"enabled": False, "mode": "none"}

    # Auto-discover OIDC endpoints when BYO OIDC omits explicit overrides
    if config.get("enabled") and config.get("issuer"):
        if not config.get("authorizationEndpoint") or not config.get("tokenEndpoint"):
            try:
                discovery = _get_oidc_discovery(config["issuer"])
                config = dict(config)
                config.setdefault("authorizationEndpoint", "")
                config.setdefault("tokenEndpoint", "")
                config.setdefault("logoutEndpoint", "")
                if not config["authorizationEndpoint"]:
                    config["authorizationEndpoint"] = discovery.get("authorization_endpoint", "")
                if not config["tokenEndpoint"]:
                    config["tokenEndpoint"] = discovery.get("token_endpoint", "")
                if not config["logoutEndpoint"]:
                    config["logoutEndpoint"] = discovery.get("end_session_endpoint", "")
            except AuthError:
                pass

    _AUTH_CONFIG_CACHE["value"] = config
    _AUTH_CONFIG_CACHE["expires_at"] = now + _AUTH_CONFIG_TTL_SECONDS
    return config


def _verify_rsa_pkcs1v15(alg: str, signing_input: bytes, signature: bytes, jwk: dict) -> bool:
    spec = _RSA_ALG_SPECS.get(alg)
    if not spec:
        return False
    hash_fn, der_prefix = spec

    if jwk.get("kty") != "RSA":
        return False
    if jwk.get("use") and jwk.get("use") != "sig":
        return False

    try:
        n_bytes = _b64url_decode(jwk["n"])
        e_bytes = _b64url_decode(jwk["e"])
    except (KeyError, AuthError):
        return False

    n = int.from_bytes(n_bytes, "big")
    e = int.from_bytes(e_bytes, "big")
    if n <= 0 or e <= 0:
        return False

    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False

    s = int.from_bytes(signature, "big")
    if s >= n:
        return False

    m = pow(s, e, n)
    em = m.to_bytes(k, "big")

    digest = hash_fn(signing_input).digest()
    t = der_prefix + digest
    ps_len = k - len(t) - 3
    if ps_len < 8:
        return False

    expected_em = b"\x00\x01" + (b"\xff" * ps_len) + b"\x00" + t
    return hmac.compare_digest(em, expected_em)


def _verify_jwt(token: str, auth_config: dict) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Malformed JWT token")

    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        claims = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError("Invalid JWT JSON payload") from exc

    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise AuthError("Invalid JWT structure")

    alg = header.get("alg", "")
    if alg not in _RSA_ALG_SPECS:
        raise AuthError(f"Unsupported JWT algorithm '{alg}'")

    kid = header.get("kid")
    if not kid:
        raise AuthError("Missing JWT 'kid' header")

    expected_issuer = (auth_config.get("issuer") or "").rstrip("/")
    expected_client_id = (auth_config.get("clientId") or "").strip()
    if not expected_issuer or not expected_client_id:
        raise AuthError("OIDC issuer or clientId is not configured", status_code=503)

    keys = _get_jwks(expected_issuer, force_refresh=False)
    jwk = next((k for k in keys if k.get("kid") == kid), None)
    if jwk is None:
        keys = _get_jwks(expected_issuer, force_refresh=True)
        jwk = next((k for k in keys if k.get("kid") == kid), None)
    if jwk is None:
        raise AuthError("No matching signing key found in JWKS")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = _b64url_decode(sig_b64)
    if not _verify_rsa_pkcs1v15(alg, signing_input, signature, jwk):
        raise AuthError("Invalid JWT signature")

    # Validate standard OIDC & Cognito claims
    token_iss = str(claims.get("iss", "")).rstrip("/")
    if token_iss != expected_issuer:
        raise AuthError("JWT issuer mismatch")

    now = time.time()
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)):
        raise AuthError("Missing JWT 'exp' claim")
    if now > float(exp) + _JWT_CLOCK_SKEW_SECONDS:
        raise AuthError("JWT token has expired")

    nbf = claims.get("nbf")
    if nbf is not None:
        if not isinstance(nbf, (int, float)) or now + _JWT_CLOCK_SKEW_SECONDS < float(nbf):
            raise AuthError("JWT token is not yet valid")

    token_use = claims.get("token_use")
    if token_use == "access":
        if claims.get("client_id") != expected_client_id:
            raise AuthError("JWT client_id mismatch")
    else:
        aud = claims.get("aud")
        aud_valid = (aud == expected_client_id) or (isinstance(aud, list) and expected_client_id in aud)
        if not aud_valid:
            raise AuthError("JWT audience mismatch")
        azp = claims.get("azp")
        if azp is not None and azp != expected_client_id:
            raise AuthError("JWT authorized party (azp) mismatch")

    return claims


def _extract_user_context(claims: dict, auth_config: dict) -> dict:
    email = str(claims.get("email") or "").strip()
    username = str(
        claims.get("preferred_username")
        or claims.get("cognito:username")
        or claims.get("name")
        or claims.get("sub")
        or "operator"
    ).strip()
    identity = email or username

    raw_groups = claims.get("cognito:groups")
    if raw_groups is None:
        raw_groups = claims.get("groups")
    if isinstance(raw_groups, str):
        groups = [raw_groups]
    elif isinstance(raw_groups, list):
        groups = [str(g) for g in raw_groups if g]
    else:
        groups = []

    allowed_groups = [str(g) for g in (auth_config.get("allowedGroups") or []) if g]
    can_write = (len(allowed_groups) == 0) or any(g in allowed_groups for g in groups)

    return {
        "authenticated": True,
        "identity": identity,
        "email": email,
        "name": str(claims.get("name") or email or username),
        "sub": str(claims.get("sub") or ""),
        "groups": groups,
        "canWrite": can_write,
    }


def _authenticate_request(headers: dict, auth_config: dict, require_write: bool = False) -> dict:
    if not auth_config.get("enabled"):
        return {
            "authenticated": False,
            "identity": "Operator (Web Console)",
            "email": "",
            "name": "Operator",
            "sub": "",
            "groups": [],
            "canWrite": True,
        }

    auth_header = headers.get("authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        raise AuthError("Authentication required", status_code=401)

    token = auth_header[7:].strip()
    if not token:
        raise AuthError("Empty Bearer token", status_code=401)

    claims = _verify_jwt(token, auth_config)
    user_ctx = _extract_user_context(claims, auth_config)

    if require_write and not user_ctx["canWrite"]:
        raise AuthError(
            "Insufficient permissions: your account is not in an authorized operator group for write actions.",
            status_code=403,
        )

    return user_ctx


def _sanitize_role_session_name(actor: str) -> str:
    """Builds a valid AWS STS RoleSessionName (2-64 chars, [\\w+=,.@-])."""
    cleaned = re.sub(r"[^A-Za-z0-9_+=,.@-]", "-", actor or "operator").strip("-")
    session_name = f"serenity-hitl-{cleaned}" if cleaned else "serenity-web-hitl"
    return session_name[:64]


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


def _resp(status: int, body: dict, extra_headers: dict | None = None):
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store, no-cache, must-revalidate",
    }
    if extra_headers:
        headers.update(extra_headers)
    return {
        "statusCode": status,
        "headers": headers,
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


def _get_live_state(user_ctx: dict | None = None):
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

    payload = {
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
    if user_ctx and user_ctx.get("authenticated"):
        payload["currentUser"] = {
            "identity": user_ctx["identity"],
            "email": user_ctx["email"],
            "name": user_ctx["name"],
            "groups": user_ctx["groups"],
            "canWrite": user_ctx["canWrite"],
        }
    return payload


def handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if ORIGIN_SECRET and not hmac.compare_digest(headers.get("x-serenity-origin-secret", ""), ORIGIN_SECRET):
        return _resp(403, {"error": "Direct access forbidden"})

    raw_path = event.get("rawPath", "/api/state")
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

    # Public OIDC/Cognito SPA discovery metadata (no secrets; protected by CloudFront IP filter & origin secret)
    if raw_path == "/api/auth/config" and method == "GET":
        try:
            auth_config = _load_auth_config()
        except AuthError as exc:
            return _resp(exc.status_code, {"error": exc.message})
        return _resp(
            200,
            {
                "enabled": bool(auth_config.get("enabled", False)),
                "mode": auth_config.get("mode", "none"),
                "issuer": auth_config.get("issuer", ""),
                "clientId": auth_config.get("clientId", ""),
                "scopes": auth_config.get("scopes", "openid email profile"),
                "authorizationEndpoint": auth_config.get("authorizationEndpoint", ""),
                "tokenEndpoint": auth_config.get("tokenEndpoint", ""),
                "logoutEndpoint": auth_config.get("logoutEndpoint", ""),
                "allowedGroups": auth_config.get("allowedGroups", []),
            },
        )

    is_write_route = method != "GET"
    try:
        auth_config = _load_auth_config()
        user_ctx = _authenticate_request(headers, auth_config, require_write=is_write_route)
    except AuthError as exc:
        extra = {"WWW-Authenticate": 'Bearer realm="Serenity-Ops"'} if exc.status_code == 401 else None
        return _resp(exc.status_code, {"error": exc.message}, extra_headers=extra)

    if raw_path == "/api/state" and method == "GET":
        return _resp(200, _get_live_state(user_ctx=user_ctx))

    if raw_path == "/api/chat" and method == "POST":
        table = dynamodb.Table(TABLE_NAME)
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _resp(400, {"error": "Invalid JSON body"})
        text = (body.get("text") or "").strip()
        if not text:
            return _resp(400, {"error": "Empty message"})
        if len(text) > _MAX_CHAT_LENGTH:
            return _resp(400, {"error": f"Message exceeds maximum length of {_MAX_CHAT_LENGTH} characters"})

        now_ts = int(time.time() * 1000)
        ttl_val = int(time.time()) + (RETENTION_DAYS * 86400)
        time_str = time.strftime("%H:%M", time.gmtime())
        author = (
            f"{user_ctx['identity']} (Web Console)"
            if user_ctx.get("authenticated")
            else "Operator (Web Console)"
        )

        user_msg = {
            "PK": "SERENITY#CHAT",
            "SK": f"MSG#{now_ts}#1",
            "id": f"msg-u-{now_ts}",
            "sender": "user",
            "author": author,
            "channel": "Web Console",
            "timestamp": time_str,
            "text": text,
            "ttl": ttl_val,
        }
        table.put_item(Item=user_msg)
        return _resp(200, {"ok": True, "message": user_msg})

    if raw_path in ("/api/actions/approve", "/api/actions/reject") and method == "POST":
        table = dynamodb.Table(TABLE_NAME)
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _resp(400, {"error": "Invalid JSON body"})
        decision = "APPROVED" if raw_path.endswith("/approve") else "REJECTED"
        actor = user_ctx["identity"] if user_ctx.get("authenticated") else "Operator (Web Console)"
        return _handle_action_decision(table, body, decision, actor=actor)

    return _resp(404, {"error": f"Unknown route {method} {raw_path}"})


def _get_module_agent_role(table, agent_or_mod: str) -> str:
    mod_items = _query_pk(table, "SERENITY#MODULES", limit=50)
    target_mod = "serenity-ses" if "ses" in (agent_or_mod or "") else (
        "serenity-cloudwatch" if "cw" in (agent_or_mod or "") or "cloudwatch" in (agent_or_mod or "") else agent_or_mod
    )
    for item in mod_items:
        sk = item.get("SK", "")
        name = item.get("name") or sk.replace("MOD#", "")
        if item.get("status", "ACTIVE") == "ACTIVE" and name == target_mod:
            return item.get("agent_role_arn", "")
    return ""


def _execute_subagent_action(
    role_arn: str,
    action_name: str,
    target: str,
    params: dict,
    actor: str = "Operator (Web Console)",
) -> str:
    if not role_arn:
        return "Marked approved in Hub (no scoped sub-agent IAM role ARN configured)."

    creds = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=_sanitize_role_session_name(actor),
        DurationSeconds=900,
    )["Credentials"]
    session = boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=REGION,
    )

    if action_name in ("put_suppressed_destination", "ses_suppress") or "ses" in role_arn:
        email = (params or {}).get("email") or target
        reason = (params or {}).get("reason", "BOUNCE")
        if reason not in ("BOUNCE", "COMPLAINT"):
            reason = "BOUNCE"
        ses_v2 = session.client("sesv2", region_name=REGION)
        ses_v2.put_suppressed_destination(EmailAddress=email, Reason=reason)
        return f"Address '{_mask_email(str(email))}' added to SES suppression list ({reason})."

    if action_name == "put_metric_alarm" or "cw" in role_arn or "cloudwatch" in role_arn:
        alarm_name = (params or {}).get("alarm_name") or target
        metric_name = (params or {}).get("metric_name", "CPUUtilization")
        namespace = (params or {}).get("namespace", "AWS/ECS")
        threshold = float((params or {}).get("threshold", 85.0))
        comparison_operator = (params or {}).get("comparison_operator", "GreaterThanOrEqualToThreshold")
        evaluation_periods = int((params or {}).get("evaluation_periods", 1))
        period_seconds = int((params or {}).get("period_seconds", 60))
        statistic = (params or {}).get("statistic", "Average")
        cw = session.client("cloudwatch", region_name=REGION)
        cw.put_metric_alarm(
            AlarmName=alarm_name,
            MetricName=metric_name,
            Namespace=namespace,
            Threshold=threshold,
            ComparisonOperator=comparison_operator,
            EvaluationPeriods=evaluation_periods,
            Period=period_seconds,
            Statistic=statistic,
            Tags=[{"Key": "ManagedBy", "Value": "serenity-ops"}],
        )
        return f"CloudWatch alarm '{alarm_name}' created on {namespace}/{metric_name}."

    return f"Action '{action_name}' recorded as approved."


def _handle_action_decision(table, body: dict, decision: str, actor: str = "Operator (Web Console)"):
    incident_id = (body.get("incidentId") or "").strip()
    event_id = (body.get("eventId") or "").strip()
    if not incident_id and not event_id:
        return _resp(400, {"error": "incidentId or eventId is required"})

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if event_id:
        ses_items = _query_pk(table, "MOD#serenity-ses", limit=100)
        target_item = next(
            (it for it in ses_items if it.get("id") == event_id or it.get("SK") == event_id),
            None,
        )
        if not target_item:
            return _resp(404, {"error": f"SES event '{event_id}' not found"})

        new_status = "APPLIED" if decision == "APPROVED" else "REJECTED"
        exec_msg = ""
        if decision == "APPROVED":
            recipient = target_item.get("recipient", "")
            evt_type = str(target_item.get("type", "BOUNCE")).upper()
            reason = "COMPLAINT" if "COMPLAINT" in evt_type else "BOUNCE"
            role_arn = _get_module_agent_role(table, "serenity-ses")
            if role_arn and recipient and "@" in recipient and "***" not in recipient:
                try:
                    exec_msg = _execute_subagent_action(
                        role_arn,
                        "put_suppressed_destination",
                        recipient,
                        {"email": recipient, "reason": reason},
                        actor=actor,
                    )
                except Exception as exc:
                    return _resp(500, {"error": f"Sub-agent execution failed: {_redact_sensitive_text(str(exc))}"})

        table.update_item(
            Key={"PK": target_item["PK"], "SK": target_item["SK"]},
            UpdateExpression="SET actionStatus = :st, updated_at = :now, updated_by = :actor",
            ExpressionAttributeValues={":st": new_status, ":now": now_iso, ":actor": actor},
        )
        return _resp(200, {"ok": True, "eventId": event_id, "status": new_status, "result": exec_msg})

    ops_items = _query_pk(table, "SERENITY#OPS", limit=100) + _query_pk(table, "SERENITY#INCIDENTS", limit=100)
    inc_item = next(
        (
            it
            for it in ops_items
            if it.get("id") == incident_id
            or it.get("incident_id") == incident_id
            or it.get("SK") == incident_id
        ),
        None,
    )

    pending_items = _query_pk(table, "SERENITY#PENDING_ACTIONS", limit=100)
    pending_item = next(
        (
            it
            for it in pending_items
            if it.get("incident_id") == incident_id or it.get("action_id") == incident_id
        ),
        None,
    )

    if not inc_item and not pending_item:
        return _resp(404, {"error": f"Incident or pending action '{incident_id}' not found"})

    exec_result = ""
    if decision == "APPROVED":
        proposed = (inc_item or {}).get("proposed_action") or (inc_item or {}).get("proposedAction") or {}
        agent_name = (pending_item or {}).get("agent") or proposed.get("agent", "")
        action_name = (pending_item or {}).get("action") or proposed.get("action", "")
        target = (pending_item or {}).get("target") or proposed.get("target", "")
        params = (pending_item or {}).get("action_params") or {}
        role_arn = (pending_item or {}).get("role_arn") or _get_module_agent_role(table, agent_name)
        if role_arn and action_name:
            try:
                exec_result = _execute_subagent_action(
                    role_arn, action_name, target, params, actor=actor
                )
            except Exception as exc:
                return _resp(500, {"error": f"Sub-agent execution failed: {_redact_sensitive_text(str(exc))}"})

    if pending_item:
        try:
            table.delete_item(Key={"PK": pending_item["PK"], "SK": pending_item["SK"]})
        except Exception:
            pass

    if inc_item:
        prop_field = "proposedAction" if "proposedAction" in inc_item else "proposed_action"
        current_prop = dict(inc_item.get(prop_field) or {})
        current_prop["status"] = decision
        current_prop["updated_at"] = now_iso
        current_prop["executed_by"] = actor
        if exec_result:
            current_prop["execution_result"] = exec_result

        table.update_item(
            Key={"PK": inc_item["PK"], "SK": inc_item["SK"]},
            UpdateExpression=f"SET {prop_field} = :prop",
            ExpressionAttributeValues={":prop": current_prop},
        )

    return _resp(
        200,
        {
            "ok": True,
            "incidentId": incident_id,
            "status": decision,
            "result": _redact_sensitive_text(exec_result),
        },
    )
