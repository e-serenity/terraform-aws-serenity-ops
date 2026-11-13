<div align="center">

# 🏛️ Serenity-Core (`modules/serenity-core`)

**Serverless Core Hub, Central DynamoDB Auto-Discovery Table & Live Web Console ($0/hr Idle Cost) for Serenity-Ops.**

[![Terraform](https://img.shields.io/badge/Terraform-%3E%3D_1.10-7B42BC?style=flat-square&logo=terraform&logoColor=white)](../../README.md)
[![AWS](https://img.shields.io/badge/AWS-DynamoDB_%7C_CloudFront_OAC_%7C_Lambda_ARM64-FF9900?style=flat-square&logo=amazon-web-services&logoColor=white)](https://aws.amazon.com/)

<code>source = "e-serenity/serenity-ops/aws//modules/serenity-core"</code>

</div>

## Overview

`serenity-core` provisions the serverless core resources of the **[Serenity-Ops](../../README.md)** platform (no VPC, NAT Gateway, or ECS cluster required):

- **Central DynamoDB Hub (`dynamodb.tf`):** Single-Table Design (`serenity-ops-hub`) with `PAY_PER_REQUEST` billing and native **AWS DynamoDB TTL** enabled (`ttl` attribute) for automatic history expiration without cron jobs.
- **Serverless Live Web Console (`frontend.tf`, `api.tf`, `front/`, `lambda/api/`):** Private S3 bucket, CloudFront Origin Access Control (OAC), `$0/mo` Edge IPv4/IPv6 CIDR filtering (`dashboard_allowed_ips`), and ARM64 Python 3.12 Live API Lambda (`/api/state` & `/api/chat`).

## Usage

```hcl
module "serenity_core" {
  source  = "e-serenity/serenity-ops/aws//modules/serenity-core"
  version = "~> 0.1"

  project_name          = "serenity-ops"
  environment           = "prod"
  region                = "eu-west-3"
  dashboard_allowed_ips = ["203.0.113.10/32"]
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
| <a name="input_dashboard_allowed_ips"></a> [dashboard_allowed_ips](#input\_dashboard_allowed_ips) | Allowed IPv4 or IPv6 addresses/CIDRs for the Web Dashboard via CloudFront Function (empty disables IP filtering) | `list(string)` | `[]` | no |
| <a name="input_dashboard_price_class"></a> [dashboard_price_class](#input\_dashboard_price_class) | CloudFront price class for the Web Dashboard (PriceClass_100, PriceClass_200, PriceClass_All) | `string` | `"PriceClass_100"` | no |
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
| <a name="output_dashboard_cloudfront_id"></a> [dashboard_cloudfront_id](#output\_dashboard_cloudfront_id) | CloudFront Distribution ID for the Web Dashboard |
| <a name="output_dashboard_s3_bucket_name"></a> [dashboard_s3_bucket_name](#output\_dashboard_s3_bucket_name) | Private S3 bucket name hosting the Web Dashboard |
| <a name="output_dashboard_url"></a> [dashboard_url](#output\_dashboard_url) | HTTPS URL of the Serenity-Ops Web Dashboard (CloudFront) |
| <a name="output_dynamodb_hub_table_arn"></a> [dynamodb_hub_table_arn](#output\_dynamodb_hub_table_arn) | Central DynamoDB Hub table ARN |
| <a name="output_dynamodb_hub_table_name"></a> [dynamodb_hub_table_name](#output\_dynamodb_hub_table_name) | Central DynamoDB Hub table name (serenity-ops-hub) |
<!-- END_TF_DOCS -->
