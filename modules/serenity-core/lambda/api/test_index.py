import base64
import hashlib
import io
import json
import math
import random
import time
from unittest.mock import MagicMock

import pytest

import index as api


# ---------------------------------------------------------------------------
# Pure-Python ephemeral RSA keypair & RS256 signer (zero external packages,
# zero hardcoded private keys in repository)
# ---------------------------------------------------------------------------

def _is_probable_prime(n: int, k: int = 16) -> bool:
    if n < 2:
        return False
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in small_primes:
        if n == p:
            return True
        if n % p == 0:
            return False
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    rng = random.SystemRandom()
    for _ in range(k):
        a = rng.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits: int) -> int:
    rng = random.SystemRandom()
    while True:
        cand = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(cand):
            return cand


def _generate_rsa_keypair(bits: int = 1024):
    e = 65537
    half = bits // 2
    while True:
        p = _gen_prime(half)
        q = _gen_prime(half)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if math.gcd(e, phi) == 1:
            n = p * q
            d = pow(e, -1, phi)
            return n, e, d


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _int_to_b64url(val: int) -> str:
    length = (val.bit_length() + 7) // 8
    return _b64url(val.to_bytes(length, "big"))


def _sign_rs256_jwt(header: dict, claims: dict, n: int, d: int) -> str:
    h_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")

    k = (n.bit_length() + 7) // 8
    digest = hashlib.sha256(signing_input).digest()
    der_prefix = bytes.fromhex("3031300d060960864801650304020105000420")
    t = der_prefix + digest
    ps_len = k - len(t) - 3
    em = b"\x00\x01" + (b"\xff" * ps_len) + b"\x00" + t
    sig_int = pow(int.from_bytes(em, "big"), d, n)
    sig_bytes = sig_int.to_bytes(k, "big")
    return f"{h_b64}.{p_b64}.{_b64url(sig_bytes)}"


@pytest.fixture(scope="module")
def rsa_keypair():
    n, e, d = _generate_rsa_keypair(bits=1024)
    jwk = {
        "kty": "RSA",
        "kid": "test-kid-1",
        "use": "sig",
        "alg": "RS256",
        "n": _int_to_b64url(n),
        "e": _int_to_b64url(e),
    }
    return {"n": n, "e": e, "d": d, "jwk": jwk}


@pytest.fixture(autouse=True)
def reset_caches(monkeypatch):
    api._AUTH_CONFIG_CACHE["value"] = None
    api._AUTH_CONFIG_CACHE["expires_at"] = 0.0
    api._OIDC_DISCOVERY_CACHE.clear()
    api._JWKS_CACHE.clear()
    monkeypatch.setattr(api, "ORIGIN_SECRET", "test-origin-secret")
    monkeypatch.setattr(api, "ACCOUNT_ID", "123456789012")
    monkeypatch.setattr(api, "AUTH_MODE", "cognito")
    monkeypatch.setattr(api, "AUTH_CONFIG_BUCKET", "test-dashboard-bucket")
    monkeypatch.setattr(api, "AUTH_CONFIG_KEY", "_internal/auth-config.json")


def _configure_auth(monkeypatch, rsa_keypair, allowed_groups=None, mode="cognito"):
    issuer = "https://cognito-idp.eu-west-3.amazonaws.com/eu-west-3_TESTPOOL"
    client_id = "test-spa-client-123"
    auth_doc = {
        "enabled": mode != "none",
        "mode": mode,
        "issuer": issuer if mode != "none" else "",
        "clientId": client_id if mode != "none" else "",
        "scopes": "openid email profile",
        "authorizationEndpoint": "https://serenity-test.auth.eu-west-3.amazoncognito.com/oauth2/authorize"
        if mode != "none"
        else "",
        "tokenEndpoint": "https://serenity-test.auth.eu-west-3.amazoncognito.com/oauth2/token"
        if mode != "none"
        else "",
        "logoutEndpoint": "https://serenity-test.auth.eu-west-3.amazoncognito.com/logout"
        if mode != "none"
        else "",
        "allowedGroups": allowed_groups or [],
    }
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": io.BytesIO(json.dumps(auth_doc).encode("utf-8"))}
    monkeypatch.setattr(api, "s3_client", mock_s3)
    monkeypatch.setattr(api, "AUTH_MODE", mode)

    def fake_http_get_json(url: str, timeout: int = 5):
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "issuer": issuer,
                "jwks_uri": f"{issuer}/.well-known/jwks.json",
                "authorization_endpoint": auth_doc["authorizationEndpoint"],
                "token_endpoint": auth_doc["tokenEndpoint"],
                "end_session_endpoint": auth_doc["logoutEndpoint"],
            }
        if url.endswith("/.well-known/jwks.json"):
            return {"keys": [rsa_keypair["jwk"]]}
        raise AssertionError(f"Unexpected URL fetch: {url}")

    monkeypatch.setattr(api, "_http_get_json", fake_http_get_json)
    return issuer, client_id


