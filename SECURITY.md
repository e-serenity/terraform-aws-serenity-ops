# Security Policy & Threat Model

**Serenity-Ops** runs inside the customer's AWS account with network isolation, least-privilege IAM boundaries, and human validation for all infrastructure mutations.

## Defense-in-Depth Architecture

### 1. Data Sovereignty & Zero External Ingestion
- All logs, metrics, traces, and incident states stay inside your AWS account (`CloudWatch`, `DynamoDB serenity-ops-hub`, `S3`).
- AI inference uses **AWS Bedrock** (`Converse API`) inside your AWS region (optionally routed through a Private VPC Interface Endpoint so prompts do not traverse the public internet).

### 2. Zero Inbound Ports (`serenity-bot`)
- The `serenity-bot` ECS service runs in private subnets with no public IP and no Application Load Balancer (ALB).
- Communication with Slack uses **Slack Socket Mode** (outbound-only TLS WebSocket connection). No inbound webhook ports are exposed to the internet.

### 3. Web Console Edge Protection & Operator Authentication (`serenity-core`)
- **Private S3 + CloudFront OAC:** Static frontend assets are stored in a private S3 bucket (`block_public_acls = true`, `block_public_policy = true`) accessible only by CloudFront via Origin Access Control (OAC).
- **Fail-Closed Edge IPv4 & IPv6 Allowlisting (`dashboard_allowed_ips`):** A CloudFront Function (`viewer-request`) is always attached to the Web Console distribution and enforces your CIDR allowlist at the AWS Edge before requests reach S3 or the Live API Lambda. By default (`dashboard_allowed_ips = []`), all public access is blocked (`HTTP 403 Forbidden`); operators must explicitly specify their VPN/office CIDRs (or `["0.0.0.0/0"]` if public access is intentionally desired). If only IPv4 CIDRs are provided, IPv6 (`AAAA`) is disabled on the distribution to prevent dual-stack bypasses or blocks.
- **Origin Secret Header Verification:** CloudFront injects a random 32-character `x-serenity-origin-secret` header into requests forwarded to `/api/*`. The Live API Lambda rejects direct invocations missing this header with `HTTP 403 Forbidden` using constant-time comparison.
- **OAuth 2.0 PKCE + Cryptographic JWT Verification (`dashboard_auth_mode`):** Enabled by default (`dashboard_auth_mode = "cognito"`, or `"oidc"` for BYO Okta/Entra ID/Google/Authentik/Keycloak). Self-signup is disabled (`allow_admin_create_user_only = true`), software TOTP MFA is enabled (`OPTIONAL` by default), and every data/mutation route (`/api/state`, `/api/chat`, `/api/actions/approve`, `/api/actions/reject`) cryptographically verifies the `Authorization: Bearer <jwt>` RS256/RS384/RS512 signature against the issuer's JWKS before executing. Optional group RBAC (`dashboard_oidc_allowed_groups`) restricts write/HITL endpoints while preserving read-only access for viewers. Authenticated operator identity is recorded in DynamoDB Hub and forwarded to AWS CloudTrail via STS `RoleSessionName` (`serenity-hitl-<operator>`).

### 4. 3-Layer AI IAM Governance & Human-in-the-Loop
1. **Mode 1: Autonomous Observability Read (`READ AUTO`):** By default, the base `serenity-bot` task role is scoped to a least-privilege observability IAM policy (`cloudwatch:Describe*/GetMetric*`, `logs:FilterLogEvents/Get*/Describe*`, `ecs:Describe*/List*`, `rds:Describe*`, `cloudtrail:LookupEvents`, `dynamodb:DescribeTable/ListTables`, `lambda:GetFunctionConfiguration/ListFunctions`). It cannot read application payloads (`s3:GetObject`, `dynamodb:GetItem/Scan` on application tables, `secretsmanager:GetSecretValue`, or Lambda code bundles) unless explicitly opted in via `enable_aws_readonly_access` or `additional_task_iam_policies`.
2. **Mode 2: Mandatory Human Approval (`WRITE ON APPROVAL`):** Any write operation proposed by the AI generates a `PENDING` approval card in both Slack and the Web Console. No mutation runs until an operator clicks **Approve**.
3. **Mode 3: Tag-Scoped Domain Sub-Agents (`sts:AssumeRole`):** Write permissions are isolated in dedicated per-module IAM roles (`serenity-agent-cw`, `serenity-agent-ses`). Destructive or mutating actions on existing resources are restricted by AWS IAM policy conditions requiring the tag `ManagedBy = serenity-ops`:
   ```json
   "Condition": {
     "StringEquals": {
       "aws:ResourceTag/ManagedBy": "serenity-ops"
     }
   }
   ```

## Reporting a Vulnerability

If you discover a security vulnerability in **Serenity-Ops** or any of its modules:

1. **Do not open a public GitHub issue.**
2. Report the issue privately via **[https://e-serenity.fr](https://e-serenity.fr)** or by emailing `contact@e-serenity.fr`.
3. Include a description of the issue, reproduction steps, and the affected module (`serenity-core`, `serenity-bot`, or `serenity-ses`).

We acknowledge security reports within 48 hours and provide a remediation plan or patch within 7 days.
