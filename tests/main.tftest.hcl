mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
      arn        = "arn:aws:iam::123456789012:root"
      user_id    = "AIDAEXAMPLE"
    }
  }
  mock_data "aws_region" {
    defaults = {
      name   = "eu-west-3"
      region = "eu-west-3"
    }
  }
  mock_data "aws_partition" {
    defaults = {
      partition  = "aws"
      dns_suffix = "amazonaws.com"
    }
  }
}

mock_provider "archive" {}
mock_provider "random" {}

run "default_finops_and_security_hardening" {
  command = plan

  variables {
    project_name = "serenity-test"
    environment  = "preprod"
    region       = "eu-west-3"
    enable_core  = true
    enable_bot   = true
    enable_ses   = true
  }

  assert {
    condition     = var.single_nat_gateway == true
    error_message = "single_nat_gateway must default to true to avoid 3x NAT Gateway charges."
  }

  assert {
    condition     = var.enable_bedrock_endpoint == false
    error_message = "enable_bedrock_endpoint must default to false to avoid 3-AZ Interface Endpoint charges."
  }

  assert {
    condition     = var.ecs_container_insights == "enabled"
    error_message = "ecs_container_insights must default to 'enabled' instead of 'enhanced'."
  }

  assert {
    condition     = var.ses_enable_dedicated_ip_pool == false
    error_message = "ses_enable_dedicated_ip_pool must default to false to avoid dedicated IP charges."
  }

  assert {
    condition     = var.llm_fallback_provider == "none"
    error_message = "llm_fallback_provider must default to 'none' so prompts stay inside AWS by default."
  }

  assert {
    condition     = var.bot_image == "ghcr.io/e-serenity/serenity-bot:0.1.3"
    error_message = "bot_image must default to the pinned SemVer tag :0.1.3."
  }

  assert {
    condition     = var.bot_enable_execute_command == false
    error_message = "bot_enable_execute_command (ECS Exec) must default to false."
  }

  assert {
    condition     = var.bot_readonly_root_filesystem == true
    error_message = "bot_readonly_root_filesystem must default to true."
  }

  assert {
    condition     = var.bot_ecr_image_tag_mutability == "IMMUTABLE"
    error_message = "bot_ecr_image_tag_mutability must default to IMMUTABLE."
  }

  assert {
    condition     = var.bot_ecr_force_delete == false
    error_message = "bot_ecr_force_delete must default to false."
  }

  assert {
    condition     = var.dashboard_s3_force_destroy == false
    error_message = "dashboard_s3_force_destroy must default to false."
  }

  assert {
    condition     = length(var.dashboard_allowed_ips) == 0
    error_message = "dashboard_allowed_ips must default to an empty list (fail-closed at CloudFront edge)."
  }

  assert {
    condition     = var.dashboard_auth_mode == "cognito"
    error_message = "dashboard_auth_mode must default to 'cognito' so the Web Dashboard and APIs require authentication by default."
  }

  assert {
    condition     = var.dashboard_cognito_mfa_configuration == "OPTIONAL"
    error_message = "dashboard_cognito_mfa_configuration must default to 'OPTIONAL' with TOTP enabled."
  }
}

run "byo_oidc_dashboard_auth_mode" {
  command = plan

  variables {
    project_name              = "serenity-test"
    environment               = "prod"
    region                    = "eu-west-3"
    enable_core               = true
    enable_bot                = false
    enable_ses                = false
    dashboard_auth_mode       = "oidc"
    dashboard_oidc_issuer_url = "https://auth.example.com/application/o/serenity-ops/"
    dashboard_oidc_client_id  = "serenity-spa-client-id"
    dashboard_oidc_allowed_groups = [
      "platform-admins"
    ]
  }

  assert {
    condition     = output.dashboard_auth_mode == "oidc"
    error_message = "dashboard_auth_mode output should reflect 'oidc'."
  }

  assert {
    condition     = output.dashboard_cognito_user_pool_id == null
    error_message = "Cognito User Pool must not be created when dashboard_auth_mode = 'oidc'."
  }
}

run "none_dashboard_auth_mode_skips_cognito" {
  command = plan

  variables {
    project_name        = "serenity-test"
    environment         = "dev"
    region              = "eu-west-3"
    enable_core         = true
    enable_bot          = false
    enable_ses          = false
    dashboard_auth_mode = "none"
  }

  assert {
    condition     = output.dashboard_auth_mode == "none"
    error_message = "dashboard_auth_mode output should reflect 'none'."
  }

  assert {
    condition     = output.dashboard_cognito_user_pool_id == null
    error_message = "Cognito User Pool must not be created when dashboard_auth_mode = 'none'."
  }
}

run "byo_ecs_cluster_skips_vpc_creation" {
  command = plan

  variables {
    project_name           = "serenity-test"
    environment            = "prod"
    region                 = "eu-west-3"
    enable_core            = false
    enable_bot             = true
    enable_ses             = false
    cluster_arn            = "arn:aws:ecs:eu-west-3:123456789012:cluster/existing-cluster"
    capacity_provider_name = "existing-managed-instances"
    subnet_ids             = ["subnet-11111111", "subnet-22222222"]
  }

  assert {
    condition     = length(module.serenity_bot) == 1
    error_message = "serenity_bot module should be enabled."
  }
}
