resource "aws_dynamodb_table_item" "module_registration" {
  count      = var.serenity_ops_table_name != "" ? 1 : 0
  table_name = var.serenity_ops_table_name
  hash_key   = "PK"
  range_key  = "SK"

  item = jsonencode({
    PK             = { S = "SERENITY#MODULES" }
    SK             = { S = "MOD#serenity-ses" }
    name           = { S = "serenity-ses" }
    status         = { S = "ACTIVE" }
    environment    = { S = var.environment }
    version        = { S = "0.1.2" }
    agent_role_arn = { S = try(aws_iam_role.serenity_agent_ses[0].arn, "") }
    updated_at     = { S = timestamp() }
  })

  lifecycle {
    ignore_changes = [item]
  }
}

resource "aws_dynamodb_table_item" "ses_state_summary" {
  count      = var.serenity_ops_table_name != "" ? 1 : 0
  table_name = var.serenity_ops_table_name
  hash_key   = "PK"
  range_key  = "SK"

  item = jsonencode({
    PK          = { S = "MOD#serenity-ses" }
    SK          = { S = "STATE#SUMMARY" }
    dmarc       = { S = "valid" }
    spf         = { S = "valid" }
    dkim        = { S = "valid" }
    bounce_rate = { N = "0.0" }
    dedicated_ips = { S = jsonencode(
      var.enable_dedicated_ip_pool ? [
        {
          pool = aws_sesv2_dedicated_ip_pool.dedicated_pool[0].pool_name
          mode = "MANAGED"
        }
      ] : []
    ) }
    updated_at = { S = timestamp() }
  })

  lifecycle {
    ignore_changes = [item]
  }
}
