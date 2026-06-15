resource "random_password" "postgres_admin" {
  count   = var.enable_postgres ? 1 : 0
  length  = 24
  special = false
}

resource "azurerm_postgresql_flexible_server" "this" {
  count = var.enable_postgres ? 1 : 0

  name                          = "${local.name_prefix}-psql-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  version                       = "16"
  administrator_login           = "careaiadmin"
  administrator_password        = random_password.postgres_admin[0].result
  sku_name                      = var.postgres_sku_name
  storage_mb                    = 32768
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true
  tags                          = local.common_tags
}

resource "azurerm_postgresql_flexible_server_database" "careai" {
  count = var.enable_postgres ? 1 : 0

  name      = "careai"
  server_id = azurerm_postgresql_flexible_server.this[0].id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  count = var.enable_postgres ? 1 : 0

  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.this[0].id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_redis_cache" "this" {
  count = var.enable_redis ? 1 : 0

  name                          = "${local.name_prefix}-redis-${random_string.suffix.result}"
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  capacity                      = 0
  family                        = "C"
  sku_name                      = var.redis_sku_name
  non_ssl_port_enabled          = false
  minimum_tls_version           = "1.2"
  public_network_access_enabled = true
  tags                          = local.common_tags
}

resource "azurerm_eventhub_namespace" "this" {
  count = var.enable_event_hubs ? 1 : 0

  name                = "${local.name_prefix}-ehns-${random_string.suffix.result}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "Basic"
  capacity            = 1
  tags                = local.common_tags
}

resource "azurerm_eventhub" "prediction_audit" {
  count = var.enable_event_hubs ? 1 : 0

  name              = "prediction-audit-events"
  namespace_id      = azurerm_eventhub_namespace.this[0].id
  partition_count   = 2
  message_retention = 1
}

resource "azurerm_role_assignment" "apps_event_hubs_sender" {
  count = var.enable_event_hubs ? 1 : 0

  scope                = azurerm_eventhub_namespace.this[0].id
  role_definition_name = "Azure Event Hubs Data Sender"
  principal_id         = azurerm_user_assigned_identity.container_apps.principal_id
}

resource "azurerm_machine_learning_workspace" "this" {
  count = var.enable_azure_ml ? 1 : 0

  name                    = "${local.name_prefix}-mlw-${random_string.suffix.result}"
  location                = azurerm_resource_group.this.location
  resource_group_name     = azurerm_resource_group.this.name
  application_insights_id = azurerm_application_insights.this.id
  key_vault_id            = azurerm_key_vault.this.id
  storage_account_id      = azurerm_storage_account.this.id
  tags                    = local.common_tags

  identity {
    type = "SystemAssigned"
  }
}
