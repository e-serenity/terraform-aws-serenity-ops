locals {
  base_secrets = [
    { name = "CLAUDE_MODEL", valueFrom = "${local.secret_arn}:CLAUDE_MODEL::" },
    { name = "GEMINI_APIKEY", valueFrom = "${local.secret_arn}:GEMINI_APIKEY::" },
    { name = "SLACK_BOT_TOKEN", valueFrom = "${local.secret_arn}:SLACK_BOT_TOKEN::" },
    { name = "SLACK_APP_TOKEN", valueFrom = "${local.secret_arn}:SLACK_APP_TOKEN::" },
    { name = "MCP_SERVERS_CONFIG", valueFrom = "${local.secret_arn}:MCP_SERVERS_CONFIG::" },
  ]

  datadog_secrets = var.enable_datadog ? [
    { name = "DATADOG_API_KEY", valueFrom = "${local.secret_arn}:DATADOG_API_KEY::" },
    { name = "DATADOG_APP_KEY", valueFrom = "${local.secret_arn}:DATADOG_APP_KEY::" },
  ] : []

  gitlab_secrets = var.enable_gitlab ? [
    { name = "GITLAB_TOKEN", valueFrom = "${local.secret_arn}:GITLAB_TOKEN::" },
  ] : []

  github_secrets = var.enable_github ? [
    { name = "GITHUB_TOKEN", valueFrom = "${local.secret_arn}:GITHUB_TOKEN::" },
  ] : []
}

