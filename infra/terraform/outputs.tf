output "resource_group_name" {
  description = "Name of the Azure resource group."
  value       = azurerm_resource_group.this.name
}

output "acr_login_server" {
  description = "Azure Container Registry login server for pushing service images."
  value       = azurerm_container_registry.this.login_server
}

output "container_apps_urls" {
  description = "Public URLs for deployed Container Apps."
  value = {
    control_plane_api = local.control_plane_url
    inference_service = local.inference_url
    rag_service       = local.rag_url
    web_console       = local.web_console_url
  }
}

output "container_apps_names" {
  description = "Container App resource names for GitHub Actions deployment variables."
  value = {
    control_plane_api = azurerm_container_app.control_plane.name
    inference_service = azurerm_container_app.inference.name
    rag_service       = azurerm_container_app.rag.name
    web_console       = azurerm_container_app.web_console.name
  }
}

output "azure_ai_search_endpoint" {
  description = "Azure AI Search service endpoint."
  value       = "https://${azurerm_search_service.this.name}.search.windows.net"
}

output "storage_account_name" {
  description = "Storage account name for artifacts, datasets, and evaluation reports."
  value       = azurerm_storage_account.this.name
}

output "event_hubs_namespace" {
  description = "Event Hubs namespace name when enabled."
  value       = try(azurerm_eventhub_namespace.this[0].name, null)
}

output "event_hub_name" {
  description = "Prediction and audit event hub name when Event Hubs is enabled."
  value       = try(azurerm_eventhub.prediction_audit[0].name, null)
}

output "postgres_fqdn" {
  description = "PostgreSQL Flexible Server FQDN when enabled."
  value       = try(azurerm_postgresql_flexible_server.this[0].fqdn, null)
}

output "redis_hostname" {
  description = "Azure Cache for Redis hostname when enabled."
  value       = try(azurerm_redis_cache.this[0].hostname, null)
}

output "azure_ml_workspace_name" {
  description = "Azure Machine Learning workspace name when enabled."
  value       = try(azurerm_machine_learning_workspace.this[0].name, null)
}
