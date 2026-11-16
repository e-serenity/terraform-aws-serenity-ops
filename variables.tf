# ------------------------------------------------------------------------------
# Global & Module Composition
# ------------------------------------------------------------------------------

variable "create" {
  description = "Controls whether resources should be created (affects nearly all resources)"
  type        = bool
  default     = true
}

variable "enable_core" {
  description = "Enable the Serenity-Core serverless Hub (DynamoDB Single-Table Hub + CloudFront Web Console + Live API Lambda)"
  type        = bool
  default     = true
}

variable "enable_bot" {
  description = "Enable the Serenity-Bot AI orchestrator (Slack Socket Mode + AWS Bedrock + MCP sub-agents)"
  type        = bool
  default     = true
}

variable "enable_ses" {
  description = "Enable the Serenity-SES governance module (SES v2 Configuration Set, Bounce/Complaint processor, and scoped serenity-agent-ses role)"
  type        = bool
  default     = false
}

variable "project_name" {
  description = "Project name and resource prefix (e.g., serenity-ops)"
  type        = string
  default     = "serenity-ops"
}

variable "environment" {
  description = "Deployment environment name (e.g., dev, preprod, prod)"
  type        = string
  default     = "preprod"
}

variable "region" {
  description = "Target AWS region"
  type        = string
  default     = "eu-west-3"
}

variable "tags" {
  description = "Additional tags applied to all created resources"
  type        = map(string)
  default     = {}
}

variable "dynamodb_table_name" {
  description = "Optional existing Serenity-Ops DynamoDB Hub table name when enable_core = false or enable_dynamodb_hub = false (leave empty '' for standalone mode)"
  type        = string
  default     = ""
}

# ------------------------------------------------------------------------------
# Serenity-Core (DynamoDB Hub & Web Dashboard)
# ------------------------------------------------------------------------------

variable "enable_dynamodb_hub" {
  description = "Enable central DynamoDB Hub table (Single-Table Design for module discovery, state, and audit) when enable_core = true"
  type        = bool
  default     = true
}

variable "dynamodb_hub_table_name" {
  description = "Custom DynamoDB Hub table name (defaults to <project_name>-<environment>-hub)"
  type        = string
  default     = ""
}

variable "dynamodb_enable_pitr" {
  description = "Enable Point-in-Time Recovery (PITR) on the DynamoDB Hub table"
  type        = bool
  default     = false
}

variable "enable_dashboard" {
  description = "Enable Serenity-Ops Web Dashboard (Private S3 + CloudFront OAC + Live API Lambda) when enable_core = true"
  type        = bool
  default     = true
}

variable "dashboard_allowed_ips" {
  description = "Allowed IPv4 or IPv6 addresses/CIDRs for the Web Dashboard via CloudFront Function (empty disables IP filtering)"
  type        = list(string)
  default     = []
}

variable "dashboard_price_class" {
  description = "CloudFront price class for the Web Dashboard (PriceClass_100, PriceClass_200, PriceClass_All)"
  type        = string
  default     = "PriceClass_100"
}

variable "dashboard_s3_force_destroy" {
  description = "Whether to allow force-destroying the S3 bucket hosting the Web Dashboard even when non-empty (defaults to false for production safety)"
  type        = bool
  default     = false
}

# ------------------------------------------------------------------------------
# Serenity-Bot (ECS, Networking & Secrets)
# ------------------------------------------------------------------------------

variable "bot_application" {
  description = "Application and ECS service name for Serenity-Bot"
  type        = string
  default     = "serenity-bot"
}

variable "bot_region_backup" {
  description = "Optional replica region for Serenity-Bot AWS Secrets Manager secret"
  type        = string
  default     = ""
}

variable "bot_create_secrets" {
  description = "When true, provisions an AWS Secrets Manager secret for Serenity-Bot credentials. Set to false and pass 'bot_existing_secret_arn' to bring your own secret without storing tokens in Terraform state."
  type        = bool
  default     = true
}

variable "bot_existing_secret_arn" {
  description = "ARN of an existing AWS Secrets Manager secret containing Serenity-Bot credentials (required when bot_create_secrets = false and enable_bot = true)"
  type        = string
  default     = ""

  validation {
    condition     = !var.create || !var.enable_bot || var.bot_create_secrets || length(trimspace(var.bot_existing_secret_arn)) > 0
    error_message = "'bot_existing_secret_arn' is required when 'bot_create_secrets' is false and 'enable_bot = true'."
  }
}

