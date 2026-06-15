# Azure Terraform Deployment

This directory defines the default Azure deployment path for `careai-platform` using Azure Container Registry and Azure Container Apps. It is designed for interview demos and uses synthetic data only.

## Resources

- Resource group
- Azure Container Registry
- Azure Container Apps environment
- Container Apps for `control-plane-api`, `inference-service`, `rag-service`, and `web-console`
- Log Analytics workspace
- Application Insights
- Key Vault with RBAC enabled
- Storage Account with private containers for `artifacts`, `datasets`, and `eval-reports`
- Azure AI Search
- Event Hubs namespace and `prediction-audit-events` hub when `enable_event_hubs = true`
- Azure Cache for Redis when `enable_redis = true`
- Azure Database for PostgreSQL Flexible Server when `enable_postgres = true`
- Azure Machine Learning workspace when `enable_azure_ml = true`

## Prerequisites

Install:

- Azure CLI
- Terraform 1.6+
- Docker

Sign in and choose a subscription:

```bash
az login
az account set --subscription "<subscription-id>"
```

## Configure

Create a local variable file from the example:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Update `terraform.tfvars` for the target environment. Do not commit `terraform.tfvars`; it may contain environment-specific values.

Key variables:

| Variable | Description | Default |
| --- | --- | --- |
| `environment` | Short environment name used in resource names. | `dev` |
| `location` | Azure region. | `eastus` |
| `resource_prefix` | Short lowercase prefix for resources. | `careai` |
| `tags` | Map of governance and ownership tags. | synthetic-only demo tags |
| `container_image_tags` | A tag per service image in ACR. | `latest` |
| `enable_postgres` | Create PostgreSQL Flexible Server and wire the control plane DB URL. | `false` |
| `enable_redis` | Create Azure Cache for Redis. | `false` |
| `enable_azure_ml` | Create Azure ML workspace for optional registry/MLflow integration. | `false` |
| `enable_event_hubs` | Create Event Hubs namespace and event hub. | `true` |
| `azure_ai_search_sku` | Azure AI Search SKU. | `basic` |

PostgreSQL, Redis, and Azure ML are optional because they can add cost. When PostgreSQL is enabled, Terraform generates an admin password and stores it in Terraform state; keep state in a protected backend before using this beyond a demo.

## Deploy

Initialize and validate Terraform:

```bash
terraform init
terraform fmt -check
terraform validate
```

Plan and apply:

```bash
terraform plan -out tfplan
terraform apply tfplan
```

## Build And Push Images

After the first apply creates ACR, push images using the `acr_login_server` output:

```bash
ACR_LOGIN_SERVER="$(terraform output -raw acr_login_server)"
az acr login --name "${ACR_LOGIN_SERVER%%.azurecr.io}"

docker build -f ../../apps/control-plane-api/Dockerfile -t "$ACR_LOGIN_SERVER/control-plane-api:latest" ../..
docker build -f ../../apps/inference-service/Dockerfile -t "$ACR_LOGIN_SERVER/inference-service:latest" ../..
docker build -f ../../apps/rag-service/Dockerfile -t "$ACR_LOGIN_SERVER/rag-service:latest" ../..
docker build -f ../../apps/web-console/Dockerfile -t "$ACR_LOGIN_SERVER/web-console:latest" ../../apps/web-console

docker push "$ACR_LOGIN_SERVER/control-plane-api:latest"
docker push "$ACR_LOGIN_SERVER/inference-service:latest"
docker push "$ACR_LOGIN_SERVER/rag-service:latest"
docker push "$ACR_LOGIN_SERVER/web-console:latest"
```

Run `terraform apply` again after pushing images if the initial Container Apps revisions were waiting on images.

## Outputs

Terraform outputs:

- `acr_login_server`
- `container_apps_urls`
- `azure_ai_search_endpoint`
- `storage_account_name`
- `event_hubs_namespace`
- `event_hub_name`
- optional `postgres_fqdn`
- optional `redis_hostname`
- optional `azure_ml_workspace_name`

## Security Notes

- No real secrets are committed.
- A user-assigned managed identity pulls images from ACR and receives scoped RBAC for Storage, Key Vault, Azure AI Search, and Event Hubs.
- ACR admin access is disabled.
- Storage containers are private and shared account keys are disabled.
- Optional PostgreSQL currently uses public Azure service access for a low-friction demo. For production, use private networking, managed identities or Entra authentication where supported, state encryption, and a remote backend with strict RBAC.
