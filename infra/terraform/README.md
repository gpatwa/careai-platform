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
| `location` | Azure region for shared foundation resources. | `eastus` |
| `container_apps_location` | Azure region for the Container Apps environment. | `westus2` |
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

For a fresh environment, bootstrap the resource group and ACR first so images can be pushed before Container Apps are created:

```bash
terraform apply \
  -target=azurerm_resource_group.this \
  -target=azurerm_container_registry.this
```

## Build And Push Images

Push images using the `acr_login_server` output:

```bash
ACR_LOGIN_SERVER="$(terraform output -raw acr_login_server)"
az acr login --name "${ACR_LOGIN_SERVER%%.azurecr.io}"

docker build --platform linux/amd64 -f ../../apps/control-plane-api/Dockerfile -t "$ACR_LOGIN_SERVER/control-plane-api:latest" ../..
docker build --platform linux/amd64 -f ../../apps/inference-service/Dockerfile -t "$ACR_LOGIN_SERVER/inference-service:latest" ../..
docker build --platform linux/amd64 -f ../../apps/rag-service/Dockerfile -t "$ACR_LOGIN_SERVER/rag-service:latest" ../..
docker build \
  --platform linux/amd64 \
  -f ../../apps/web-console/Dockerfile \
  --build-arg VITE_CONTROL_PLANE_API_URL="${VITE_CONTROL_PLANE_API_URL:-http://localhost:8000}" \
  --build-arg VITE_RAG_SERVICE_URL="${VITE_RAG_SERVICE_URL:-http://localhost:8002}" \
  -t "$ACR_LOGIN_SERVER/web-console:latest" \
  ../../apps/web-console

docker push "$ACR_LOGIN_SERVER/control-plane-api:latest"
docker push "$ACR_LOGIN_SERVER/inference-service:latest"
docker push "$ACR_LOGIN_SERVER/rag-service:latest"
docker push "$ACR_LOGIN_SERVER/web-console:latest"
```

The explicit `linux/amd64` platform matters on Apple Silicon macOS. Terraform deploys image tags from ACR, but Docker decides the image CPU architecture at build time. Building with `--platform linux/amd64` prevents an ARM-only local image from being pushed to Azure Container Apps.

Then deploy the full stack:

```bash
terraform plan -out tfplan
terraform apply tfplan
```

The Vite web console reads API URLs at image build time. For a polished Azure-hosted UI, either run the GitHub Actions deployment after the first full Terraform apply, or rebuild the web image with the Container Apps URLs from `terraform output -json container_apps_urls`, update `container_image_tags.web_console`, and apply again.

The first deployment has a small bootstrap loop because Container Apps need images and the web image benefits from final service URLs:

1. Apply only the resource group and ACR.
2. Push initial `latest` images.
3. Run the full Terraform apply to create Container Apps and supporting Azure resources.
4. Run the GitHub Actions deployment once. It resolves Container App URLs before building the web console and redeploys all images with a commit-based tag.

## Outputs

Terraform outputs:

- `acr_login_server`
- `container_apps_names`
- `container_apps_urls`
- `azure_ai_search_endpoint`
- `storage_account_name`
- `event_hubs_namespace`
- `event_hubs_fully_qualified_namespace`
- `event_hub_name`
- optional `postgres_fqdn`
- optional `redis_hostname`
- optional `azure_ml_workspace_name`

## GitHub Actions Deployment

After Terraform has created the Azure resources, use `.github/workflows/deploy-azure-container-apps.yml` to build images, push to ACR, update Container Apps, and run smoke tests.

The workflow is configured for GitHub OpenID Connect, with a documented `AZURE_CREDENTIALS` service-principal fallback if OIDC is unavailable. Create an Entra ID app registration or managed identity with federated credentials for this repository, then grant it permissions to push images and update Container Apps. Minimum practical roles for the demo resource group:

- `Contributor` on the resource group.
- `AcrPush` on the Azure Container Registry.

Create GitHub repository variables:

```bash
terraform output -raw resource_group_name
terraform output -raw acr_login_server
terraform output -json container_apps_names
terraform output -json container_apps_urls
terraform output -raw azure_ai_search_endpoint
terraform output -raw event_hubs_fully_qualified_namespace
terraform output -raw event_hub_name
```