variable "bot_initial_secrets" {
  description = "Optional initial secrets map to seed into AWS Secrets Manager when bot_create_secrets = true (merged over defaults). Prefer populating secrets directly in AWS Secrets Manager or passing 'bot_existing_secret_arn' in production to avoid storing tokens in Terraform state."
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "bot_image" {
  description = "Container image URI used when bot_create_ecr_repository = false. Defaults to the pinned SemVer GHCR release image (:0.1.2)."
  type        = string
  default     = "ghcr.io/e-serenity/serenity-bot:0.1.2"
}

variable "bot_create_ecr_repository" {
  description = "When true, provisions a private AWS ECR repository and configures ECS to pull '<ecr_repository_url>:<bot_ecr_image_tag>' instead of bot_image"
  type        = bool
  default     = false
}

variable "bot_ecr_image_tag" {
  description = "Image tag pulled from the private ECR repository when bot_create_ecr_repository = true (defaults to var.environment when empty)"
  type        = string
  default     = ""
}

variable "bot_ecr_image_tag_mutability" {
  description = "Tag mutability setting for the private ECR repository ('IMMUTABLE' or 'MUTABLE'). Defaults to 'IMMUTABLE' to prevent image tag tampering."
  type        = string
  default     = "IMMUTABLE"
}

variable "bot_ecr_force_delete" {
  description = "Whether to allow deleting the private ECR repository even when it contains images (defaults to false for production safety)"
  type        = bool
  default     = false
}

variable "bot_enable_execute_command" {
  description = "Whether to enable Amazon ECS Exec on the Serenity-Bot task (defaults to false for least-privilege container hardening)"
  type        = bool
  default     = false
}

variable "bot_readonly_root_filesystem" {
  description = "Whether to mount the container root filesystem as read-only (defaults to true with a /tmp tmpfs mount)"
  type        = bool
  default     = true
}

variable "bot_cpu" {
  description = "CPU units allocated to the Serenity-Bot ECS task (e.g., 1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "bot_memory" {
  description = "Memory in MiB allocated to the Serenity-Bot ECS task (e.g., 1024 = 1 GiB)"
  type        = number
  default     = 1024
}

variable "cluster_arn" {
  description = "Optional ARN of an existing ECS cluster for Serenity-Bot. Leave empty ('') to automatically provision a dedicated ECS cluster and VPC."
  type        = string
  default     = ""
}

variable "capacity_provider_name" {
  description = "Name of the ECS Managed Instances capacity provider (required when cluster_arn is provided)"
  type        = string
  default     = ""

  validation {
    condition     = !var.create || !var.enable_bot || trimspace(var.cluster_arn) == "" || length(trimspace(var.capacity_provider_name)) > 0
    error_message = "'capacity_provider_name' is required when an existing 'cluster_arn' is provided and 'enable_bot = true'."
  }
}

variable "subnet_ids" {
  description = "Existing private subnet IDs for Serenity-Bot ECS tasks (required when cluster_arn is provided or when create_vpc = false)"
  type        = list(string)
  default     = []

  validation {
    condition     = !var.create || !var.enable_bot || (trimspace(var.cluster_arn) == "" && var.create_vpc) || length(var.subnet_ids) > 0
    error_message = "At least one subnet in 'subnet_ids' is required when 'cluster_arn' is provided or 'create_vpc' is false and 'enable_bot = true'."
  }
}

variable "create_vpc" {
  description = "When true (and cluster_arn is empty), creates a dedicated VPC, subnets, NAT Gateway(s), and VPC endpoints for Serenity-Bot"
  type        = bool
  default     = true
}

variable "vpc_cidr" {
  description = "CIDR block for the created VPC (used when create_vpc = true and cluster_arn is empty)"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of Availability Zones. Defaults to <region>a, <region>b, <region>c when empty."
  type        = list(string)
  default     = []
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks (used when create_vpc = true and cluster_arn is empty)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDR blocks for ECS workloads (used when create_vpc = true and cluster_arn is empty)"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24", "10.0.12.0/24"]
}

variable "enable_nat_gateway" {
  description = "Whether to provision NAT Gateway(s) for private subnets"
  type        = bool
  default     = true
}

variable "single_nat_gateway" {
  description = "When true (default for cost efficiency), provisions a single shared NAT Gateway across all AZs (~$32/mo instead of ~$96/mo). Set to false for multi-AZ NAT high availability."
  type        = bool
  default     = true
}

