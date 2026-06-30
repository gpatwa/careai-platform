# Final Architecture Review

## What Was Implemented

`careai-platform` is a local-first monorepo for a synthetic healthcare-style MLOps and LLMOps platform that can be explained and demonstrated in a Senior Manager AI/ML Engineering system design interview.

Implemented platform areas:

- Control plane API for datasets, model artifacts, deployments, prompt templates, evaluations, approvals, audit events, prediction events, error events, drift snapshots, model cards, and prompt cards.
- Bounded cross-service workflow runtime for Payment Integrity cases: deterministic allowlisted planning, evidence verification, one policy-retrieval retry, persisted loop history, and human-review handoffs.
- Synthetic claims-risk ML pipeline with deterministic data generation, scikit-learn training, MLflow logging, metrics, segment metrics, lineage metadata, baseline feature distributions, and optional control-plane registration.
- Inference service with Pydantic feature validation, feature freshness and missingness checks, safe prediction responses, reason codes, correlation IDs, fallback scoring, audit events, prediction monitoring events, and champion/challenger traffic-split metadata.
- Monitoring APIs and drift job with deterministic PSI-style checks, SLO-oriented error and latency summaries, rollback recommendation metadata, and event-consumer hooks.
- Synthetic document ingestion pipeline with chunking, metadata, role filters, deterministic local embeddings, local JSON vector index fallback, and Azure AI Search integration behind configuration.
- RAG service with role-filtered retrieval, prompt registry fallback/control-plane lookup, Azure OpenAI or local mock provider, citations, safety checks, groundedness heuristics, audit logs, and `rag.query_answered` events.
- RAG evaluation pipeline with a 20-item synthetic eval set, retrieval/citation/relevance/groundedness/safety/latency metrics, JSON reports, thresholds, and optional control-plane `EvaluationRun` registration.
- React/Vite web console for overview, models, deployments, monitoring, RAG, governance, and audit views with mock fallback data.
- Dockerfiles for all runnable services and Docker Compose for local PostgreSQL, Redis, MLflow, Azurite, APIs, RAG, inference, and web console.
- Terraform for Azure Container Registry, Container Apps, Log Analytics, Application Insights, Key Vault, Storage, Azure AI Search, Event Hubs, optional PostgreSQL, optional Redis, and optional Azure ML.
- GitHub Actions for CI and manual Azure Container Apps deployment.
- OpenTelemetry hooks, structured JSON logging, event publisher abstractions, local event stream fallback, and Azure Event Hubs support.
- Optional AKS Helm chart that renders the four app services without secrets.
- End-to-end local demo and Azure smoke-test scripts under `scripts/`.

Supporting architecture and deployment docs:

- [System architecture](diagrams/system_architecture.md)
- [Data flow](diagrams/data_flow.md)
- [Azure network architecture](diagrams/azure_network_architecture.md)
- [Local deployment runbook](deployment/local_deployment.md)
- [Azure deployment runbook](deployment/azure_deployment_runbook.md)
- [Artifact deployment wiring](artifact_deployment_wiring.md)

## What Is Intentionally Mocked

The demo is intentionally synthetic and uses safe local fallbacks:

- No real PHI, PII, member, patient, claims, provider, employer, payer, or clinical data is included.
- The claims-risk model predicts a synthetic label from synthetic aggregate features only.
- Inference can fall back to deterministic rules when no model artifact is configured.
- Champion/challenger routing currently simulates selection metadata while using the active loaded scorer or fallback scorer.
- Human approvals, RBAC, model cards, prompt cards, and governance gates are platform metadata controls, not integrations with an enterprise IAM/GRC system.
- RAG generation defaults to a deterministic local mock provider unless Azure OpenAI chat configuration is present.
- Local retrieval uses deterministic embeddings and a JSON vector index unless Azure AI Search and Azure OpenAI embeddings are configured.
- Drift, safety, groundedness, and quality metrics are lightweight deterministic heuristics intended for system design explanation.
- Rollback recommendation is metadata-driven and threshold-based; automated rollback execution is represented by API and runbook controls.
- The workflow planner is deterministic custom code, not LangGraph or an LLM planner. It has bounded retries and review handoffs, but not queue-backed scheduling or full distributed-workflow semantics.
- Terraform uses public endpoints for optional PostgreSQL/Redis in the low-friction demo path; private networking is a production next step.

