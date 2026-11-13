# Standalone Serenity-Bot Example (`examples/bot`)

Deploys [`modules/serenity-bot`](https://github.com/e-serenity/terraform-aws-serenity-ops/blob/main/modules/serenity-bot/README.md) in **standalone Slack-only mode** (`dynamodb_table_name = ""`), without deploying `serenity-core` (no DynamoDB Hub or CloudFront Web Console).

## What This Example Provisions

- **Self-contained Networking:** Dedicated VPC (`10.10.0.0/16`), single NAT Gateway (`single_nat_gateway = true`), and S3 + Bedrock Runtime VPC Endpoints (`enable_s3_endpoint = true`, `enable_bedrock_endpoint = true`).
- **ECS Graviton (ARM64) Service:** Managed ECS cluster and `serenity-bot` service running Slack Socket Mode (zero inbound ports) with least-privilege AWS observability IAM permissions.
- **Secrets Manager Placeholder:** Creates an AWS Secrets Manager secret (`create_secrets = true`) where you populate your Slack (`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`) and optional integration tokens after apply.
- **Integrations:** GitHub enabled (`enable_github = true`), GitLab / Datadog / Grafana disabled by default.

## Usage

```bash
cd examples/bot
terraform init
terraform apply
```

> **Note:** To reference the published Registry module directly from your own configuration instead of cloning this repository, set `source = "e-serenity/serenity-ops/aws//modules/serenity-bot"` with `version = "~> 0.1"`.

After `terraform apply`, populate your Slack Socket Mode tokens in the secret returned by `bot_secrets_manager_secret_arn` (see [`docs/slack-app.md`](https://github.com/e-serenity/terraform-aws-serenity-ops/blob/main/docs/slack-app.md)), then invite the bot to your alert channels.

## Requirements

| Name | Version |
|------|---------|
| terraform | `>= 1.10.0` |
| aws | `>= 6.0.0` |
| archive | `>= 2.4.0` |

## Outputs

| Name | Description |
|------|-------------|
| `bot_service_name` | Name of the deployed Serenity-Bot ECS service |
| `bot_ecs_cluster_arn` | ECS Managed Instances cluster ARN |
| `bot_vpc_id` | Bot VPC ID (when created or managed by serenity-bot) |
| `bot_secrets_manager_secret_arn` | ARN of the AWS Secrets Manager secret storing bot credentials |
| `bot_tasks_iam_role_arn` | ARN of the Serenity-Bot ECS task IAM role |
| `bot_ecr_repository_url` | Bot ECR Repository URL (when `create_ecr_repository = true`) |