variable "existing_vpc_id" {
  description = "Existing VPC ID (required when cluster_arn is empty and create_vpc = false)"
  type        = string
  default     = ""

  validation {
    condition     = !var.create || !var.enable_bot || trimspace(var.cluster_arn) != "" || var.create_vpc || length(trimspace(var.existing_vpc_id)) > 0
    error_message = "'existing_vpc_id' is required when 'cluster_arn' is empty, 'create_vpc' is false, and 'enable_bot = true'."
  }
}

variable "existing_private_route_table_ids" {
  description = "Existing private route table IDs for the S3 Gateway VPC Endpoint (optional when create_vpc = false)"
  type        = list(string)
  default     = []
}

variable "enable_s3_endpoint" {
  description = "Enable S3 Gateway VPC Endpoint (free, used when cluster_arn is empty)"
  type        = bool
  default     = true
}

variable "enable_bedrock_endpoint" {
  description = "Enable AWS Bedrock Runtime Interface VPC Endpoint (~$7.20/mo per AZ, used when cluster_arn is empty). Disabled by default to minimize idle costs when NAT Gateway is enabled."
  type        = bool
  default     = false
}

variable "ecs_cluster_name" {
  description = "Custom ECS cluster name when created by Serenity-Bot (defaults to <bot_application>-<environment>-cluster-managed)"
  type        = string
  default     = ""
}

variable "ecs_container_insights" {
  description = "ECS Container Insights mode (enhanced, enabled, or disabled). Defaults to 'enabled' to avoid extra per-metric Enhanced Container Insights charges."
  type        = string
  default     = "enabled"
}

variable "ecs_allowed_instance_types" {
  description = "Allowed EC2 instance types or families for ECS Managed Instances"
  type        = list(string)
  default     = ["m8g.*", "m7g.*", "m6g.*", "m6a.*", "t4g.*"]
}

variable "ecs_instance_min_vcpu" {
  description = "Minimum vCPU count for ECS Managed Instances selection"
  type        = number
  default     = 1
}

variable "ecs_instance_min_memory_mib" {
  description = "Minimum memory (in MiB) for ECS Managed Instances selection"
  type        = number
  default     = 128
}

variable "ecs_burstable_performance" {
  description = "Burstable instance policy (included, required, excluded)"
  type        = string
  default     = "included"
}

# ------------------------------------------------------------------------------
# Serenity-Bot (Integrations, LLM Routing & Platform Self-Monitoring)
# ------------------------------------------------------------------------------

variable "enable_datadog" {
  description = "Enable Datadog integration (Monitors, Logs, APM, Events)"
  type        = bool
  default     = false
}

variable "enable_gitlab" {
  description = "Enable GitLab integration (Commits, Merge Requests, CI/CD Pipelines, Code Search)"
  type        = bool
  default     = false
}

variable "gitlab_allowed_namespace" {
  description = "Optional allowed GitLab group/namespace prefix (e.g., 'my-org/')"
  type        = string
  default     = ""
}

variable "enable_github" {
  description = "Enable GitHub integration (Pull Requests, Actions, Commits)"
  type        = bool
  default     = false
}

variable "enable_grafana" {
  description = "Enable Grafana / Prometheus integration"
  type        = bool
  default     = false
}

variable "history_retention_days" {
  description = "Retention period in days for incident history, chat messages, and audit records via native DynamoDB TTL"
  type        = number
  default     = 90
}

variable "llm_primary_provider" {
  description = "Primary LLM provider for the orchestrator ('bedrock', 'gemini', 'anthropic', or 'openai')"
  type        = string
  default     = "bedrock"
}

variable "llm_primary_model" {
  description = "Optional override for the primary LLM model ID. When empty (''), defaults to the CLAUDE_MODEL secret in AWS Secrets Manager ('global.anthropic.claude-sonnet-5-5' by default; can be set to regional inference profiles such as 'us.anthropic.claude-sonnet-5-5' to keep data within US/Canada regions or 'eu.anthropic.claude-sonnet-5-5' to keep data within EU regions)."
  type        = string
  default     = ""
}

variable "llm_fallback_provider" {
  description = "Optional fallback LLM provider invoked automatically when the primary provider is throttled or unavailable ('none', 'bedrock', 'openai', 'gemini', or 'anthropic'). Defaults to 'none' to prevent routing prompts outside your primary provider unless explicitly configured."
  type        = string
  default     = "none"
}

variable "llm_fallback_model" {
  description = "Optional fallback LLM model ID (e.g., 'global.openai.gpt-6.1-sol', 'eu.anthropic.claude-sonnet-5-5', or 'gemini-3.5-flash'). Defaults to '' when llm_fallback_provider = 'none'."
  type        = string
  default     = ""
}

