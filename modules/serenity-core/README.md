# 🏛️ Serenity-Core (`modules/serenity-core`)

**Serverless Core Hub, Central DynamoDB Auto-Discovery Table & Live Web Console ($0/hr Idle Cost) for Serenity-Ops.**

[![Terraform](https://img.shields.io/badge/Terraform-%3E%3D_1.10-7B42BC?style=flat-square&logo=terraform&logoColor=white)](https://github.com/e-serenity/terraform-aws-serenity-ops/blob/main/README.md)
[![AWS](https://img.shields.io/badge/AWS-DynamoDB_%7C_CloudFront_OAC_%7C_Lambda_ARM64-FF9900?style=flat-square&logo=amazon-web-services&logoColor=white)](https://aws.amazon.com/)

`source = "e-serenity/serenity-ops/aws//modules/serenity-core"`

## Overview

`serenity-core` provisions the serverless core resources of the **[Serenity-Ops](https://github.com/e-serenity/terraform-aws-serenity-ops/blob/main/README.md)** platform (no VPC, NAT Gateway, or ECS cluster required):

- **Central DynamoDB Hub (`dynamodb.tf`):** Single-Table Design (`serenity-ops-hub`) with `PAY_PER_REQUEST` billing and native **AWS DynamoDB TTL** enabled (`ttl` attribute) for automatic history expiration without cron jobs.
- **Serverless Live Web Console (`frontend.tf`, `api.tf`, `auth.tf`, `front/`, `lambda/api/`):** Private S3 bucket, CloudFront Origin Access Control (OAC), `$0/mo` Edge IPv4/IPv6 CIDR filtering (`dashboard_allowed_ips`), **AWS Cognito / Generic OIDC authentication (OAuth 2.0 PKCE + server-side RS256 JWT verification)**, and ARM64 Python 3.12 Live API Lambda (`/api/auth/config`, `/api/state`, `/api/chat`, `/api/actions/approve`, `/api/actions/reject`).

## Usage

### Default: AWS Cognito Authentication ($0/mo Free Tier up to 10,000 MAU)

```hcl
module "serenity_core" {
  source  = "e-serenity/serenity-ops/aws//modules/serenity-core"
  version = "~> 0.1"

  project_name                   = "serenity-ops"
  environment                    = "prod"
  region                         = "eu-west-3"
  dashboard_allowed_ips          = ["203.0.113.10/32"]
  dashboard_auth_mode            = "cognito" # default
  dashboard_cognito_admin_emails = ["ops@example.com"]
  dashboard_oidc_allowed_groups  = ["serenity-admins"]
}
```

### Bring Your Own OIDC Provider (Okta, Microsoft Entra ID, Google Workspace, Authentik, Keycloak)

```hcl
module "serenity_core" {
  source  = "e-serenity/serenity-ops/aws//modules/serenity-core"
  version = "~> 0.1"

  project_name                  = "serenity-ops"
  environment                   = "prod"
  region                        = "eu-west-3"
  dashboard_allowed_ips         = ["203.0.113.10/32"]
  dashboard_auth_mode           = "oidc"
  dashboard_oidc_issuer_url     = "https://auth.example.com/application/o/serenity-ops/"
  dashboard_oidc_client_id      = "your-public-spa-pkce-client-id"
  dashboard_oidc_allowed_groups = ["platform-admins"]
}
```

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.10.0 |
| <a name="requirement_archive"></a> [archive](#requirement\_archive) | >= 2.4.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 6.0.0 |
| <a name="requirement_random"></a> [random](#requirement\_random) | >= 3.5.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_archive"></a> [archive](#provider\_archive) | >= 2.4.0 |
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 6.0.0 |
| <a name="provider_random"></a> [random](#provider\_random) | >= 3.5.0 |

## Modules

No modules.

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_dashboard_additional_callback_urls"></a> [dashboard_additional_callback_urls](#input\_dashboard\_additional\_callback\_urls) | Optional extra OAuth2 callback/logout URLs registered on the Cognito SPA client (e.g., custom domain https://ops.example.com or http://localhost:5173 for local testing) | `list(string)` | `[]` | no |
| <a name="input_dashboard_allowed_ips"></a> [dashboard_allowed_ips](#input\_dashboard\_allowed\_ips) | Allowed IPv4 or IPv6 addresses/CIDRs for the Web Dashboard via CloudFront Function (fail-closed by default: empty [] blocks all public access; specify your VPN/office CIDRs or explicitly set ['0.0.0.0/0'] to open publicly) | `list(string)` | `[]` | no |
| <a name="input_dashboard_auth_mode"></a> [dashboard_auth_mode](#input\_dashboard\_auth\_mode) | Authentication mode for the Web Dashboard and Live API: 'cognito' (default, provisions an AWS Cognito User Pool with Hosted UI + PKCE + JWT verification at $0/mo Free Tier), 'oidc' (bring your own OIDC provider such as Okta, Entra ID, Google Workspace, Authentik, or Keycloak), or 'none' (rely solely on CloudFront Edge IP filtering) | `string` | `"cognito"` | no |
| <a name="input_dashboard_cognito_admin_emails"></a> [dashboard_cognito_admin_emails](#input\_dashboard\_cognito\_admin\_emails) | Optional list of operator email addresses pre-provisioned in the Cognito User Pool and added to the 'serenity-admins' group (used when dashboard_auth_mode = 'cognito') | `list(string)` | `[]` | no |
| <a name="input_dashboard_cognito_domain_prefix"></a> [dashboard_cognito_domain_prefix](#input\_dashboard\_cognito\_domain\_prefix) | Optional globally unique prefix for the Cognito Hosted UI domain (used when dashboard_auth_mode = 'cognito'). Defaults to '<project_name>-<environment>-<account_hash>'. | `string` | `""` | no |
| <a name="input_dashboard_cognito_mfa_configuration"></a> [dashboard_cognito_mfa_configuration](#input\_dashboard\_cognito\_mfa\_configuration) | MFA configuration for the Cognito User Pool ('OPTIONAL', 'ON', or 'OFF'). Software TOTP authenticator apps are enabled whenever set to 'OPTIONAL' or 'ON'. | `string` | `"OPTIONAL"` | no |
| <a name="input_dashboard_oidc_allowed_groups"></a> [dashboard_oidc_allowed_groups](#input\_dashboard\_oidc\_allowed\_groups) | Optional list of group names (checked against JWT 'cognito:groups' or 'groups' claim) authorized to execute write actions (POST /api/chat, POST /api/actions/approve, POST /api/actions/reject). When empty, any authenticated user can perform actions. | `list(string)` | `[]` | no |
| <a name="input_dashboard_oidc_authorization_endpoint"></a> [dashboard_oidc_authorization_endpoint](#input\_dashboard\_oidc\_authorization\_endpoint) | Optional override for the OIDC authorization endpoint (auto-discovered from '<issuer>/.well-known/openid-configuration' when empty) | `string` | `""` | no |
| <a name="input_dashboard_oidc_client_id"></a> [dashboard_oidc_client_id](#input\_dashboard\_oidc\_client\_id) | OIDC public SPA Client ID (Authorization Code + PKCE, no client secret). Required when dashboard_auth_mode = 'oidc'. | `string` | `""` | no |
| <a name="input_dashboard_oidc_issuer_url"></a> [dashboard_oidc_issuer_url](#input\_dashboard\_oidc\_issuer\_url) | OIDC Issuer URL (e.g., 'https://accounts.google.com' or 'https://login.microsoftonline.com/<tenant>/v2.0'). Required when dashboard_auth_mode = 'oidc'. | `string` | `""` | no |
| <a name="input_dashboard_oidc_logout_endpoint"></a> [dashboard_oidc_logout_endpoint](#input\_dashboard\_oidc\_logout\_endpoint) | Optional override for the OIDC logout / end_session endpoint (auto-discovered from '<issuer>/.well-known/openid-configuration' when empty) | `string` | `""` | no |
| <a name="input_dashboard_oidc_scopes"></a> [dashboard_oidc_scopes](#input\_dashboard\_oidc\_scopes) | Space-separated OAuth2 scopes requested by the Web Dashboard during OIDC/Cognito sign-in | `string` | `"openid email profile"` | no |
| <a name="input_dashboard_oidc_token_endpoint"></a> [dashboard_oidc_token_endpoint](#input\_dashboard\_oidc\_token\_endpoint) | Optional override for the OIDC token endpoint (auto-discovered from '<issuer>/.well-known/openid-configuration' when empty) | `string` | `""` | no |
| <a name="input_dashboard_price_class"></a> [dashboard_price_class](#input\_dashboard\_price\_class) | CloudFront price class for the Web Dashboard (PriceClass_100, PriceClass_200, PriceClass_All) | `string` | `"PriceClass_100"` | no |
| <a name="input_dashboard_s3_force_destroy"></a> [dashboard_s3_force_destroy](#input\_dashboard_s3_force_destroy) | Whether to allow force-destroying the S3 bucket hosting the Web Dashboard even when non-empty (defaults to false for production safety) | `bool` | `false` | no |
| <a name="input_dynamodb_enable_pitr"></a> [dynamodb_enable_pitr](#input\_dynamodb_enable_pitr) | Enable Point-in-Time Recovery (PITR) on the DynamoDB Hub table | `bool` | `false` | no |
| <a name="input_dynamodb_hub_table_name"></a> [dynamodb_hub_table_name](#input\_dynamodb_hub_table_name) | Custom DynamoDB Hub table name (defaults to <project_name>-<environment>-hub) | `string` | `""` | no |
| <a name="input_enable_dashboard"></a> [enable_dashboard](#input\_enable_dashboard) | Enable Serenity-Ops Web Dashboard (Private S3 + CloudFront OAC + Live API Lambda) | `bool` | `true` | no |
| <a name="input_enable_dynamodb_hub"></a> [enable_dynamodb_hub](#input\_enable_dynamodb_hub) | Enable central DynamoDB Hub table (Single-Table Design for module discovery, state and audit) | `bool` | `true` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | Deployment environment (e.g., dev, preprod, prod) | `string` | `"preprod"` | no |
| <a name="input_project_name"></a> [project_name](#input\_project_name) | Project name and resource prefix (e.g., serenity-ops) | `string` | `"serenity-ops"` | no |
| <a name="input_region"></a> [region](#input\_region) | Target AWS region | `string` | `"eu-west-3"` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Additional tags applied to module resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_dashboard_api_role_arn"></a> [dashboard_api_role_arn](#output\_dashboard_api_role_arn) | IAM Role ARN of the Web Dashboard Live API Lambda (null when enable_dashboard = false) |
| <a name="output_dashboard_auth_mode"></a> [dashboard_auth_mode](#output\_dashboard_auth_mode) | Configured authentication mode for the Web Dashboard ('cognito', 'oidc', or 'none') |
| <a name="output_dashboard_cloudfront_id"></a> [dashboard_cloudfront_id](#output\_dashboard_cloudfront_id) | CloudFront Distribution ID for the Web Dashboard |
| <a name="output_dashboard_cognito_client_id"></a> [dashboard_cognito_client_id](#output\_dashboard_cognito_client_id) | AWS Cognito SPA App Client ID (PKCE, no client secret; null when dashboard_auth_mode != 'cognito') |
| <a name="output_dashboard_cognito_hosted_ui_url"></a> [dashboard_cognito_hosted_ui_url](#output\_dashboard_cognito_hosted_ui_url) | HTTPS base URL of the AWS Cognito Hosted UI domain (null when dashboard_auth_mode != 'cognito') |
| <a name="output_dashboard_cognito_user_pool_arn"></a> [dashboard_cognito_user_pool_arn](#output\_dashboard_cognito_user_pool_arn) | AWS Cognito User Pool ARN protecting the Web Dashboard (null when dashboard_auth_mode != 'cognito') |
| <a name="output_dashboard_cognito_user_pool_id"></a> [dashboard_cognito_user_pool_id](#output\_dashboard_cognito_user_pool_id) | AWS Cognito User Pool ID protecting the Web Dashboard (null when dashboard_auth_mode != 'cognito') |
| <a name="output_dashboard_s3_bucket_name"></a> [dashboard_s3_bucket_name](#output\_dashboard_s3_bucket_name) | Private S3 bucket name hosting the Web Dashboard |
| <a name="output_dashboard_url"></a> [dashboard_url](#output\_dashboard_url) | HTTPS URL of the Serenity-Ops Web Dashboard (CloudFront) |
| <a name="output_dynamodb_hub_table_arn"></a> [dynamodb_hub_table_arn](#output\_dynamodb_hub_table_arn) | Central DynamoDB Hub table ARN |
| <a name="output_dynamodb_hub_table_name"></a> [dynamodb_hub_table_name](#output\_dynamodb_hub_table_name) | Central DynamoDB Hub table name (serenity-ops-hub) |
<!-- END_TF_DOCS -->