| GitHub variable | Value |
| --- | --- |
| `AZURE_CLIENT_ID` | Federated credential client ID. |
| `AZURE_TENANT_ID` | Azure tenant ID. |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID. |
| `AZURE_RESOURCE_GROUP` | Terraform `resource_group_name`. |
| `ACR_LOGIN_SERVER` | Terraform `acr_login_server`. |
| `CONTROL_PLANE_APP_NAME` | `container_apps_names.control_plane_api`. |
| `INFERENCE_APP_NAME` | `container_apps_names.inference_service`. |
| `RAG_APP_NAME` | `container_apps_names.rag_service`. |
| `WEB_CONSOLE_APP_NAME` | `container_apps_names.web_console`. |
| `CONTROL_PLANE_URL` | `container_apps_urls.control_plane_api`. |
| `INFERENCE_URL` | `container_apps_urls.inference_service`. |
| `RAG_URL` | `container_apps_urls.rag_service`. |
| `WEB_CONSOLE_URL` | `container_apps_urls.web_console`; used for API CORS. |
| `AZURE_AI_SEARCH_ENDPOINT` | Terraform `azure_ai_search_endpoint`, when using Azure AI Search. |
| `AZURE_AI_SEARCH_INDEX` | Search index name, usually `careai-rag-chunks`. |
| `AZURE_OPENAI_ENDPOINT` | Optional Azure OpenAI endpoint. |
| `AZURE_OPENAI_DEPLOYMENT` | Optional shared Azure OpenAI deployment fallback. |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Optional Azure OpenAI chat deployment. Falls back to `AZURE_OPENAI_DEPLOYMENT`. |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Optional Azure OpenAI embedding deployment. Falls back to `AZURE_OPENAI_DEPLOYMENT`. |
| `AZURE_EVENTHUB_NAME` | Terraform `event_hub_name`, usually `prediction-audit-events`. |
| `AZURE_EVENTHUB_FULLY_QUALIFIED_NAMESPACE` | Terraform `event_hubs_fully_qualified_namespace` for managed-identity Event Hubs publishing. |

Create GitHub repository secrets when those integrations are enabled:

| GitHub secret | Notes |
| --- | --- |
| `DATABASE_URL` | Optional database URL. Maps to `DATABASE_URL` and `CONTROL_PLANE_DATABASE_URL`. |
| `REDIS_URL` | Optional Redis URL. |
| `AZURE_AI_SEARCH_API_KEY` | Optional until the app supports managed identity data-plane auth for Search. |
| `AZURE_OPENAI_API_KEY` | Optional; omitted values keep RAG in local mock mode. |
| `AZURE_EVENTHUB_CONNECTION_STRING` | Optional fallback for Event Hubs publishing when managed identity is not used. Prefer the namespace variable plus RBAC. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Optional Application Insights connection string. |

Run the workflow from the GitHub Actions tab. It accepts an optional `image_tag`; when omitted it deploys the commit SHA. The workflow stores runtime configuration as Container App secrets and references them from environment variables. If Azure OpenAI is not configured, the RAG smoke test uses the local deterministic mock provider.

Azure AI Search and Azure OpenAI are intentionally configuration-gated. Terraform provisions Azure AI Search and gives the Container Apps identity Search RBAC, but the current application client uses API-key auth for the Search data plane. Set `AZURE_AI_SEARCH_API_KEY` plus an embedding provider to use Azure-backed retrieval; otherwise the RAG service uses the local JSON vector index fallback.

For durable Azure control-plane metadata, set `enable_postgres = true` or provide a `DATABASE_URL` secret that points at a managed PostgreSQL instance. Without that configuration, the control plane can still run for a smoke demo, but container-local SQLite state should be treated as ephemeral.

If OpenID Connect is not available in your organization, create a service principal scoped to the demo resource group and store its JSON credentials in the `AZURE_CREDENTIALS` GitHub secret. The deployment workflow will use that secret automatically when the OIDC variables are not set. OIDC is still preferred because it avoids long-lived cloud credentials in GitHub.

The default split keeps shared foundation resources in `eastus` and the Container Apps environment in `westus2` so the demo can usually avoid the regional capacity issue that showed up during deployment. If your subscription still hits a regional capacity or offer restriction, rerun Terraform with another Container Apps region such as `centralus` or `westus3`.

The workflow is manual-only by default to avoid accidental Azure spend. To deploy on every push to `main`, add a `push` trigger after the environment is stable.

## Security Notes

- No real secrets are committed.
- A user-assigned managed identity pulls images from ACR and receives scoped RBAC for Storage, Key Vault, Azure AI Search, and Event Hubs.
- ACR admin access is disabled.
- Storage containers are private and shared account keys are enabled only so Terraform can provision and wait on the data plane reliably; runtime access should still use managed identity.
- Optional PostgreSQL currently uses public Azure service access for a low-friction demo. For production, use private networking, managed identities or Entra authentication where supported, state encryption, and a remote backend with strict RBAC.