variable "max_token_budget" {
  description = "Maximum total token budget (input + output) per incident investigation before triggering a graceful circuit breaker"
  type        = number
  default     = 32000
}

variable "max_tool_iterations" {
  description = "Maximum number of LLM reasoning/tool steps per investigation session"
  type        = number
  default     = 12
}

variable "enable_pii_redaction" {
  description = "Enable automatic scrubbing of secrets, API keys, and sensitive tokens across logs, prompts, and Slack outputs"
  type        = bool
  default     = true
}

variable "bot_enable_aws_readonly_access" {
  description = "Opt-in: Attach the broad AWS managed ReadOnlyAccess policy to the Serenity-Bot task role in addition to the default least-privilege observability policy"
  type        = bool
  default     = false
}

variable "bot_additional_task_iam_policies" {
  description = "Optional map of additional IAM policy ARNs (e.g., { CustomMCPRead = \"arn:aws:iam::...\" }) to attach to the Serenity-Bot ECS task role"
  type        = map(string)
  default     = {}
}

variable "enable_platform_alarms" {
  description = "When true, provisions a predefined suite of CloudWatch alarms to monitor the Serenity-Ops platform itself (ECS CPU/Memory, Bot Error Logs, and DynamoDB Hub errors)"
  type        = bool
  default     = false
}

variable "platform_alert_slack_channel" {
  description = "Optional dedicated Slack channel name (e.g., '#cloudsecops') where platform CloudWatch alarms are forwarded and ingested for automated RCA"
  type        = string
  default     = ""
}

variable "platform_alarms_cpu_threshold" {
  description = "CPU utilization threshold percentage triggering the Serenity-Bot ECS high CPU CloudWatch alarm"
  type        = number
  default     = 85
}

variable "platform_alarms_memory_threshold" {
  description = "Memory utilization threshold percentage triggering the Serenity-Bot ECS high Memory CloudWatch alarm"
  type        = number
  default     = 85
}

variable "platform_alarms_error_log_threshold" {
  description = "Number of ERROR/CRITICAL/Exception log events in 1 minute triggering the bot error log alarm"
  type        = number
  default     = 5
}

variable "application_context" {
  description = "Custom business and technical context about your workloads (services, tech stacks, repositories, log groups, criticality, runbooks). Injected into the AI prompt to ground RCA and investigations."
  type = object({
    organization_name    = optional(string, "")
    business_domain      = optional(string, "")
    architecture_summary = optional(string, "")
    services = optional(list(object({
      name        = string
      description = optional(string, "")
      tech_stack  = optional(string, "")
      repository  = optional(string, "")
      log_group   = optional(string, "")
      criticality = optional(string, "MEDIUM")
    })), [])
    runbooks    = optional(map(string), {})
    extra_notes = optional(string, "")
  })
  default = {}
}

# ------------------------------------------------------------------------------
# Serenity-SES
# ------------------------------------------------------------------------------

variable "ses_name_prefix" {
  description = "Prefix applied to all created AWS SES, SNS, SQS, and Lambda resources (defaults to <project_name>-<environment>)"
  type        = string
  default     = ""
}

variable "ses_enable_agent" {
  description = "Whether to provision the scoped IAM role serenity-agent-ses when enable_ses = true"
  type        = bool
  default     = true
}

variable "ses_enable_dedicated_ip_pool" {
  description = "Whether to provision an AWS SES v2 Managed Dedicated IP Pool when enable_ses = true (disabled by default to avoid monthly AWS dedicated IP charges; set to true when dedicated IPs are required)"
  type        = bool
  default     = false
}

# ------------------------------------------------------------------------------
# Serenity-Bot (Slack Access Control — Channel & User Allowlists)
# ------------------------------------------------------------------------------

variable "slack_allowed_channel_ids" {
  description = "Optional list of allowed Slack channel IDs (e.g., ['C0123456789']) where Serenity-Bot is permitted to respond to mentions and alerts. When non-empty, messages in other channels are ignored."
  type        = list(string)
  default     = []
}

variable "slack_allowed_user_ids" {
  description = "Optional list of allowed Slack user IDs (e.g., ['U0123456789']) permitted to interact with Serenity-Bot (DMs, mentions, and HITL approvals). When non-empty, unauthorized users are rejected."
  type        = list(string)
  default     = []
}

variable "slack_allow_direct_messages" {
  description = "Whether Serenity-Bot responds to 1-on-1 Direct Messages (IM). When slack_allowed_user_ids is set, only listed users can DM the bot."
  type        = bool
  default     = true
}
