resource "azurerm_container_app" "control_plane" {
  name                         = "${local.short_prefix}-ctrl-${random_string.suffix.result}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.container_apps.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.container_apps.id
  }

  dynamic "secret" {
    for_each = var.enable_postgres ? [local.postgres_database_url] : []
    content {
      name  = "control-plane-database-url"
      value = secret.value
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.container_min_replicas
    max_replicas = var.container_max_replicas

    container {
      name   = "control-plane-api"
      image  = local.control_plane_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "SERVICE_NAME"
        value = "control-plane-api"
      }

      env {
        name  = "SERVICE_PORT"
        value = "8000"
      }

      env {
        name  = "DEFAULT_TENANT_ID"
        value = var.default_tenant_id
      }

      env {
        name  = "TENANT_MODE"
        value = var.tenant_mode
      }

      dynamic "env" {
        for_each = var.enable_postgres ? [1] : []
        content {
          name        = "CONTROL_PLANE_DATABASE_URL"
          secret_name = "control-plane-database-url"
        }
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.this.connection_string
      }

      env {
        name  = "AZURE_STORAGE_ACCOUNT_NAME"
        value = azurerm_storage_account.this.name
      }

      env {
        name  = "AZURE_MANAGED_IDENTITY_CLIENT_ID"
        value = azurerm_user_assigned_identity.container_apps.client_id
      }

      dynamic "env" {
        for_each = var.enable_event_hubs ? [1] : []
        content {
          name  = "AZURE_EVENTHUB_NAME"
          value = azurerm_eventhub.prediction_audit[0].name
        }
      }

      dynamic "env" {
        for_each = var.enable_event_hubs ? [1] : []
        content {
          name  = "AZURE_EVENTHUB_FULLY_QUALIFIED_NAMESPACE"
          value = "${azurerm_eventhub_namespace.this[0].name}.servicebus.windows.net"
        }
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull]
}

resource "azurerm_container_app" "inference" {
  name                         = "${local.short_prefix}-infer-${random_string.suffix.result}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.container_apps.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.container_apps.id
  }

  ingress {
    external_enabled = true
    target_port      = 8001

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.container_min_replicas
    max_replicas = var.container_max_replicas

    container {
      name   = "inference-service"
      image  = local.inference_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "SERVICE_NAME"
        value = "inference-service"
      }

      env {
        name  = "SERVICE_PORT"
        value = "8001"
      }

      env {
        name  = "DEFAULT_TENANT_ID"
        value = var.default_tenant_id
      }

      env {
        name  = "TENANT_MODE"
        value = var.tenant_mode
      }

      env {
        name  = "CONTROL_PLANE_API_URL"
        value = local.control_plane_url
      }

      env {
        name  = "AZURE_MANAGED_IDENTITY_CLIENT_ID"
        value = azurerm_user_assigned_identity.container_apps.client_id
      }

      env {
        name  = "CLAIMS_RISK_FEATURE_VERSION"
        value = "claims-risk-features-v1"
      }

      dynamic "env" {
        for_each = var.claims_risk_model_uri != "" ? [1] : []
        content {
          name  = "CLAIMS_RISK_MODEL_URI"
          value = var.claims_risk_model_uri
        }
      }

      dynamic "env" {
        for_each = var.claims_risk_model_metadata_path != "" ? [1] : []
        content {
          name  = "CLAIMS_RISK_MODEL_METADATA_PATH"
          value = var.claims_risk_model_metadata_path
        }
      }

      env {
        name  = "INFERENCE_AUDIT_ENABLED"
        value = "true"
      }

      env {
        name  = "INFERENCE_MONITORING_ENABLED"
        value = "true"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.this.connection_string
      }

      dynamic "env" {
        for_each = var.enable_event_hubs ? [1] : []
        content {
          name  = "AZURE_EVENTHUB_NAME"
          value = azurerm_eventhub.prediction_audit[0].name
        }
      }

      dynamic "env" {
        for_each = var.enable_event_hubs ? [1] : []
        content {
          name  = "AZURE_EVENTHUB_FULLY_QUALIFIED_NAMESPACE"
          value = "${azurerm_eventhub_namespace.this[0].name}.servicebus.windows.net"
        }
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull]
}

resource "azurerm_container_app" "rag" {
  name                         = "${local.short_prefix}-rag-${random_string.suffix.result}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.container_apps.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.container_apps.id
  }

  ingress {
    external_enabled = true
    target_port      = 8002

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.container_min_replicas
    max_replicas = var.container_max_replicas

    container {
      name   = "rag-service"
      image  = local.rag_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "SERVICE_NAME"
        value = "rag-service"
      }

      env {
        name  = "SERVICE_PORT"
        value = "8002"
      }

      env {
        name  = "DEFAULT_TENANT_ID"
        value = var.default_tenant_id
      }

      env {
        name  = "TENANT_MODE"
        value = var.tenant_mode
      }

      env {
        name  = "CONTROL_PLANE_API_URL"
        value = local.control_plane_url
      }

      env {
        name  = "AZURE_MANAGED_IDENTITY_CLIENT_ID"
        value = azurerm_user_assigned_identity.container_apps.client_id
      }

      env {
        name  = "RAG_DOCS_DIR"
        value = "data/synthetic_docs"
      }

      env {
        name  = "RAG_LOCAL_INDEX_PATH"
        value = "data/local/rag-index.json"
      }

      env {
        name  = "RAG_AUDIT_ENABLED"
        value = "true"
      }

      env {
        name  = "AZURE_AI_SEARCH_ENDPOINT"
        value = "https://${azurerm_search_service.this.name}.search.windows.net"
      }

      env {
        name  = "AZURE_AI_SEARCH_INDEX_NAME"
        value = "careai-rag-chunks"
      }

      env {
        name  = "AZURE_AI_SEARCH_INDEX"
        value = "careai-rag-chunks"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.this.connection_string
      }

      dynamic "env" {
        for_each = var.enable_event_hubs ? [1] : []
        content {
          name  = "AZURE_EVENTHUB_NAME"
          value = azurerm_eventhub.prediction_audit[0].name
        }
      }

      dynamic "env" {
        for_each = var.enable_event_hubs ? [1] : []
        content {
          name  = "AZURE_EVENTHUB_FULLY_QUALIFIED_NAMESPACE"
          value = "${azurerm_eventhub_namespace.this[0].name}.servicebus.windows.net"
        }
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull]
}

resource "azurerm_container_app" "web_console" {
  name                         = "${local.short_prefix}-web-${random_string.suffix.result}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.container_apps.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.container_apps.id
  }

  ingress {
    external_enabled = true
    target_port      = 8080

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.container_min_replicas
    max_replicas = var.container_max_replicas

    container {
      name   = "web-console"
      image  = local.web_console_image
      cpu    = 0.25
      memory = "0.5Gi"
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull]
}
