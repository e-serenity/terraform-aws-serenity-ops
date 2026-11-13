# Full Serenity-Ops Suite Example (`examples/full`)

Deploys the complete [Serenity-Ops](https://github.com/e-serenity/terraform-aws-serenity-ops/blob/main/README.md) platform via the root module (`enable_core = true`, `enable_bot = true`, `enable_ses = true`), connecting all modules through the central DynamoDB Hub table.

## What This Example Provisions

- **`serenity-core`:** Central DynamoDB Hub table (`enable_dynamodb_hub = true`) and CloudFront OAC + S3 + ARM64 Live API Lambda Web Console (`enable_dashboard = true`), restricted via `dashboard_allowed_ips` (update `["203.0.113.10/32"]` to your VPN or office CIDR before applying).
- **`serenity-bot`:** Self-contained VPC/ECS Graviton deployment with Slack Socket Mode, GitHub connector (`enable_github = true`), Secrets Manager placeholder (`bot_create_secrets = true`), and a sample `application_context` map for RCA grounding.
- **`serenity-ses`:** AWS SES v2 bounce/complaint feedback pipeline (`enable_ses = true`) using the shared SES IP pool (`ses_enable_dedicated_ip_pool = false`) and the scoped `serenity-agent-ses` IAM role (`ses_enable_agent = true`).

## Usage

```bash
cd examples/full
terraform init
terraform apply
```

> **Note:** Update `dashboard_allowed_ips` in [`main.tf`](https://github.com/e-serenity/terraform-aws-serenity-ops/blob/main/examples/full/main.tf) with your own IP/CIDR before running `terraform apply`. To reference the published Registry module directly from your own configuration, set `source = "e-serenity/serenity-ops/aws"` with `version = "~> 0.1"`.

After `terraform apply`, open the Web Console at `dashboard_url`, populate your Slack Socket Mode tokens in the created AWS Secrets Manager secret (see [`docs/slack-app.md`](https://github.com/e-serenity/terraform-aws-serenity-ops/blob/main/docs/slack-app.md)), and invite the bot to your alert channels.

## Requirements

| Name | Version |
|------|---------|
| terraform | `>= 1.10.0` |
| aws | `>= 6.0.0` |
| archive | `>= 2.4.0` |
| random | `>= 3.5.0` |

## Outputs

| Name | Description |
|------|-------------|
| `dynamodb_hub_table_name` | Central DynamoDB Hub table name |
| `dynamodb_hub_table_arn` | Central DynamoDB Hub table ARN |
| `dashboard_url` | HTTPS URL of the Serenity-Ops Web Dashboard (CloudFront) |
| `bot_ecs_cluster_arn` | ECS Managed Instances cluster ARN (when `enable_bot = true`) |
| `bot_vpc_id` | Bot VPC ID (when `enable_bot = true` and created/managed by serenity-bot) |
| `bot_ecr_repository_url` | Bot ECR Repository URL (when `enable_bot = true`) |