module "ecs_service" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "6.10.0"

  depends_on = [
    aws_ecs_cluster_capacity_providers.this
  ]

  name           = "${var.environment}-${var.application}"
  cluster_arn    = local.effective_cluster_arn
  propagate_tags = "SERVICE"

  enable_execute_command = true

  cpu                      = var.cpu
  memory                   = var.memory
  desired_count            = 1
  requires_compatibilities = ["MANAGED_INSTANCES"]

  enable_autoscaling = false

  deployment_circuit_breaker = {
    enable   = true
    rollback = true
  }

  capacity_provider_strategy = {
    base = {
      capacity_provider = local.effective_capacity_provider_name
      weight            = 1
      base              = 1
    }
  }

  runtime_platform = {
    cpu_architecture = "ARM64"
  }

  subnet_ids = local.private_subnet_ids

  security_group_name = "${var.application}-${var.environment}-ecs-sg"
  security_group_egress_rules = {
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  container_definitions = {
    (var.application) = {
      essential = true
      image     = local.image

      enable_cloudwatch_logging = true
      cloudwatch_log_group_name = local.container_log_group_name
      memory_reservation        = 100
      readonlyRootFilesystem    = false
      stopTimeout               = 60 * 5

      environment = [
        { name = "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", value = "https://otlp.datadoghq.eu/v1/traces" },
        { name = "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", value = "http/protobuf" },
        { name = "DD_OTLP_SOURCE", value = "llmobs" },
        { name = "HEALTH_PORT", value = tostring(local.health_port) },
        { name = "ENVIRONMENT", value = var.environment },
        { name = "AWS_DEFAULT_REGION", value = var.region },
        { name = "DYNAMODB_TABLE_NAME", value = var.dynamodb_table_name },
        { name = "ENABLE_DATADOG", value = tostring(var.enable_datadog) },
        { name = "ENABLE_GITLAB", value = tostring(var.enable_gitlab) },
        { name = "GITLAB_ALLOWED_NAMESPACE", value = var.gitlab_allowed_namespace },
        { name = "ENABLE_GITHUB", value = tostring(var.enable_github) },
        { name = "ENABLE_GRAFANA", value = tostring(var.enable_grafana) },
        { name = "HISTORY_RETENTION_DAYS", value = tostring(var.history_retention_days) },
        { name = "APPLICATION_CONTEXT", value = jsonencode(var.application_context) },
        { name = "LLM_PRIMARY_PROVIDER", value = var.llm_primary_provider },
        { name = "LLM_PRIMARY_MODEL", value = var.llm_primary_model },
        { name = "LLM_FALLBACK_PROVIDER", value = var.llm_fallback_provider },
        { name = "LLM_FALLBACK_MODEL", value = var.llm_fallback_model },
        { name = "MAX_TOKEN_BUDGET", value = tostring(var.max_token_budget) },
        { name = "MAX_TOOL_ITERATIONS", value = tostring(var.max_tool_iterations) },
        { name = "ENABLE_PII_REDACTION", value = tostring(var.enable_pii_redaction) },
      ]

      secrets = concat(local.base_secrets, local.datadog_secrets, local.gitlab_secrets, local.github_secrets)

      healthCheck = {
        command     = ["CMD-SHELL", "curl -fsS http://127.0.0.1:${local.health_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  }

  create_task_exec_iam_role          = true
  task_exec_iam_role_name            = "${var.application}-${var.environment}-task-exec"
  task_exec_iam_role_use_name_prefix = false
  task_exec_secret_arns = [
    local.secret_arn,
  ]

  create_tasks_iam_role          = true
  tasks_iam_role_name            = "${var.application}-${var.environment}-task-app"
  tasks_iam_role_use_name_prefix = false

  tasks_iam_role_policies = merge(
    {
      ObservabilityReadOnly = aws_iam_policy.observability_readonly.arn
      BedrockInference      = aws_iam_policy.ecs_bedrock_inference.arn
      STSAssumeSubagents    = aws_iam_policy.sts_assume_subagents.arn
    },
    local.enable_hub ? {
      DynamoDBHubAccess = aws_iam_policy.dynamodb_access[0].arn
    } : {},
    var.enable_aws_readonly_access ? {
      AWSManagedReadOnlyAccess = "arn:aws:iam::aws:policy/ReadOnlyAccess"
    } : {},
    var.additional_task_iam_policies
  )
}

resource "aws_iam_policy" "observability_readonly" {
  name        = "${var.application}-${var.environment}-observability-readonly-policy"
  description = "Least-privilege AWS observability read-only permissions for Serenity-Bot (no S3 object or DynamoDB item reads)"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchMetricsAndAlarmsRead"
        Effect = "Allow"
        Action = [
          "cloudwatch:Describe*",
          "cloudwatch:GetMetric*",
          "cloudwatch:ListMetrics"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogsRead"
        Effect = "Allow"
        Action = [
          "logs:FilterLogEvents",
          "logs:Get*",
          "logs:Describe*"
        ]
        Resource = "*"
      },
      {
        Sid    = "ECSRDSCloudTrailMetadataRead"
        Effect = "Allow"
        Action = [
          "ecs:Describe*",
          "ecs:List*",
          "rds:Describe*",
          "cloudtrail:LookupEvents"
        ]
        Resource = "*"
      },
      {
        Sid    = "DynamoDBAndLambdaMetadataReadOnly"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeTable",
          "dynamodb:ListTables",
          "lambda:GetFunctionConfiguration",
          "lambda:ListFunctions"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_policy" "ecs_bedrock_inference" {
  name        = "${var.application}-${var.environment}-bedrock-policy"
  description = "Allows Serenity-Bot to invoke AWS Bedrock Converse API and foundation models"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Converse",
          "bedrock:ConverseStream"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:*:inference-profile/*"
        ]
      }
    ]
  })
}

resource "aws_iam_policy" "dynamodb_access" {
  count       = local.enable_hub ? 1 : 0
  name        = "${var.application}-${var.environment}-dynamodb-hub-policy"
  description = "Allows Serenity-Bot to synchronize state, incidents, and chat history with the serenity-ops-hub table"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          "arn:aws:dynamodb:*:*:table/${var.dynamodb_table_name}",
          "arn:aws:dynamodb:*:*:table/${var.dynamodb_table_name}/index/*"
        ]
      }
    ]
  })
}

resource "aws_dynamodb_table_item" "bot_registration" {
  count      = local.enable_hub ? 1 : 0
  table_name = var.dynamodb_table_name
  hash_key   = "PK"
  range_key  = "SK"

  item = jsonencode({
    PK             = { S = "SERENITY#MODULES" }
    SK             = { S = "MOD#serenity-bot" }
    name           = { S = "serenity-bot" }
    status         = { S = "ACTIVE" }
    environment    = { S = var.environment }
    version        = { S = "1.2.0" }
    retention_days = { N = tostring(var.history_retention_days) }
    integrations = {
      M = {
        datadog = { BOOL = var.enable_datadog }
        gitlab  = { BOOL = var.enable_gitlab }
        github  = { BOOL = var.enable_github }
        grafana = { BOOL = var.enable_grafana }
      }
    }
  })
}

resource "aws_iam_policy" "sts_assume_subagents" {
  name        = "${var.application}-${var.environment}-sts-subagents-policy"
  description = "Allows Serenity-Bot to assume scoped domain sub-agent roles (SES, CloudWatch) after human approval"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sts:AssumeRole"]
        Resource = ["arn:aws:iam::*:role/*serenity-agent-*"]
      }
    ]
  })
}
