provider "aws" {
  region = local.region

  default_tags {
    tags = local.tags
  }
}

locals {
  name        = "serenity-ops"
  environment = "preprod"
  region      = "eu-west-3"

  tags = {
    Example     = local.name
    Environment = local.environment
    ManagedBy   = "terraform"
  }
}

################################################################################
# Serenity-Ops Full Suite (Core Hub + Web Console + Bot + SES)
################################################################################

module "serenity_ops" {
  source = "../.."

  project_name = local.name
  environment  = local.environment
  region       = local.region
  tags         = local.tags

  # Core Hub & Web Console
  enable_core           = true
  enable_dynamodb_hub   = true
  enable_dashboard      = true
  dashboard_allowed_ips = ["203.0.113.10/32"] # Replace with your VPN / Office CIDR

  # Serenity-Bot AI Orchestrator
  enable_bot         = true
  single_nat_gateway = true
  enable_github      = true
  enable_gitlab      = false
  enable_datadog     = false
  enable_grafana     = false

  # Populate credentials directly in AWS Secrets Manager after apply,
  # or set bot_create_secrets = false and pass bot_existing_secret_arn.
  bot_create_secrets = true

  application_context = {
    organization_name    = "Example Corp"
    business_domain      = "E-Commerce & Logistics"
    architecture_summary = "Microservices on AWS ECS Graviton with Aurora PostgreSQL"
    services = [
      {
        name        = "order-api"
        description = "Order validation and checkout processing service"
        tech_stack  = "Node.js / Express / Redis / PostgreSQL"
        repository  = "github.com/my-org/order-service"
        log_group   = "/aws/ecs/prod-order-api"
        criticality = "HIGH"
      }
    ]
    runbooks = {
      "HighLatency" = "https://wiki.example.com/runbooks/high-latency"
    }
  }

  # Serenity-SES Module
  enable_ses                   = true
  ses_enable_agent             = true
  ses_enable_dedicated_ip_pool = false
}
