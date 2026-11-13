output "bot_service_name" {
  description = "Name of the deployed Serenity-Bot ECS service"
  value       = module.serenity_bot.service_name
}

output "bot_ecs_cluster_arn" {
  description = "ECS Managed Instances cluster ARN"
  value       = module.serenity_bot.ecs_cluster_arn
}

output "bot_vpc_id" {
  description = "Bot VPC ID (when created or managed by serenity-bot)"
  value       = module.serenity_bot.vpc_id
}

output "bot_secrets_manager_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret storing bot credentials"
  value       = module.serenity_bot.secrets_manager_secret_arn
}

output "bot_tasks_iam_role_arn" {
  description = "ARN of the Serenity-Bot ECS task IAM role"
  value       = module.serenity_bot.tasks_iam_role_arn
}

output "bot_ecr_repository_url" {
  description = "Bot ECR Repository URL (when create_ecr_repository = true)"
  value       = module.serenity_bot.ecr_repository_url
}