def _make_event(path: str, method: str = "GET", body: dict | None = None, token: str | None = None, origin_secret: str = "test-origin-secret"):
    headers = {"x-serenity-origin-secret": origin_secret}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return {
        "rawPath": path,
        "headers": headers,
        "requestContext": {"http": {"method": method}},
        "body": json.dumps(body) if body is not None else "",
    }


def _mock_dynamodb_and_cw(monkeypatch, items_by_pk=None):
    items_by_pk = items_by_pk or {}
    mock_table = MagicMock()

    def fake_query(**kwargs):
        expr = kwargs.get("KeyConditionExpression")
        pk_val = expr._values[1] if hasattr(expr, "_values") else ""
        return {"Items": list(items_by_pk.get(pk_val, []))}

    mock_table.query.side_effect = fake_query
    mock_ddb = MagicMock()
    mock_ddb.Table.return_value = mock_table
    monkeypatch.setattr(api, "dynamodb", mock_ddb)

    mock_cw = MagicMock()
    mock_cw.describe_alarms.return_value = {"MetricAlarms": []}
    del mock_cw.DescribeAlarms
    monkeypatch.setattr(api, "cw_client", mock_cw)
    return mock_table


def test_direct_access_without_origin_secret_is_forbidden(monkeypatch, rsa_keypair):
    _configure_auth(monkeypatch, rsa_keypair)
    resp = api.handler(_make_event("/api/auth/config", origin_secret="wrong-secret"), None)
    assert resp["statusCode"] == 403


def test_auth_config_endpoint_is_public_and_returns_oidc_metadata(monkeypatch, rsa_keypair):
    issuer, client_id = _configure_auth(monkeypatch, rsa_keypair)
    resp = api.handler(_make_event("/api/auth/config"), None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert data["enabled"] is True
    assert data["mode"] == "cognito"
    assert data["issuer"] == issuer
    assert data["clientId"] == client_id
    assert data["authorizationEndpoint"].endswith("/oauth2/authorize")


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/api/state", "GET", None),
        ("/api/chat", "POST", {"text": "hello"}),
        ("/api/actions/approve", "POST", {"incidentId": "inc-1"}),
        ("/api/actions/reject", "POST", {"incidentId": "inc-1"}),
    ],
)
def test_unauthenticated_requests_return_401(monkeypatch, rsa_keypair, path, method, body):
    _configure_auth(monkeypatch, rsa_keypair)
    resp = api.handler(_make_event(path, method=method, body=body, token=None), None)
    assert resp["statusCode"] == 401
    assert "WWW-Authenticate" in resp["headers"]


def test_jwt_tampered_payload_or_alg_none_is_rejected(monkeypatch, rsa_keypair):
    issuer, client_id = _configure_auth(monkeypatch, rsa_keypair)
    now = int(time.time())
    valid_token = _sign_rs256_jwt(
        {"alg": "RS256", "kid": "test-kid-1", "typ": "JWT"},
        {"iss": issuer, "aud": client_id, "sub": "u-1", "email": "alice@example.com", "exp": now + 300},
        rsa_keypair["n"],
        rsa_keypair["d"],
    )

    # Tamper payload claim
    h, _, s = valid_token.split(".")
    tampered_p = _b64url(json.dumps({"iss": issuer, "aud": client_id, "sub": "u-1", "email": "evil@example.com", "exp": now + 300}).encode())
    resp = api.handler(_make_event("/api/state", token=f"{h}.{tampered_p}.{s}"), None)
    assert resp["statusCode"] == 401

    # Algorithm "none" attack
    alg_none_h = _b64url(json.dumps({"alg": "none", "kid": "test-kid-1"}).encode())
    resp_none = api.handler(_make_event("/api/state", token=f"{alg_none_h}.{tampered_p}."), None)
    assert resp_none["statusCode"] == 401

    # Expired token
    expired_token = _sign_rs256_jwt(
        {"alg": "RS256", "kid": "test-kid-1", "typ": "JWT"},
        {"iss": issuer, "aud": client_id, "sub": "u-1", "email": "alice@example.com", "exp": now - 120},
        rsa_keypair["n"],
        rsa_keypair["d"],
    )
    resp_exp = api.handler(_make_event("/api/state", token=expired_token), None)
    assert resp_exp["statusCode"] == 401


