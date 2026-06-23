data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  lower   = true
  numeric = true
  special = false
  upper   = false
}

locals {
  name_prefix    = "${var.resource_prefix}-${var.environment}"
  compact_prefix = replace(local.name_prefix, "-", "")
  short_prefix   = substr(local.compact_prefix, 0, 12)

  acr_name             = substr("cr${local.short_prefix}${random_string.suffix.result}", 0, 50)
  storage_account_name = substr("st${local.short_prefix}${random_string.suffix.result}", 0, 24)
  search_name          = substr("${local.name_prefix}-search-${random_string.suffix.result}", 0, 60)

  common_tags = merge(var.tags, {
    environment = var.environment
    managed_by  = "terraform"
  })

  control_plane_image = "${azurerm_container_registry.this.login_server}/control-plane-api:${var.container_image_tags.control_plane_api}"
  inference_image     = "${azurerm_container_registry.this.login_server}/inference-service:${var.container_image_tags.inference_service}"
  rag_image           = "${azurerm_container_registry.this.login_server}/rag-service:${var.container_image_tags.rag_service}"
  web_console_image   = "${azurerm_container_registry.this.login_server}/web-console:${var.container_image_tags.web_console}"

  control_plane_url = "https://${azurerm_container_app.control_plane.ingress[0].fqdn}"
  inference_url     = "https://${azurerm_container_app.inference.ingress[0].fqdn}"
  rag_url           = "https://${azurerm_container_app.rag.ingress[0].fqdn}"
  web_console_url   = "https://${azurerm_container_app.web_console.ingress[0].fqdn}"

  postgres_database_url = var.enable_postgres ? "postgresql+psycopg://careaiadmin:${random_password.postgres_admin[0].result}@${azurerm_postgresql_flexible_server.this[0].fqdn}:5432/careai?sslmode=require" : ""
}

resource "azurerm_resource_group" "this" {
  name     = "${local.name_prefix}-rg"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "${local.name_prefix}-law"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

resource "azurerm_application_insights" "this" {
  name                = "${local.name_prefix}-appi"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.this.id
  tags                = local.common_tags
}

resource "azurerm_container_registry" "this" {
  name                = local.acr_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.common_tags
}

resource "azurerm_user_assigned_identity" "container_apps" {
  name                = "${local.name_prefix}-apps-mi"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.common_tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.container_apps.principal_id
}

resource "azurerm_container_app_environment" "this" {
  name                       = "${local.short_prefix}-cae-${random_string.suffix.result}"
  location                   = var.container_apps_location
  resource_group_name        = azurerm_resource_group.this.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  tags                       = local.common_tags
}

resource "azurerm_key_vault" "this" {
  name                       = substr("kv${local.short_prefix}${random_string.suffix.result}", 0, 24)
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = local.common_tags
}

resource "azurerm_role_assignment" "apps_key_vault_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.container_apps.principal_id
}

resource "azurerm_storage_account" "this" {
  name                            = local.storage_account_name
  location                        = azurerm_resource_group.this.location
  resource_group_name             = azurerm_resource_group.this.name
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = true
  tags                            = local.common_tags
}

resource "azurerm_storage_container" "artifacts" {
  name                  = "artifacts"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "datasets" {
  name                  = "datasets"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "eval_reports" {
  name                  = "eval-reports"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_role_assignment" "apps_storage_blob_contributor" {
  scope                = azurerm_storage_account.this.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.container_apps.principal_id
}

resource "azurerm_search_service" "this" {
  name                = local.search_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = var.azure_ai_search_sku
  replica_count       = 1
  partition_count     = 1
  tags                = local.common_tags
}

resource "azurerm_role_assignment" "apps_search_index_contributor" {
  scope                = azurerm_search_service.this.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azurerm_user_assigned_identity.container_apps.principal_id
}

resource "azurerm_role_assignment" "apps_search_index_reader" {
  scope                = azurerm_search_service.this.id
  role_definition_name = "Search Index Data Reader"
  principal_id         = azurerm_user_assigned_identity.container_apps.principal_id
}
