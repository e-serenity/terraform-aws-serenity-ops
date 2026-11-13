# 🤖 Serenity-Bot (`modules/serenity-bot`)

**Autonomous RCA & Human-in-the-Loop AI Orchestrator for AWS, Powered by Bedrock & Slack Socket Mode.**

[![Terraform Module](https://img.shields.io/badge/Terraform_Registry-e--serenity%2Fserenity--ops%2Faws%2F%2Fmodules%2Fserenity--bot-7B42BC?style=flat-square&logo=terraform&logoColor=white)](https://registry.terraform.io/modules/e-serenity/serenity-ops/aws/latest/submodules/serenity-bot)
[![AWS Bedrock](https://img.shields.io/badge/AI-AWS_Bedrock_(Claude_Sonnet)-FF9900?style=flat-square&logo=amazon-web-services&logoColor=white)](https://aws.amazon.com/bedrock/)
[![Zero Inbound Ports](https://img.shields.io/badge/Network-Slack_Socket_Mode_(0_Inbound_Ports)-10B981?style=flat-square)](https://github.com/e-serenity/terraform-aws-serenity-ops/blob/main/modules/serenity-bot/ecs-service.tf)
[![Standalone or Hub](https://img.shields.io/badge/Mode-Self--Contained_VPC_&_ECS_%7C_BYO_ECS_Cluster-3B82F6?style=flat-square)](#deployment-modes)

[Key Capabilities](#key-capabilities) · [Security Model (2 Modes)](#security--iam-permission-model) · [Deployment Modes](#deployment-modes) · [Container Image: Default `:stable` vs Private AWS ECR](#container-image-default-stable-vs-private-aws-ecr-recommended-for-production) · [Inputs](#inputs) · [Outputs](#outputs)

`source = "e-serenity/serenity-ops/aws//modules/serenity-bot"`

## Key Capabilities

**Serenity-Bot** is the AI CloudSecOps & AIOps orchestrator of the **[Serenity-Ops](https://github.com/e-serenity/terraform-aws-serenity-ops)** suite. It runs as a private container on **AWS ECS (ARM64)** with no inbound ports exposed to the internet via **Slack Socket Mode**, and communicates privately with **AWS Bedrock**.

1. **Real-Time Alert Analysis (RCA):** Listens to your Slack alert channels (where invited) or EventBridge, correlates signals across AWS services (`CloudWatch Alarms/Metrics/Logs`, `ECS`, `RDS`, `CloudTrail`, `DynamoDB`, `Lambda`, plus custom MCP servers) as well as your opt-in integrations (`GitHub`, `GitLab`, `Datadog`, `Grafana`) and your Terraform `application_context` map, and posts an actionable Root Cause Analysis in-thread.
2. **Web & Slack Chatbot:** Answers infrastructure, log, and deployment questions in real time (*"Which alarms are currently firing?"*, *"Which GitLab commit caused the RDS latency spike?"*) via Slack or inside the `serenity-ops` Web Console.
3. **Human-in-the-Loop Remediation:** Proposes and executes write actions by assuming scoped sub-agent IAM roles (`serenity-agent-ses`, `serenity-agent-cw`) only after explicit human approval (`Approve` / `Reject`).
4. **Self-Contained by Default or Bring-Your-Own ECS Cluster:** By default (`cluster_arn = ""`), `serenity-bot` provisions its own dedicated VPC, NAT Gateway, S3 & Bedrock VPC Endpoints, and ARM64 ECS Managed Instances cluster (~$35–$40/mo). If you pass an existing `cluster_arn`, `serenity-bot` skips VPC and ECS cluster creation and deploys the service directly onto your existing infrastructure (~$4/mo compute).

## Security & IAM Permission Model

| Operating Mode | Permission Scope | Human Approval | Primary Use Cases |
| :--- | :--- | :---: | :--- |
| **Mode 1: Scoped Observability Read (`READ AUTO`)** | Least-privilege AWS observability policy (`cloudwatch:Describe*/GetMetric*`, `logs:FilterLogEvents/Get*/Describe*`, `ecs:Describe*/List*`, `rds:Describe*`, `cloudtrail:LookupEvents`, `dynamodb:DescribeTable/ListTables`, `lambda:GetFunctionConfiguration/ListFunctions` — no application payload reads; opt-in `enable_aws_readonly_access` / `additional_task_iam_policies`) + opt-in Terraform connectors (`GitLab`, `Datadog`...) | ❌ Not required (autonomous) | Automated Alert RCA (`CloudWatch`, `ECS`, `RDS`, `CloudTrail`, `DynamoDB`, `Lambda`), log/commit correlation, and Chatbot queries. |
| **Mode 2: Controlled Write (`WRITE ON APPROVAL`)** | `sts:AssumeRole` delegation to tag-scoped sub-agents (`ManagedBy=serenity-ops`) | ✅ **Mandatory** (`Approve` / `Reject` via Slack or Web) | Quarantining SES bounced addresses (`serenity-agent-ses`), creating tagged CloudWatch alarms (`serenity-agent-cw`) *(ECS service rollbacks on roadmap)*. |

## Deployment Modes

### Option 1: Default Mode (Creates VPC, Endpoints & ECS Cluster Automatically)

By default, no networking or ECS variables are required. `serenity-bot` provisions its own VPC, NAT Gateway, VPC Endpoints (S3 Gateway + Bedrock Runtime), and ARM64 ECS Managed Instances cluster, and pulls the pre-built `ghcr.io/e-serenity/serenity-bot:stable` image so the service starts on the first `terraform apply`:

```hcl
module "serenity_bot" {
  source  = "e-serenity/serenity-ops/aws//modules/serenity-bot"
  version = "~> 0.1"

  application        = "serenity-bot"
  environment        = "prod"
  region             = "eu-west-3"
  single_nat_gateway = true

  # Optional: couple to Serenity-Ops Hub (or leave empty "" for Slack-only mode)
  dynamodb_table_name    = module.serenity_core.dynamodb_hub_table_name
  history_retention_days = 90

  enable_gitlab          = true
  enable_datadog         = true

  # Custom application & architecture context for AI RCA grounding
  application_context = {
    organization_name = "My Company"
    services = [
      {
        name        = "order-api"
        tech_stack  = "Node.js / Express / Redis"
        repository  = "github.com/my-org/order-service"
        log_group   = "/aws/ecs/prod-order-api"
        criticality = "HIGH"
      }
    ]
  }
}
```

### Option 2: Bring-Your-Own ECS Cluster (No VPC Creation)

Already have an ECS cluster? Pass `cluster_arn`, `capacity_provider_name`, and `subnet_ids`. `serenity-bot` deploys directly onto your cluster without creating a VPC, NAT Gateway, VPC Endpoints, or ECS cluster:

```hcl
module "serenity_bot" {
  source  = "e-serenity/serenity-ops/aws//modules/serenity-bot"
  version = "~> 0.1"

  application            = "serenity-bot"
  environment            = "prod"
  region                 = "eu-west-3"
  cluster_arn            = var.ecs_cluster_arn
  capacity_provider_name = var.ecs_capacity_provider_name
  subnet_ids             = var.private_subnet_ids

  dynamodb_table_name    = module.serenity_core.dynamodb_hub_table_name
}
```

## LLM Configuration & Resilient Fallback (AWS Bedrock & Gemini)

Serenity-Bot uses a resilient multi-provider LLM architecture:

### 1. Primary Engine: AWS Bedrock (Anthropic Claude)
By default, the bot communicates privately with **AWS Bedrock** via VPC Endpoints (`enable_bedrock_endpoint = true`) with zero outbound internet transit.

> **Important:**
> **Anthropic Claude on AWS Bedrock (One-Time Use Case Form):**
> Serverless foundation models are now automatically enabled across all AWS commercial regions upon first invocation—the legacy "Model access" page has been retired by AWS. 
> However, for **Anthropic models**, first-time users must submit their company & use case details in the **Amazon Bedrock Console** before access is completed, as required for AWS Marketplace subscription validation.

### 2. Optional Resilient Fallback: Google Gemini API (Disabled by Default)
To prevent downtime when AWS Bedrock access is pending, rate-limited, or undergoing maintenance, Serenity-Bot supports an optional fallback (disabled by default when `GEMINI_APIKEY` is left empty):
* Store your Gemini API key in `GEMINI_APIKEY` inside AWS Secrets Manager (either in the secret created by `create_secrets = true` or in your own secret passed via `existing_secret_arn`). ⚠️ *Note: Enabling this fallback sends prompts to the Google Gemini API outside your AWS account.*
* When configured, the orchestrator automatically routes RCA investigations and chat requests to **Google Gemini** (`gemini-3.5-flash` / `gemini-3.8-flash` / `gemini-3.1-flash-lite`) if Bedrock fails.
* Additional fallback and alternate providers (e.g., OpenAI, Mistral) are planned for future releases.

## Container Image: Default `:stable` vs Private AWS ECR (Recommended for Production)

### 1. Default Behavior (`create_ecr_repository = false`): Quick Evaluation
To let you test `serenity-bot` in a single `terraform apply` without building an ARM64 Docker image first, `image` defaults to our pre-built image:
```hcl
image = "ghcr.io/e-serenity/serenity-bot:stable"
```
> **Note:**
> While convenient for evaluation and quickstarts, pulling from an external registry (`ghcr.io`) introduces an external dependency during ECS task launches or restarts.

### 2. Production Best Practice (`create_ecr_repository = true`): Self-Hosted in AWS ECR
For production environments, we recommend hosting the container image inside your own AWS account via **Amazon ECR** so your infrastructure has no external registry dependency:

1. **Enable the private ECR repository in Terraform:**
   ```hcl
   module "serenity_bot" {
     source  = "e-serenity/serenity-ops/aws//modules/serenity-bot"
     version = "~> 0.1"

     application           = "serenity-bot"
     environment           = "prod"
     region                = "eu-west-3"
     create_ecr_repository = true # Creates aws_ecr_repository.this and configures ECS to pull <ecr_url>:prod
     ecr_image_tag         = "prod"
     # ...
   }
   ```
2. **Apply Terraform (or target the ECR repository first):**
   ```bash
   terraform apply -target=module.serenity_bot.aws_ecr_repository.this
   ```
3. **Build the `linux/arm64` image from [`modules/serenity-bot/bot`](https://github.com/e-serenity/terraform-aws-serenity-ops/tree/main/modules/serenity-bot/bot) and push it to your ECR repository:**
   *(Works natively on Apple Silicon Macs, or on Linux/Windows x86_64 via `docker buildx`)*
   ```bash
   AWS_REGION="eu-west-3"
   ECR_URL=$(terraform output -raw bot_ecr_repository_url) # e.g. <account_id>.dkr.ecr.eu-west-3.amazonaws.com/serenity-bot

   # Authenticate Docker to your private AWS ECR registry
   aws ecr get-login-password --region "$AWS_REGION" | \
     docker login --username AWS --password-stdin "$ECR_URL"

   # Cross-compile for AWS Graviton (linux/arm64) and push directly to ECR
   docker buildx build \
     --platform linux/arm64 \
     --push \
     -t "${ECR_URL}:prod" \
     ./modules/serenity-bot/bot
   ```
4. **Run the full `terraform apply`** (or force a new ECS deployment if already applied):
   ```bash
   terraform apply
   ```

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.10.0 |
| <a name="requirement_archive"></a> [archive](#requirement\_archive) | >= 2.4.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 6.0.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_archive"></a> [archive](#provider\_archive) | >= 2.4.0 |
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 6.0.0 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_ecs_service"></a> [ecs_service](#module\_ecs_service) | terraform-aws-modules/ecs/aws//modules/service | 6.10.0 |
| <a name="module_secrets_manager"></a> [secrets_manager](#module\_secrets_manager) | terraform-aws-modules/secrets-manager/aws | 1.3.1 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_additional_task_iam_policies"></a> [additional\_task\_iam\_policies](#input\_additional\_task\_iam\_policies) | Optional map of additional IAM policy ARNs (e.g., { CustomMCPRead = "arn:aws:iam::..." }) to attach to the Serenity-Bot ECS task role | `map(string)` | `{}` | no |
| <a name="input_application"></a> [application](#input\_application) | Application and ECS service name (e.g., serenity-bot) | `string` | `"serenity-bot"` | no |
| <a name="input_application_context"></a> [application_context](#input\_application_context) | Custom business and technical context about your workloads (services, tech stacks, repositories, log groups, criticality, runbooks). Injected into the AI prompt to ground RCA and investigations. | `object({...})` | `{}` | no |
| <a name="input_availability_zones"></a> [availability_zones](#input\_availability_zones) | List of Availability Zones. Defaults to <region>a, <region>b, <region>c when empty. | `list(string)` | `[]` | no |
| <a name="input_capacity_provider_name"></a> [capacity_provider_name](#input\_capacity_provider_name) | Name of the ECS Managed Instances capacity provider (required when cluster_arn is provided; defaults to <application>-<environment>-managed-instances when created). | `string` | `""` | no |
| <a name="input_cluster_arn"></a> [cluster_arn](#input\_cluster_arn) | Optional ARN of an existing ECS cluster. Leave empty ('') to automatically provision a dedicated ECS cluster and VPC. | `string` | `""` | no |
| <a name="input_cpu"></a> [cpu](#input\_cpu) | CPU units allocated to the ECS task (e.g., 1024 = 1 vCPU) | `number` | `1024` | no |
| <a name="input_create_ecr_repository"></a> [create_ecr_repository](#input\_create_ecr_repository) | When true, provisions a private AWS ECR repository in your account and configures ECS to pull '<ecr_repository_url>:<ecr_image_tag>' instead of the external 'image' (recommended for production to avoid external registry dependencies). | `bool` | `false` | no |
| <a name="input_create_secrets"></a> [create_secrets](#input\_create_secrets) | When true, provisions a new AWS Secrets Manager secret for Serenity-Bot credentials. Set to false and provide 'existing_secret_arn' to bring your own secret without storing tokens in Terraform state. | `bool` | `true` | no |
| <a name="input_create_vpc"></a> [create_vpc](#input\_create_vpc) | When true (and cluster_arn is empty), creates a dedicated VPC, subnets, NAT Gateway(s), and VPC endpoints. | `bool` | `true` | no |
| <a name="input_dynamodb_table_name"></a> [dynamodb_table_name](#input\_dynamodb_table_name) | Optional: Name of the central Serenity-Ops DynamoDB Hub table (e.g., 'serenity-ops-hub'). Leave empty ('') to run serenity-bot in Standalone Slack-only mode. | `string` | `""` | no |
| <a name="input_ecr_image_tag"></a> [ecr_image_tag](#input\_ecr_image_tag) | Image tag pulled from the private ECR repository when create_ecr_repository = true (defaults to var.environment when empty) | `string` | `""` | no |
| <a name="input_ecs_allowed_instance_types"></a> [ecs_allowed_instance_types](#input\_ecs_allowed_instance_types) | Allowed EC2 instance types or families for ECS Managed Instances | `list(string)` | `["m8g.*", "m7g.*", "m6g.*", "m6a.*", "t4g.*"]` | no |
| <a name="input_ecs_burstable_performance"></a> [ecs_burstable_performance](#input\_ecs_burstable_performance) | Burstable instance policy (included, required, excluded) | `string` | `"included"` | no |
| <a name="input_ecs_cluster_name"></a> [ecs_cluster_name](#input\_ecs_cluster_name) | Custom ECS cluster name when created by this module (defaults to <application>-<environment>-cluster-managed) | `string` | `""` | no |
| <a name="input_ecs_container_insights"></a> [ecs_container_insights](#input\_ecs_container_insights) | ECS Container Insights mode (enhanced, enabled, or disabled) | `string` | `"enhanced"` | no |
| <a name="input_ecs_instance_min_memory_mib"></a> [ecs_instance_min_memory_mib](#input\_ecs_instance_min_memory_mib) | Minimum memory (in MiB) for ECS Managed Instances selection | `number` | `128` | no |
| <a name="input_ecs_instance_min_vcpu"></a> [ecs_instance_min_vcpu](#input\_ecs_instance_min_vcpu) | Minimum vCPU count for ECS Managed Instances selection | `number` | `1` | no |
| <a name="input_enable_aws_readonly_access"></a> [enable_aws_readonly_access](#input\_enable_aws_readonly_access) | Opt-in: Attach the broad AWS managed ReadOnlyAccess policy to the bot task role in addition to the default least-privilege observability policy (disabled by default to prevent reading application data such as S3 objects or DynamoDB items) | `bool` | `false` | no |
| <a name="input_enable_bedrock_endpoint"></a> [enable_bedrock_endpoint](#input\_enable_bedrock_endpoint) | Enable AWS Bedrock Runtime Interface VPC Endpoint (used when cluster_arn is empty) | `bool` | `true` | no |
| <a name="input_enable_datadog"></a> [enable_datadog](#input\_enable_datadog) | Enable Datadog integration (Monitors, Logs, APM, Events via MCP / OTLP) | `bool` | `false` | no |
| <a name="input_enable_github"></a> [enable_github](#input\_enable_github) | Enable GitHub integration (Pull Requests, Actions, Commits) | `bool` | `false` | no |
| <a name="input_enable_gitlab"></a> [enable_gitlab](#input\_enable_gitlab) | Enable GitLab integration (Commits, Merge Requests, CI/CD Pipelines, Code Search) | `bool` | `false` | no |
| <a name="input_enable_grafana"></a> [enable_grafana](#input\_enable_grafana) | Enable Grafana / Prometheus integration | `bool` | `false` | no |
| <a name="input_enable_nat_gateway"></a> [enable_nat_gateway](#input\_enable_nat_gateway) | Whether to provision NAT Gateway(s) for private subnets | `bool` | `true` | no |
| <a name="input_enable_pii_redaction"></a> [enable_pii_redaction](#input\_enable_pii_redaction) | Enable automatic scrubbing of secrets, API keys, and sensitive tokens across logs, prompts, and Slack outputs | `bool` | `true` | no |
| <a name="input_enable_platform_alarms"></a> [enable_platform_alarms](#input\_enable_platform_alarms) | When true, provisions a predefined suite of CloudWatch alarms to monitor the Serenity-Ops platform itself (ECS CPU/Memory, Bot Error Logs, and DynamoDB Hub errors). | `bool` | `false` | no |
| <a name="input_enable_s3_endpoint"></a> [enable_s3_endpoint](#input\_enable_s3_endpoint) | Enable S3 Gateway VPC Endpoint (free, used when cluster_arn is empty) | `bool` | `true` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | Deployment environment name (e.g., preprod, prod, dev) | `string` | `"preprod"` | no |
| <a name="input_existing_private_route_table_ids"></a> [existing_private_route_table_ids](#input\_existing_private_route_table_ids) | Existing private route table IDs for the S3 Gateway VPC Endpoint (optional when create_vpc = false) | `list(string)` | `[]` | no |
| <a name="input_existing_secret_arn"></a> [existing_secret_arn](#input\_existing_secret_arn) | ARN of an existing AWS Secrets Manager secret containing Serenity-Bot credentials (required when create_secrets = false). | `string` | `""` | no |
| <a name="input_existing_vpc_id"></a> [existing_vpc_id](#input\_existing_vpc_id) | Existing VPC ID (required when cluster_arn is empty and create_vpc = false) | `string` | `""` | no |
| <a name="input_gitlab_allowed_namespace"></a> [gitlab_allowed_namespace](#input\_gitlab_allowed_namespace) | Optional allowed GitLab group/namespace prefix (e.g., 'my-org/') | `string` | `""` | no |
| <a name="input_history_retention_days"></a> [history_retention_days](#input\_history_retention_days) | Retention period in days for incident history, chat messages, and audit records via native DynamoDB TTL | `number` | `90` | no |
| <a name="input_image"></a> [image](#input\_image) | Container image URI used when create_ecr_repository = false. Defaults to the official pre-built GHCR image (:stable) for instant zero-build testing. | `string` | `"ghcr.io/e-serenity/serenity-bot:stable"` | no |
| <a name="input_initial_secrets"></a> [initial_secrets](#input\_initial_secrets) | Optional initial secrets map to seed into AWS Secrets Manager when create_secrets = true (merged over defaults). Prefer populating secrets directly in AWS Secrets Manager or passing 'existing_secret_arn' in production to avoid storing tokens in Terraform state. | `map(string)` | `{}` | no |
| <a name="input_llm_fallback_model"></a> [llm_fallback_model](#input\_llm_fallback_model) | Fallback LLM model ID (defaults to 'gemini-3.5-flash' when llm_fallback_provider = 'gemini') | `string` | `"gemini-3.5-flash"` | no |
| <a name="input_llm_fallback_provider"></a> [llm_fallback_provider](#input\_llm_fallback_provider) | Fallback LLM provider invoked automatically when the primary provider is throttled or unavailable ('gemini', 'bedrock', 'anthropic', or 'openai') | `string` | `"gemini"` | no |
| <a name="input_llm_primary_model"></a> [llm_primary_model](#input\_llm_primary_model) | Optional override for the primary LLM model ID. When empty (''), defaults to the CLAUDE_MODEL secret in AWS Secrets Manager. | `string` | `""` | no |
| <a name="input_llm_primary_provider"></a> [llm_primary_provider](#input\_llm_primary_provider) | Primary LLM provider for the orchestrator ('bedrock', 'gemini', 'anthropic', or 'openai') | `string` | `"bedrock"` | no |
| <a name="input_max_token_budget"></a> [max_token_budget](#input\_max_token_budget) | Maximum total token budget (input + output) per incident investigation before triggering a graceful circuit breaker | `number` | `32000` | no |
| <a name="input_max_tool_iterations"></a> [max_tool_iterations](#input\_max_tool_iterations) | Maximum number of LLM reasoning/tool steps per investigation session | `number` | `12` | no |
| <a name="input_memory"></a> [memory](#input\_memory) | Memory in MiB allocated to the ECS task (e.g., 1024 = 1 GiB) | `number` | `1024` | no |
| <a name="input_platform_alarms_cpu_threshold"></a> [platform_alarms_cpu_threshold](#input\_platform_alarms_cpu_threshold) | CPU utilization threshold percentage triggering the Serenity-Bot ECS high CPU CloudWatch alarm | `number` | `85` | no |
| <a name="input_platform_alarms_error_log_threshold"></a> [platform_alarms_error_log_threshold](#input\_platform_alarms_error_log_threshold) | Number of ERROR/CRITICAL/Exception log events in 1 minute triggering the bot error log alarm | `number` | `5` | no |
| <a name="input_platform_alarms_memory_threshold"></a> [platform_alarms_memory_threshold](#input\_platform_alarms_memory_threshold) | Memory utilization threshold percentage triggering the Serenity-Bot ECS high Memory CloudWatch alarm | `number` | `85` | no |
| <a name="input_platform_alert_slack_channel"></a> [platform_alert_slack_channel](#input\_platform_alert_slack_channel) | Optional dedicated Slack channel name (e.g., '#cloudsecops' or '#serenity-alerts') where platform CloudWatch alarms are forwarded. Automatically added to bot monitored channels for automated RCA. | `string` | `""` | no |
| <a name="input_private_subnet_cidrs"></a> [private_subnet_cidrs](#input\_private_subnet_cidrs) | Private subnet CIDR blocks for ECS workloads (used when create_vpc = true and cluster_arn is empty) | `list(string)` | `["10.0.10.0/24", "10.0.11.0/24", "10.0.12.0/24"]` | no |
| <a name="input_public_subnet_cidrs"></a> [public_subnet_cidrs](#input\_public_subnet_cidrs) | Public subnet CIDR blocks (used when create_vpc = true and cluster_arn is empty) | `list(string)` | `["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]` | no |
| <a name="input_region"></a> [region](#input\_region) | Primary AWS region | `string` | `"eu-west-3"` | no |
| <a name="input_region_backup"></a> [region_backup](#input\_region_backup) | Optional replica region for AWS Secrets Manager | `string` | `""` | no |
| <a name="input_single_nat_gateway"></a> [single_nat_gateway](#input\_single_nat_gateway) | When true, provisions a single shared NAT Gateway across all AZs. When false, provisions one NAT Gateway per public subnet. | `bool` | `false` | no |
| <a name="input_subnet_ids"></a> [subnet_ids](#input\_subnet_ids) | Existing private subnet IDs for ECS tasks (required when cluster_arn is provided or when create_vpc = false). | `list(string)` | `[]` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Common tags applied to all created resources | `map(string)` | `{}` | no |
| <a name="input_vpc_cidr"></a> [vpc_cidr](#input\_vpc_cidr) | CIDR block for the created VPC (used when create_vpc = true and cluster_arn is empty) | `string` | `"10.0.0.0/16"` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_ecr_repository_url"></a> [ecr_repository_url](#output\_ecr_repository_url) | URL of the AWS ECR repository for the bot container image (null when a custom image URI is provided) |
| <a name="output_ecs_capacity_provider_name"></a> [ecs_capacity_provider_name](#output\_ecs_capacity_provider_name) | Effective ECS Managed Instances capacity provider name (created or provided) |
| <a name="output_ecs_cluster_arn"></a> [ecs_cluster_arn](#output\_ecs_cluster_arn) | Effective ECS cluster ARN (created or provided) |
| <a name="output_ecs_cluster_id"></a> [ecs_cluster_id](#output\_ecs_cluster_id) | ECS Managed Instances cluster ID (when created by serenity-bot) |
| <a name="output_ecs_cluster_name"></a> [ecs_cluster_name](#output\_ecs_cluster_name) | ECS Managed Instances cluster name (when created by serenity-bot) |
| <a name="output_platform_alarms_cloudwatch_alarm_arns"></a> [platform_alarms_cloudwatch_alarm_arns](#output\_platform_alarms_cloudwatch_alarm_arns) | List of ARNs of created CloudWatch alarms monitoring the Serenity-Ops platform |
| <a name="output_platform_alarms_sns_topic_arn"></a> [platform_alarms_sns_topic_arn](#output\_platform_alarms_sns_topic_arn) | ARN of the SNS topic receiving platform self-monitoring CloudWatch alarms (null when enable_platform_alarms = false) |
| <a name="output_private_subnet_ids"></a> [private_subnet_ids](#output\_private_subnet_ids) | Private subnet IDs used by the ECS tasks |
| <a name="output_public_subnet_ids"></a> [public_subnet_ids](#output\_public_subnet_ids) | Created public subnet IDs (empty when using an existing VPC or external cluster_arn) |
| <a name="output_secrets_manager_secret_arn"></a> [secrets_manager_secret_arn](#output\_secrets_manager_secret_arn) | Effective ARN of the AWS Secrets Manager secret storing bot credentials (created or provided) |
| <a name="output_service_id"></a> [service_id](#output\_service_id) | ID of the deployed ECS service |
| <a name="output_service_name"></a> [service_name](#output\_service_name) | Name of the deployed ECS service |
| <a name="output_tasks_iam_role_arn"></a> [tasks_iam_role_arn](#output\_tasks_iam_role_arn) | ARN of the ECS task IAM role |
| <a name="output_vpc_id"></a> [vpc_id](#output\_vpc_id) | VPC ID (created or existing when ECS cluster is managed by serenity-bot; null when using an external cluster_arn) |
<!-- END_TF_DOCS -->

## Local Python Unit Tests (`bot/`)

```bash
cd bot && uv run pytest -q
```