def test_authenticated_state_and_chat_record_operator_identity(monkeypatch, rsa_keypair):
    issuer, client_id = _configure_auth(monkeypatch, rsa_keypair, allowed_groups=["serenity-admins"])
    mock_table = _mock_dynamodb_and_cw(
        monkeypatch,
        items_by_pk={
            "MOD#serenity-ses": [
                {
                    "PK": "MOD#serenity-ses",
                    "SK": "EVENT#2026-11-22#1",
                    "id": "evt-1",
                    "recipient": "john.doe@customer.com",
                    "type": "HardBounce",
                }
            ]
        },
    )

    now = int(time.time())
    token = _sign_rs256_jwt(
        {"alg": "RS256", "kid": "test-kid-1", "typ": "JWT"},
        {
            "iss": issuer,
            "aud": client_id,
            "token_use": "id",
            "sub": "u-123",
            "email": "alice@e-serenity.fr",
            "cognito:groups": ["serenity-admins"],
            "exp": now + 300,
        },
        rsa_keypair["n"],
        rsa_keypair["d"],
    )

    state_resp = api.handler(_make_event("/api/state", token=token), None)
    assert state_resp["statusCode"] == 200
    state = json.loads(state_resp["body"])
    assert state["accountId"] == "********9012"
    assert state["emailEvents"][0]["recipient"] == "j***e@customer.com"
    assert state["currentUser"]["email"] == "alice@e-serenity.fr"
    assert state["currentUser"]["canWrite"] is True

    chat_resp = api.handler(_make_event("/api/chat", method="POST", body={"text": "Check ECS"}, token=token), None)
    assert chat_resp["statusCode"] == 200
    saved_item = mock_table.put_item.call_args.kwargs["Item"]
    assert saved_item["author"] == "alice@e-serenity.fr (Web Console)"


def test_group_rbac_blocks_viewer_on_write_routes_and_allows_read(monkeypatch, rsa_keypair):
    issuer, client_id = _configure_auth(monkeypatch, rsa_keypair, allowed_groups=["serenity-admins"])
    _mock_dynamodb_and_cw(monkeypatch)

    now = int(time.time())
    viewer_token = _sign_rs256_jwt(
        {"alg": "RS256", "kid": "test-kid-1", "typ": "JWT"},
        {
            "iss": issuer,
            "aud": client_id,
            "sub": "u-viewer",
            "email": "viewer@e-serenity.fr",
            "cognito:groups": ["readonly"],
            "exp": now + 300,
        },
        rsa_keypair["n"],
        rsa_keypair["d"],
    )

    state_resp = api.handler(_make_event("/api/state", token=viewer_token), None)
    assert state_resp["statusCode"] == 200
    assert json.loads(state_resp["body"])["currentUser"]["canWrite"] is False

    chat_resp = api.handler(_make_event("/api/chat", method="POST", body={"text": "hack"}, token=viewer_token), None)
    assert chat_resp["statusCode"] == 403

    approve_resp = api.handler(
        _make_event("/api/actions/approve", method="POST", body={"incidentId": "inc-1"}, token=viewer_token), None
    )
    assert approve_resp["statusCode"] == 403


def test_hitl_approval_records_operator_in_dynamodb_and_sts_session(monkeypatch, rsa_keypair):
    issuer, client_id = _configure_auth(monkeypatch, rsa_keypair)
    mock_table = _mock_dynamodb_and_cw(
        monkeypatch,
        items_by_pk={
            "SERENITY#OPS": [
                {
                    "PK": "SERENITY#OPS",
                    "SK": "INCIDENT#2026-11-22#1",
                    "id": "inc-42",
                    "proposedAction": {
                        "agent": "serenity-agent-ses",
                        "action": "put_suppressed_destination",
                        "target": "bad@example.com",
                        "status": "PENDING_APPROVAL",
                    },
                }
            ],
            "SERENITY#PENDING_ACTIONS": [
                {
                    "PK": "SERENITY#PENDING_ACTIONS",
                    "SK": "ACTION#inc-42",
                    "incident_id": "inc-42",
                    "agent": "serenity-agent-ses",
                    "action": "put_suppressed_destination",
                    "target": "bad@example.com",
                    "role_arn": "arn:aws:iam::123456789012:role/serenity-agent-ses",
                }
            ],
        },
    )

    mock_sts = MagicMock()
    mock_sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIAEXAMPLE",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
        }
    }
    monkeypatch.setattr(api, "sts_client", mock_sts)

    mock_ses = MagicMock()
    mock_session = MagicMock()
    mock_session.client.return_value = mock_ses
    monkeypatch.setattr(api.boto3, "Session", MagicMock(return_value=mock_session))

    now = int(time.time())
    token = _sign_rs256_jwt(
        {"alg": "RS256", "kid": "test-kid-1", "typ": "JWT"},
        {"iss": issuer, "aud": client_id, "sub": "u-admin", "email": "ops@e-serenity.fr", "exp": now + 300},
        rsa_keypair["n"],
        rsa_keypair["d"],
    )

    resp = api.handler(_make_event("/api/actions/approve", method="POST", body={"incidentId": "inc-42"}, token=token), None)
    assert resp["statusCode"] == 200
    assert mock_sts.assume_role.call_args.kwargs["RoleSessionName"] == "serenity-hitl-ops@e-serenity.fr"
    mock_ses.put_suppressed_destination.assert_called_once_with(EmailAddress="bad@example.com", Reason="BOUNCE")

    updated_prop = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"][":prop"]
    assert updated_prop["executed_by"] == "ops@e-serenity.fr"
    assert updated_prop["status"] == "APPROVED"


def test_auth_mode_none_allows_requests_without_bearer_token(monkeypatch, rsa_keypair):
    _configure_auth(monkeypatch, rsa_keypair, mode="none")
    _mock_dynamodb_and_cw(monkeypatch)
    resp = api.handler(_make_event("/api/state", token=None), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["mode"] == "live"