## How To Deploy To Azure

Default deployment target: Azure Container Apps.

1. Prepare local tooling:

   ```bash
   az login
   cd infra/terraform
   terraform init
   terraform fmt -check
   terraform validate
   ```

2. Configure `terraform.tfvars` from `terraform.tfvars.example`. Keep real environment-specific values out of git.

3. Bootstrap the resource group and ACR if needed:

   ```bash
   terraform apply \
     -target=azurerm_resource_group.this \
     -target=azurerm_container_registry.this
   ```

4. Build and push initial `latest` images to ACR. The GitHub deployment workflow is intended for subsequent app updates after Container Apps exist.

5. Apply the full Terraform stack:

   ```bash
   terraform plan -out tfplan
   terraform apply tfplan
   ```

6. Configure GitHub repository variables and secrets from Terraform outputs, then run the manual `deploy-azure-container-apps` workflow. The workflow rebuilds the web console with the deployed API URLs and deploys commit-tagged images.

7. Run deployed smoke tests:

   ```bash
   CONTROL_PLANE_URL=https://<control-plane-app> \
   INFERENCE_URL=https://<inference-app> \
   RAG_URL=https://<rag-app> \
   WEB_CONSOLE_URL=https://<web-console-app> \
   scripts/demo_azure_smoke_test.sh
   ```

Optional AKS extension:

```bash
helm template careai-platform infra/helm/optional-aks
```

## Limitations

- This is an interview-grade platform demo, not a regulated production system.
- There is no real identity provider, fine-grained RBAC engine, secrets rotation workflow, or production data access layer.
- Database migrations exist for the demo schema, but production would need a stronger migration/release process, backups, restores, and rollback rehearsals.
- Model registry metadata is stored in the control plane while MLflow tracks experiments; production would define a single source of truth for model/package promotion.
- Inference model loading supports a single active artifact path/URI plus simulated traffic selection; production champion/challenger serving would isolate artifacts, metrics, and rollback paths per revision.
- RAG safety checks are deterministic guardrails and do not replace enterprise content safety, medical policy, legal review, or human oversight.
- Azure AI Search and Azure OpenAI integrations require real Azure resources and credentials; tests run without those credentials by design.
- Terraform state can contain generated optional PostgreSQL credentials when PostgreSQL is enabled; production needs protected remote state and strict RBAC.
- Container Apps use simple scaling and public ingress for the demo; production would add private networking, managed identities for more data-plane integrations, WAF/API gateway controls, and environment-specific policies.
- Terraform provisions storage and search but does not publish a trained model bundle to Blob Storage, ingest RAG documents into Azure AI Search, or create a scheduled planner job.

## Next Production Steps

- Add Entra ID authentication, authorization policies, and role-to-action enforcement across APIs and UI.
- Move all runtime secrets to Key Vault references or managed identity flows; remove API-key-based Search/OpenAI paths where possible.
- Add private networking, VNet integration, private endpoints, API gateway/WAF, and environment isolation.
- Split champion and challenger model loading into distinct runtime artifacts and emit per-route SLO metrics.
- Add scheduled drift jobs, background evaluation jobs, retraining triggers, and alert-to-incident workflows.
- Add a queue-backed/Container Apps Job workflow scheduler with idempotency, retries, and dead-letter handling; only then consider a structured, policy-gated LLM planner.
- Add richer data-quality validation, schema registry checks, model explainability artifacts, and fairness review workflows.
- Promote RAG evaluations to a stronger eval harness with human review queues, regression baselines, and prompt/version approval workflows.
- Add remote Terraform state, policy-as-code, container vulnerability scanning, SBOM generation, image signing, and release approvals.
- Add load tests, failure-injection tests, restore drills, and runbooks for rollback, degraded mode, and incident response.
- Add screenshots or a short recorded walkthrough after running `scripts/demo_local.sh` for interview prep.
