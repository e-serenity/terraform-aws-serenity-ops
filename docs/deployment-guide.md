# 🧩 Modular Ecosystem & Terraform Deployment Guide

[← Back to Main README](../README.md)

---

## Table of Contents

- [Modular Ecosystem & Independent Deployment](#modular-ecosystem--independent-deployment)
- [Terraform Modules: Choose What You Need](#terraform-modules-choose-what-you-need)
  - [Option A: Deploy the Full Suite (`Core Hub + Bot + SES + Live Web Console`)](#option-a-deploy-the-full-suite-core-hub--bot--ses--live-web-console)
  - [Option B: Deploy `serenity-bot` Standalone (AI Reports on Slack Alerts)](#option-b-deploy-serenity-bot-standalone-ai-reports-on-slack-alerts)
  - [Option C: Deploy `serenity-ses` Standalone (SES v2 Protection, No AI)](#option-c-deploy-serenity-ses-standalone-ses-v2-protection-no-ai)

---

## Modular Ecosystem & Independent Deployment

The root module (`e-serenity/serenity-ops/aws`) composes the suite with `enable_core`, `enable_bot`, and `enable_ses` flags, and each submodule under `modules/` can also be deployed independently using Terraform Registry submodule syntax (`//modules/<name>`). When connected to `serenity-ops-hub`, modules register themselves in DynamoDB (`PK=SERENITY#MODULES`) and appear automatically in the Web Console:

| Terraform Module & Source Path | Role & Capabilities | Standalone Mode | Hub-Coupled Mode (`serenity-ops-hub`) |
| :--- | :--- | :---: | :---: |
| **[`modules/serenity-core`](../modules/serenity-core)**<br>`e-serenity/serenity-ops/aws//modules/serenity-core` | **Serverless Core Hub & Live Web Console ($0/hr idle)**: `serenity-ops-hub` DynamoDB table (native TTL), Private S3 + CloudFront OAC + Edge IPv4/IPv6 Filter + ARM64 Live API Lambda. | ✅ | ✅ *(Central Hub)* |
| **[`modules/serenity-bot`](../modules/serenity-bot)**<br>`e-serenity/serenity-ops/aws//modules/serenity-bot` | **AI Orchestrator (Bedrock & Slack)**: Real-time Alert RCA, Chatbot, opt-in integrations (`enable_gitlab`, `enable_datadog`...) and Human-in-the-Loop approval queue. Creates its own VPC, Endpoints & ECS Managed Instances cluster by default, or deploys onto an existing `cluster_arn` without creating a VPC. | ✅ *(Slack-only, no DynamoDB needed)* | ✅ *(Syncs Web Console + unlocks AI across modules)* |
| **[`modules/serenity-ses`](../modules/serenity-ses)**<br>`e-serenity/serenity-ops/aws//modules/serenity-ses` | **AWS SES v2 Governance**: Managed Dedicated IP Pool, Configuration Set, ARM64 Bounce/Complaint processor Lambda, and scoped `serenity-agent-ses` IAM role. | ✅ *(Pure SES protection)* | ✅ *(Hub telemetry + AI-assisted remediation)* |
| **`modules/serenity-cloudwatch`** *(Coming Soon)* | **CloudWatch Governance**: Scoped `serenity-agent-cw` IAM role and EventBridge alarm ingestion rules. | ✅ | ✅ |
| **`modules/serenity-finops`** *(Coming Soon)* | **Account-Wide FinOps Optimization**: Orphaned resource detection and automated rightsizing under human approval. | 🔜 | 🔜 |

Once `terraform apply` finishes on `serenity-core`, it outputs your live **`dashboard_url`** (`https://<id>.cloudfront.net`), connected to your `serenity-ops-hub` DynamoDB table.

---

## Terraform Modules: Choose What You Need

Ready-to-run templates are also available under [`examples/full`](../examples/full) and [`examples/bot`](../examples/bot).

### Option A: Deploy the Full Suite via Root Module (`Core Hub + Bot + SES + Live Web Console`)

```hcl
module "serenity_ops" {
  source  = "e-serenity/serenity-ops/aws"
  version = "~> 0.1"

  project_name          = "serenity-ops"
  environment           = "prod"
  region                = "eu-west-3"
  dashboard_allowed_ips = ["10.0.0.1/32"] # Your VPN / Office IPv4 or IPv6 CIDR ($0/mo via CloudFront Function)

  enable_core = true
  enable_bot  = true
  enable_ses  = true

  history_retention_days   = 90
  enable_datadog           = true
  enable_gitlab            = true
  gitlab_allowed_namespace = "my-org/"
}
```

### Option B: Deploy `serenity-bot` Standalone (AI Reports on Slack Alerts)

Already have an ECS cluster in your VPC? Pass `cluster_arn`, `capacity_provider_name`, and `subnet_ids`. `serenity-bot` deploys directly onto your existing cluster without creating a VPC, NAT Gateway, or VPC Endpoints (or leave `cluster_arn` empty to let `serenity-bot` provision its own VPC and ECS cluster automatically, as shown in [`examples/bot`](../examples/bot)):

```hcl
module "serenity_bot_existing_ecs" {
  source  = "e-serenity/serenity-ops/aws//modules/serenity-bot"
  version = "~> 0.1"

  application            = "serenity-bot"
  environment            = "prod"
  region                 = "eu-west-3"
  cluster_arn            = var.existing_ecs_cluster_arn
  capacity_provider_name = var.existing_capacity_provider
  subnet_ids             = var.existing_private_subnet_ids

  # Optional: couple to serenity-core Hub or leave empty ("") for Slack-only mode
  dynamodb_table_name = ""
  enable_gitlab       = true
}
```

### Option C: Deploy `serenity-ses` Standalone (SES v2 Protection, No AI)

```hcl
module "serenity_ses_standalone" {
  source  = "e-serenity/serenity-ops/aws//modules/serenity-ses"
  version = "~> 0.1"

  name_prefix           = "my-app-prod"
  environment           = "prod"
  enable_serenity_agent = false # SES v2 Dedicated IP Pool + Bounce/Complaint tracking
}
```
