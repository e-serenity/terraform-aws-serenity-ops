output "dynamodb_hub_table_name" {
  description = "Central DynamoDB Hub table name"
  value       = module.serenity_ops.dynamodb_hub_table_name
}

output "dynamodb_hub_table_arn" {
  description = "Central DynamoDB Hub table ARN"
  value       = module.serenity_ops.dynamodb_hub_table_arn
}

output "dashboard_url" {
  description = "HTTPS URL of the Serenity-Ops Web Dashboard (CloudFront)"
  value       = module.serenity_ops.dashboard_url
}

output "dashboard_cognito_user_pool_id" {
  description = "AWS Cognito User Pool ID protecting the Web Dashboard"
  value       = module.serenity_ops.dashboard_cognito_user_pool_id
}

output "dashboard_cognito_hosted_ui_url" {
  description = "AWS Cognito Hosted UI URL for operator sign-in"
  value       = module.serenity_ops.dashboard_cognito_hosted_ui_url
}

output "bot_ecs_cluster_arn" {
  description = "ECS Managed Instances cluster ARN (when enable_bot = true)"
  value       = module.serenity_ops.bot_ecs_cluster_arn
}

output "bot_vpc_id" {
  description = "Bot VPC ID (when enable_bot = true and created/managed by serenity-bot)"
  value       = module.serenity_ops.bot_vpc_id
}

output "bot_ecr_repository_url" {
  description = "Bot ECR Repository URL (when enable_bot = true)"
  value       = module.serenity_ops.bot_ecr_repository_url
}
