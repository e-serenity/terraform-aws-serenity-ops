locals {
  enable_core = var.create && var.enable_core
  enable_bot  = var.create && var.enable_bot
  enable_ses  = var.create && var.enable_ses

  # Deterministic DynamoDB Hub table name when Core Hub is created so count conditions remain known at plan time
  resolved_hub_table_name = local.enable_core && var.enable_dynamodb_hub ? (
    coalesce(var.dynamodb_hub_table_name, "${var.project_name}-${var.environment}-hub")
  ) : var.dynamodb_table_name

  ses_name_prefix = coalesce(var.ses_name_prefix, "${var.project_name}-${var.environment}")
}

module "serenity_core" {
  count  = local.enable_core ? 1 : 0
  source = "./modules/serenity-core"

  project_name = var.project_name
  environment  = var.environment
  region       = var.region
  tags         = var.tags

  enable_dynamodb_hub     = var.enable_dynamodb_hub
  dynamodb_hub_table_name = var.dynamodb_hub_table_name
  dynamodb_enable_pitr    = var.dynamodb_enable_pitr

  enable_dashboard      = var.enable_dashboard
  dashboard_allowed_ips = var.dashboard_allowed_ips
  dashboard_price_class = var.dashboard_price_class
}

module "serenity_bot" {
  count  = local.enable_bot ? 1 : 0
  source = "./modules/serenity-bot"

  depends_on = [module.serenity_core]

  application         = var.bot_application
  environment         = var.environment
  region              = var.region
  region_backup       = var.bot_region_backup
  dynamodb_table_name = local.resolved_hub_table_name
  tags                = var.tags

  create_secrets        = var.bot_create_secrets
  existing_secret_arn   = var.bot_existing_secret_arn
  initial_secrets       = var.bot_initial_secrets
  image                 = var.bot_image
  create_ecr_repository = var.bot_create_ecr_repository
  ecr_image_tag         = var.bot_ecr_image_tag
  cpu                   = var.bot_cpu
  memory                = var.bot_memory

  cluster_arn            = var.cluster_arn
  capacity_provider_name = var.capacity_provider_name
  subnet_ids             = var.subnet_ids

  create_vpc                       = var.create_vpc
  vpc_cidr                         = var.vpc_cidr
  availability_zones               = var.availability_zones
  public_subnet_cidrs              = var.public_subnet_cidrs
  private_subnet_cidrs             = var.private_subnet_cidrs
  enable_nat_gateway               = var.enable_nat_gateway
  single_nat_gateway               = var.single_nat_gateway
  existing_vpc_id                  = var.existing_vpc_id
  existing_private_route_table_ids = var.existing_private_route_table_ids
  enable_s3_endpoint               = var.enable_s3_endpoint
  enable_bedrock_endpoint          = var.enable_bedrock_endpoint

  ecs_cluster_name            = var.ecs_cluster_name
  ecs_container_insights      = var.ecs_container_insights
  ecs_allowed_instance_types  = var.ecs_allowed_instance_types
  ecs_instance_min_vcpu       = var.ecs_instance_min_vcpu
  ecs_instance_min_memory_mib = var.ecs_instance_min_memory_mib
  ecs_burstable_performance   = var.ecs_burstable_performance

  enable_datadog           = var.enable_datadog
  enable_gitlab            = var.enable_gitlab
  gitlab_allowed_namespace = var.gitlab_allowed_namespace
  enable_github            = var.enable_github
  enable_grafana           = var.enable_grafana
  history_retention_days   = var.history_retention_days

  llm_primary_provider  = var.llm_primary_provider
  llm_primary_model     = var.llm_primary_model
  llm_fallback_provider = var.llm_fallback_provider
  llm_fallback_model    = var.llm_fallback_model
  max_token_budget      = var.max_token_budget
  max_tool_iterations   = var.max_tool_iterations
  enable_pii_redaction  = var.enable_pii_redaction

  enable_platform_alarms              = var.enable_platform_alarms
  platform_alert_slack_channel        = var.platform_alert_slack_channel
  platform_alarms_cpu_threshold       = var.platform_alarms_cpu_threshold
  platform_alarms_memory_threshold    = var.platform_alarms_memory_threshold
  platform_alarms_error_log_threshold = var.platform_alarms_error_log_threshold

  application_context = var.application_context
}

module "serenity_ses" {
  count  = local.enable_ses ? 1 : 0
  source = "./modules/serenity-ses"

  depends_on = [module.serenity_core]

  name_prefix              = local.ses_name_prefix
  environment              = var.environment
  serenity_ops_table_name  = local.resolved_hub_table_name
  enable_serenity_agent    = var.ses_enable_agent
  enable_dedicated_ip_pool = var.ses_enable_dedicated_ip_pool
  tags                     = var.tags
}
