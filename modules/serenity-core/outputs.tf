output "dynamodb_hub_table_name" {
  description = "Central DynamoDB Hub table name (serenity-ops-hub)"
  value       = var.enable_dynamodb_hub ? aws_dynamodb_table.hub[0].name : null
}

output "dynamodb_hub_table_arn" {
  description = "Central DynamoDB Hub table ARN"
  value       = var.enable_dynamodb_hub ? aws_dynamodb_table.hub[0].arn : null
}

output "dashboard_url" {
  description = "HTTPS URL of the Serenity-Ops Web Dashboard (CloudFront)"
  value       = var.enable_dashboard ? "https://${aws_cloudfront_distribution.dashboard[0].domain_name}" : null
}

output "dashboard_cloudfront_id" {
  description = "CloudFront Distribution ID for the Web Dashboard"
  value       = var.enable_dashboard ? aws_cloudfront_distribution.dashboard[0].id : null
}

output "dashboard_s3_bucket_name" {
  description = "Private S3 bucket name hosting the Web Dashboard"
  value       = var.enable_dashboard ? aws_s3_bucket.dashboard[0].id : null
}

output "dashboard_api_role_arn" {
  description = "IAM Role ARN of the Web Dashboard Live API Lambda (null when enable_dashboard = false)"
  value       = var.enable_dashboard ? aws_iam_role.dashboard_api[0].arn : null
}

output "dashboard_auth_mode" {
  description = "Configured authentication mode for the Web Dashboard ('cognito', 'oidc', or 'none')"
  value       = var.enable_dashboard ? var.dashboard_auth_mode : null
}

output "dashboard_cognito_user_pool_id" {
  description = "AWS Cognito User Pool ID protecting the Web Dashboard (null when dashboard_auth_mode != 'cognito')"
  value       = local.enable_cognito ? aws_cognito_user_pool.dashboard[0].id : null
}

output "dashboard_cognito_user_pool_arn" {
  description = "AWS Cognito User Pool ARN protecting the Web Dashboard (null when dashboard_auth_mode != 'cognito')"
  value       = local.enable_cognito ? aws_cognito_user_pool.dashboard[0].arn : null
}

output "dashboard_cognito_client_id" {
  description = "AWS Cognito SPA App Client ID (PKCE, no client secret; null when dashboard_auth_mode != 'cognito')"
  value       = local.enable_cognito ? aws_cognito_user_pool_client.dashboard[0].id : null
}

output "dashboard_cognito_hosted_ui_url" {
  description = "HTTPS base URL of the AWS Cognito Hosted UI domain (null when dashboard_auth_mode != 'cognito')"
  value       = local.enable_cognito ? local.cognito_hosted_ui : null
}
