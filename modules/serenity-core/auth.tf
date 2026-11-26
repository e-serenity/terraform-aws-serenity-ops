locals {
  enable_cognito = var.enable_dashboard && var.dashboard_auth_mode == "cognito"
  enable_oidc    = var.enable_dashboard && var.dashboard_auth_mode == "oidc"

  cognito_default_prefix = substr(
    trim(
      replace(
        lower("${local.name_prefix}-${substr(md5(data.aws_caller_identity.current.account_id), 0, 8)}"),
        "/[^a-z0-9-]/",
        "-"
      ),
      "-"
    ),
    0,
    63
  )
  cognito_domain_prefix = var.dashboard_cognito_domain_prefix != "" ? var.dashboard_cognito_domain_prefix : local.cognito_default_prefix

  dashboard_base_url = var.enable_dashboard ? "https://${aws_cloudfront_distribution.dashboard[0].domain_name}" : ""
  dashboard_callback_urls = var.enable_dashboard ? distinct(concat(
    [
      local.dashboard_base_url,
      "${local.dashboard_base_url}/",
    ],
    var.dashboard_additional_callback_urls
  )) : []

  auth_config_s3_key = "_internal/auth-config.json"

  cognito_issuer_url = local.enable_cognito ? "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.dashboard[0].id}" : ""
  cognito_hosted_ui  = local.enable_cognito ? "https://${aws_cognito_user_pool_domain.dashboard[0].domain}.auth.${var.region}.amazoncognito.com" : ""
}

resource "aws_cognito_user_pool" "dashboard" {
  count = local.enable_cognito ? 1 : 0

  name                     = "${local.name_prefix}-dashboard-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = var.dashboard_cognito_mfa_configuration

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  dynamic "software_token_mfa_configuration" {
    for_each = var.dashboard_cognito_mfa_configuration != "OFF" ? [1] : []
    content {
      enabled = true
    }
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-dashboard-users"
  })
}

resource "aws_cognito_user_pool_domain" "dashboard" {
  count = local.enable_cognito ? 1 : 0

  domain       = local.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.dashboard[0].id
}

resource "aws_cognito_user_group" "dashboard_admins" {
  count = local.enable_cognito ? 1 : 0

  name         = "serenity-admins"
  user_pool_id = aws_cognito_user_pool.dashboard[0].id
  description  = "Serenity-Ops operators authorized to approve Human-in-the-Loop write actions"
}

resource "aws_cognito_user" "dashboard_admins" {
  for_each = local.enable_cognito ? toset(var.dashboard_cognito_admin_emails) : toset([])

  user_pool_id = aws_cognito_user_pool.dashboard[0].id
  username     = each.value

  attributes = {
    email          = each.value
    email_verified = "true"
  }

  lifecycle {
    ignore_changes = [attributes]
  }
}

resource "aws_cognito_user_in_group" "dashboard_admins" {
  for_each = local.enable_cognito ? toset(var.dashboard_cognito_admin_emails) : toset([])

  user_pool_id = aws_cognito_user_pool.dashboard[0].id
  group_name   = aws_cognito_user_group.dashboard_admins[0].name
  username     = aws_cognito_user.dashboard_admins[each.key].username
}

resource "aws_cognito_user_pool_client" "dashboard" {
  count = local.enable_cognito ? 1 : 0

  name         = "${local.name_prefix}-dashboard-spa"
  user_pool_id = aws_cognito_user_pool.dashboard[0].id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]

  callback_urls = local.dashboard_callback_urls
  logout_urls   = local.dashboard_callback_urls

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 7

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

# Stored in the private dashboard S3 bucket (not exposed via CloudFront) so the
# Live API Lambda reads the resolved OIDC/Cognito client ID without creating a
# Terraform dependency cycle between CloudFront, Lambda, and Cognito callbacks.
resource "aws_s3_object" "dashboard_auth_config" {
  count = var.enable_dashboard ? 1 : 0

  bucket       = aws_s3_bucket.dashboard[0].id
  key          = local.auth_config_s3_key
  content_type = "application/json; charset=utf-8"

  content = jsonencode({
    enabled               = var.dashboard_auth_mode != "none"
    mode                  = var.dashboard_auth_mode
    issuer                = local.enable_cognito ? local.cognito_issuer_url : (local.enable_oidc ? trimsuffix(var.dashboard_oidc_issuer_url, "/") : "")
    clientId              = local.enable_cognito ? aws_cognito_user_pool_client.dashboard[0].id : (local.enable_oidc ? var.dashboard_oidc_client_id : "")
    scopes                = var.dashboard_oidc_scopes
    authorizationEndpoint = local.enable_cognito ? "${local.cognito_hosted_ui}/oauth2/authorize" : (local.enable_oidc ? var.dashboard_oidc_authorization_endpoint : "")
    tokenEndpoint         = local.enable_cognito ? "${local.cognito_hosted_ui}/oauth2/token" : (local.enable_oidc ? var.dashboard_oidc_token_endpoint : "")
    logoutEndpoint        = local.enable_cognito ? "${local.cognito_hosted_ui}/logout" : (local.enable_oidc ? var.dashboard_oidc_logout_endpoint : "")
    allowedGroups         = var.dashboard_oidc_allowed_groups
  })
}
