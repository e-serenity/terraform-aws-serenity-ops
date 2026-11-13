<div align="center">

# 📧 Serenity-SES (`modules/serenity-ses`)

**Automated AWS SES v2 Reputation Protection, Managed Dedicated IPs & AI-Optional Governance.**

[![Terraform Module](https://img.shields.io/badge/Terraform_Registry-e--serenity%2Fserenity--ops%2Faws%2F%2Fmodules%2Fserenity--ses-7B42BC?style=flat-square&logo=terraform&logoColor=white)](https://registry.terraform.io/modules/e-serenity/serenity-ops/aws/latest/submodules/serenity-ses)
[![AWS SES v2](https://img.shields.io/badge/AWS-SES_v2_%7C_Lambda_ARM64_%7C_DynamoDB-FF9900?style=flat-square&logo=amazon-web-services&logoColor=white)](https://aws.amazon.com/ses/)
[![AI-Optional](https://img.shields.io/badge/Architecture-Standalone_or_AI--Assisted-10B981?style=flat-square)](#deployment-modes)

<code>source = "e-serenity/serenity-ops/aws//modules/serenity-ses"</code>

</div>

## Why `serenity-ses`?

A hard **Bounce rate > 5%** or **Complaint rate > 0.1%** can cause AWS to place your SES account under probation and block your transactional emails.

**`serenity-ses`** deploys a serverless AWS SES v2 reputation protection pipeline that runs either standalone or connected to the **[Serenity-Ops](../..)** platform:

- **Managed Dedicated IP Pool (`MANAGED`):** Provisions and warms up your dedicated AWS SES v2 IPs with a pre-wired Configuration Set.
- **Real-Time Feedback Pipeline (`SNS -> SQS -> ARM64 Lambda`):** Captures `Bounce`, `Complaint`, and `DeliveryDelay` events, archives them in DynamoDB with native TTL, and tracks your sender reputation.
- **AI-Optional:** Works out of the box without AI. When connected to `serenity-ops` and `serenity-bot`, it streams live telemetry to the Web Console and enables the scoped **`serenity-agent-ses`** sub-agent (Suppression List quarantine & SPF/DKIM/DMARC auditing under human approval).

## Deployment Modes

### Option 1: Standalone Mode (Pure SES Reputation Protection, without `serenity-ops`)

```hcl
module "ses" {
  source  = "e-serenity/serenity-ops/aws//modules/serenity-ses"
  version = "~> 0.1"

  name_prefix = "my-company"
  environment = "prod"
}
```

### Option 2: Hub-Coupled Mode (`serenity-ops` Web Console + `serenity-agent-ses` AI Sub-Agent)

```hcl
module "ses" {
  source  = "e-serenity/serenity-ops/aws//modules/serenity-ses"
  version = "~> 0.1"

  name_prefix             = "serenity-prod"
  environment             = "prod"
  serenity_ops_table_name = module.serenity_core.dynamodb_hub_table_name
  enable_serenity_agent   = true
}
```

## Scoped Sub-Agent IAM Boundary (`serenity-agent-ses`)

When `enable_serenity_agent = true`, the module provisions the `serenity-agent-ses` IAM role, which `serenity-bot` can assume only after explicit human approval (`Approve`):
- **Read Scope:** SES v2 account reputation metrics, sending quotas, verified identities, and DNS verification (`SPF`, `DKIM`, `DMARC`).
- **Scoped Write Boundary:** Adding/removing hard-bounced addresses in the *Account Suppression List* (`sesv2:PutSuppressedDestination`) and modifying only resources tagged with `aws:ResourceTag/ManagedBy = serenity-ops`.

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.10.0 |
| <a name="requirement_archive"></a> [archive](#requirement\_archive) | >= 2.4.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 6.0.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_archive"></a> [archive](#provider\_archive) | >= 2.4.0 |
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 6.0.0 |

## Modules

No modules.

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_enable_dedicated_ip_pool"></a> [enable_dedicated_ip_pool](#input\_enable_dedicated_ip_pool) | Whether to provision an AWS SES v2 Managed Dedicated IP Pool (incurs AWS monthly dedicated IP add-on charges). Set to false to use the free shared SES pool. | `bool` | `true` | no |
| <a name="input_enable_serenity_agent"></a> [enable_serenity_agent](#input\_enable_serenity_agent) | Whether to provision the scoped IAM role for serenity-agent-ses (used by the Serenity-Ops AI orchestrator after human approval) | `bool` | `true` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | Deployment environment name (e.g., prod, preprod, dev) | `string` | `"prod"` | no |
| <a name="input_name_prefix"></a> [name_prefix](#input\_name_prefix) | Prefix applied to all created AWS SES, SNS, SQS, Lambda, and DynamoDB resources | `string` | n/a | yes |
| <a name="input_serenity_ops_table_name"></a> [serenity_ops_table_name](#input\_serenity_ops_table_name) | Optional: Name of the central Serenity-Ops DynamoDB Hub table (e.g., serenity-ops-hub) to register this module and stream real-time bounce/complaint events | `string` | `""` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Common tags applied to all created resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_agent_role_arn"></a> [agent_role_arn](#output\_agent_role_arn) | ARN of the scoped IAM role serenity-agent-ses for AI orchestrator delegation |
| <a name="output_configuration_set"></a> [configuration_set](#output\_configuration_set) | The ID of the configuration set to set on SES identities for using features of this module |
| <a name="output_dedicated_pool_name"></a> [dedicated_pool_name](#output\_dedicated_pool_name) | Name of the managed dedicated IP pool (null when enable_dedicated_ip_pool = false) |
| <a name="output_sns_topic_arn"></a> [sns_topic_arn](#output\_sns_topic_arn) | ARN of the SNS topic receiving SES sending reports |
| <a name="output_sqs_queue_arn"></a> [sqs_queue_arn](#output\_sqs_queue_arn) | ARN of the SQS queue buffering sending reports |
<!-- END_TF_DOCS -->
