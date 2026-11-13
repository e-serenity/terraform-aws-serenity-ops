provider "aws" {
  region = local.region

  default_tags {
    tags = local.tags
  }
}

locals {
  application = "serenity-bot"
  environment = "preprod"
  region      = "eu-west-3"

  tags = {
    Example     = local.application
    Environment = local.environment
    ManagedBy   = "terraform"
  }
}

################################################################################
# Standalone Serenity-Bot (Slack Socket Mode + AWS Bedrock RCA)
################################################################################

module "serenity_bot" {
  source = "../../modules/serenity-bot"

  application = local.application
  environment = local.environment
  region      = local.region
  tags        = local.tags

  # Standalone Slack-only mode (no DynamoDB Hub required)
  dynamodb_table_name = ""

  # Networking (self-contained by default; or pass cluster_arn + subnet_ids for BYO-ECS)
  create_vpc                 = true
  vpc_cidr                   = "10.10.0.0/16"
  single_nat_gateway         = true
  enable_s3_endpoint         = true
  enable_bedrock_endpoint    = true
  ecs_allowed_instance_types = ["m8g.*", "m7g.*", "m6g.*", "m6a.*", "t4g.*"]

  # Populate credentials directly in AWS Secrets Manager after apply,
  # or set create_secrets = false and pass existing_secret_arn.
  create_secrets = true

  enable_github  = true
  enable_gitlab  = false
  enable_datadog = false
  enable_grafana = false
}
