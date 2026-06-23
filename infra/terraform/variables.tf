variable "environment" {
  description = "Deployment environment name used in Azure resource names."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?$", var.environment))
    error_message = "environment must be 2-12 characters, contain only lowercase letters, numbers, and hyphens, and start and end with a letter or number."
  }
}

variable "location" {
  description = "Azure region for persistent and shared foundation resources."
  type        = string
  default     = "eastus"
}

variable "container_apps_location" {
  description = "Azure region for the Container Apps environment."
  type        = string
  default     = "westus2"
}

variable "resource_prefix" {
  description = "Short lowercase prefix for Azure resource names."
  type        = string
  default     = "careai"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{1,14}[a-z0-9])?$", var.resource_prefix))
    error_message = "resource_prefix must be 3-16 characters, contain only lowercase letters, numbers, and hyphens, and start and end with a letter or number."
  }
}

variable "tags" {
  description = "Tags applied to Azure resources."
  type        = map(string)
  default = {
    project     = "careai-platform"
    data_policy = "synthetic-only"
  }
}

variable "container_image_tags" {
  description = "Image tags deployed from Azure Container Registry for each service."
  type = object({
    control_plane_api = string
    inference_service = string
    rag_service       = string
    web_console       = string
  })
  default = {
    control_plane_api = "latest"
    inference_service = "latest"
    rag_service       = "latest"
    web_console       = "latest"
  }
}

variable "enable_postgres" {
  description = "Create Azure Database for PostgreSQL Flexible Server and wire the control plane to it."
  type        = bool
  default     = false
}

variable "enable_redis" {
  description = "Create Azure Cache for Redis. Disabled by default to avoid unnecessary demo cost."
  type        = bool
  default     = false
}

variable "enable_azure_ml" {
  description = "Create an optional Azure Machine Learning workspace for model registry and MLflow integration."
  type        = bool
  default     = false
}

variable "enable_event_hubs" {
  description = "Create Event Hubs namespace and prediction/audit event hub."
  type        = bool
  default     = true
}

variable "postgres_sku_name" {
  description = "SKU for optional PostgreSQL Flexible Server."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "redis_sku_name" {
  description = "SKU for optional Azure Cache for Redis."
  type        = string
  default     = "Basic"
}

variable "azure_ai_search_sku" {
  description = "Azure AI Search SKU. Use free only when the subscription has no existing free search service."
  type        = string
  default     = "basic"
}

variable "container_min_replicas" {
  description = "Minimum replicas for each Container App."
  type        = number
  default     = 0
}

variable "container_max_replicas" {
  description = "Maximum replicas for each Container App."
  type        = number
  default     = 3
}
