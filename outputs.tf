# ------------------------------------------------------------------------------
# Serenity-Core
# ------------------------------------------------------------------------------

output "dynamodb_hub_table_name" {
  description = "Central DynamoDB Hub table name (null when enable_core = false or enable_dynamodb_hub = false)"
  value       = try(module.serenity_core[0].dynamodb_hub_table_name, null)
}

output "dynamodb_hub_table_arn" {
  description = "Central DynamoDB Hub table ARN"
  value       = try(module.serenity_core[0].dynamodb_hub_table_arn, null)
}

output "dashboard_url" {
  description = "HTTPS URL of the Serenity-Ops Web Dashboard (CloudFront)"
  value       = try(module.serenity_core[0].dashboard_url, null)
}

output "dashboard_cloudfront_id" {
  description = "CloudFront Distribution ID for the Web Dashboard"
  value       = try(module.serenity_core[0].dashboard_cloudfront_id, null)
}

output "dashboard_s3_bucket_name" {
  description = "Private S3 bucket name hosting the Web Dashboard"
  value       = try(module.serenity_core[0].dashboard_s3_bucket_name, null)
}

# ------------------------------------------------------------------------------
# Serenity-Bot
# ------------------------------------------------------------------------------

output "bot_service_name" {
  description = "Name of the deployed Serenity-Bot ECS service"
  value       = try(module.serenity_bot[0].service_name, null)
}

output "bot_service_id" {
  description = "ID of the deployed Serenity-Bot ECS service"
  value       = try(module.serenity_bot[0].service_id, null)
}

output "bot_tasks_iam_role_arn" {
  description = "ARN of the Serenity-Bot ECS task IAM role"
  value       = try(module.serenity_bot[0].tasks_iam_role_arn, null)
}

output "bot_secrets_manager_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret storing bot credentials"
  value       = try(module.serenity_bot[0].secrets_manager_secret_arn, null)
}

output "bot_ecr_repository_url" {
  description = "URL of the AWS ECR repository for the bot container image (null when bot_create_ecr_repository = false)"
  value       = try(module.serenity_bot[0].ecr_repository_url, null)
}

output "bot_vpc_id" {
  description = "VPC ID used by Serenity-Bot (null when enable_bot = false or using an external cluster_arn)"
  value       = try(module.serenity_bot[0].vpc_id, null)
}

output "bot_public_subnet_ids" {
  description = "Created public subnet IDs for Serenity-Bot"
  value       = try(module.serenity_bot[0].public_subnet_ids, [])
}

output "bot_private_subnet_ids" {
  description = "Private subnet IDs used by Serenity-Bot ECS tasks"
  value       = try(module.serenity_bot[0].private_subnet_ids, [])
}

output "bot_ecs_cluster_id" {
  description = "ECS Managed Instances cluster ID (when created by Serenity-Bot)"
  value       = try(module.serenity_bot[0].ecs_cluster_id, null)
}

output "bot_ecs_cluster_arn" {
  description = "Effective Serenity-Bot ECS cluster ARN"
  value       = try(module.serenity_bot[0].ecs_cluster_arn, null)
}

output "bot_ecs_cluster_name" {
  description = "ECS Managed Instances cluster name (when created by Serenity-Bot)"
  value       = try(module.serenity_bot[0].ecs_cluster_name, null)
}

output "bot_ecs_capacity_provider_name" {
  description = "Effective Serenity-Bot ECS Managed Instances capacity provider name"
  value       = try(module.serenity_bot[0].ecs_capacity_provider_name, null)
}

output "bot_platform_alarms_sns_topic_arn" {
  description = "ARN of the SNS topic receiving platform self-monitoring CloudWatch alarms"
  value       = try(module.serenity_bot[0].platform_alarms_sns_topic_arn, null)
}

output "bot_platform_alarms_cloudwatch_alarm_arns" {
  description = "List of ARNs of created CloudWatch alarms monitoring the Serenity-Ops platform"
  value       = try(module.serenity_bot[0].platform_alarms_cloudwatch_alarm_arns, [])
}

# ------------------------------------------------------------------------------
# Serenity-SES
# ------------------------------------------------------------------------------

output "ses_configuration_set" {
  description = "Name of the SES v2 configuration set (when enable_ses = true)"
  value       = try(module.serenity_ses[0].configuration_set, null)
}

output "ses_dedicated_pool_name" {
  description = "Name of the SES managed dedicated IP pool (null when disabled)"
  value       = try(module.serenity_ses[0].dedicated_pool_name, null)
}

output "ses_agent_role_arn" {
  description = "ARN of the scoped IAM role serenity-agent-ses for AI orchestrator delegation"
  value       = try(module.serenity_ses[0].agent_role_arn, null)
}

output "ses_sns_topic_arn" {
  description = "ARN of the SNS topic receiving SES sending reports"
  value       = try(module.serenity_ses[0].sns_topic_arn, null)
}

output "ses_sqs_queue_arn" {
  description = "ARN of the SQS queue buffering SES sending reports"
  value       = try(module.serenity_ses[0].sqs_queue_arn, null)
}
