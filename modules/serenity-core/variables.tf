variable "project_name" {
  description = "Project name and resource prefix (e.g., serenity-ops)"
  type        = string
  default     = "serenity-ops"
}

variable "environment" {
  description = "Deployment environment (e.g., dev, preprod, prod)"
  type        = string
  default     = "preprod"
}

variable "region" {
  description = "Target AWS region"
  type        = string
  default     = "eu-west-3"
}

variable "tags" {
  description = "Additional tags applied to module resources"
  type        = map(string)
  default     = {}
}

variable "enable_dynamodb_hub" {
  description = "Enable central DynamoDB Hub table (Single-Table Design for module discovery, state and audit)"
  type        = bool
  default     = true
}

variable "dynamodb_hub_table_name" {
  description = "Custom DynamoDB Hub table name (defaults to <project_name>-<environment>-hub)"
  type        = string
  default     = ""
}

variable "dynamodb_enable_pitr" {
  description = "Enable Point-in-Time Recovery (PITR) on the DynamoDB Hub table"
  type        = bool
  default     = false
}

variable "enable_dashboard" {
  description = "Enable Serenity-Ops Web Dashboard (Private S3 + CloudFront OAC + Live API Lambda)"
  type        = bool
  default     = true
}

variable "dashboard_allowed_ips" {
  description = "Allowed IPv4 or IPv6 addresses/CIDRs for the Web Dashboard via CloudFront Function (fail-closed by default: empty [] blocks all public access; specify your VPN/office CIDRs or explicitly set ['0.0.0.0/0'] to open publicly)"
  type        = list(string)
  default     = []
}

variable "dashboard_price_class" {
  description = "CloudFront price class for the Web Dashboard (PriceClass_100, PriceClass_200, PriceClass_All)"
  type        = string
  default     = "PriceClass_100"
}

variable "dashboard_s3_force_destroy" {
  description = "Whether to allow force-destroying the S3 bucket hosting the Web Dashboard even when non-empty (defaults to false for production safety)"
  type        = bool
  default     = false
}

# ------------------------------------------------------------------------------
# Web Dashboard Authentication (AWS Cognito / Generic OIDC with PKCE & JWT)
# ------------------------------------------------------------------------------

variable "dashboard_auth_mode" {
  description = "Authentication mode for the Web Dashboard and Live API: 'cognito' (default, provisions an AWS Cognito User Pool with Hosted UI + PKCE + JWT verification at $0/mo Free Tier), 'oidc' (bring your own OIDC provider such as Okta, Entra ID, Google Workspace, Authentik, or Keycloak), or 'none' (rely solely on CloudFront Edge IP filtering)"
  type        = string
  default     = "cognito"

  validation {
    condition     = contains(["cognito", "oidc", "none"], var.dashboard_auth_mode)
    error_message = "'dashboard_auth_mode' must be one of: 'cognito', 'oidc', or 'none'."
  }
}

variable "dashboard_cognito_domain_prefix" {
  description = "Optional globally unique prefix for the Cognito Hosted UI domain (used when dashboard_auth_mode = 'cognito'). Defaults to '<project_name>-<environment>-<account_hash>'."
  type        = string
  default     = ""
}

variable "dashboard_cognito_admin_emails" {
  description = "Optional list of operator email addresses pre-provisioned in the Cognito User Pool and added to the 'serenity-admins' group (used when dashboard_auth_mode = 'cognito')"
  type        = list(string)
  default     = []
}

variable "dashboard_cognito_mfa_configuration" {
  description = "MFA configuration for the Cognito User Pool ('OPTIONAL', 'ON', or 'OFF'). Software TOTP authenticator apps are enabled whenever set to 'OPTIONAL' or 'ON'."
  type        = string
  default     = "OPTIONAL"

  validation {
    condition     = contains(["OFF", "OPTIONAL", "ON"], var.dashboard_cognito_mfa_configuration)
    error_message = "'dashboard_cognito_mfa_configuration' must be one of: 'OFF', 'OPTIONAL', or 'ON'."
  }
}

variable "dashboard_additional_callback_urls" {
  description = "Optional extra OAuth2 callback/logout URLs registered on the Cognito SPA client (e.g., custom domain https://ops.example.com or http://localhost:5173 for local testing)"
  type        = list(string)
  default     = []
}

variable "dashboard_oidc_issuer_url" {
  description = "OIDC Issuer URL (e.g., 'https://accounts.google.com' or 'https://login.microsoftonline.com/<tenant>/v2.0'). Required when dashboard_auth_mode = 'oidc'."
  type        = string
  default     = ""

  validation {
    condition     = !var.enable_dashboard || var.dashboard_auth_mode != "oidc" || length(trimspace(var.dashboard_oidc_issuer_url)) > 0
    error_message = "'dashboard_oidc_issuer_url' is required when 'enable_dashboard = true' and 'dashboard_auth_mode = \"oidc\"'."
  }
}

variable "dashboard_oidc_client_id" {
  description = "OIDC public SPA Client ID (Authorization Code + PKCE, no client secret). Required when dashboard_auth_mode = 'oidc'."
  type        = string
  default     = ""

  validation {
    condition     = !var.enable_dashboard || var.dashboard_auth_mode != "oidc" || length(trimspace(var.dashboard_oidc_client_id)) > 0
    error_message = "'dashboard_oidc_client_id' is required when 'enable_dashboard = true' and 'dashboard_auth_mode = \"oidc\"'."
  }
}

variable "dashboard_oidc_authorization_endpoint" {
  description = "Optional override for the OIDC authorization endpoint (auto-discovered from '<issuer>/.well-known/openid-configuration' when empty)"
  type        = string
  default     = ""
}

variable "dashboard_oidc_token_endpoint" {
  description = "Optional override for the OIDC token endpoint (auto-discovered from '<issuer>/.well-known/openid-configuration' when empty)"
  type        = string
  default     = ""
}

variable "dashboard_oidc_logout_endpoint" {
  description = "Optional override for the OIDC logout / end_session endpoint (auto-discovered from '<issuer>/.well-known/openid-configuration' when empty)"
  type        = string
  default     = ""
}

variable "dashboard_oidc_scopes" {
  description = "Space-separated OAuth2 scopes requested by the Web Dashboard during OIDC/Cognito sign-in"
  type        = string
  default     = "openid email profile"
}

variable "dashboard_oidc_allowed_groups" {
  description = "Optional list of group names (checked against JWT 'cognito:groups' or 'groups' claim) authorized to execute write actions (POST /api/chat, POST /api/actions/approve, POST /api/actions/reject). When empty, any authenticated user can perform actions."
  type        = list(string)
  default     = []
}
