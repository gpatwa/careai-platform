# Interview Storyboard

## 1. Platform Orientation

Show the local web console and explain the platform boundaries: control plane, inference, RAG, metadata store, cache, experiment tracking, and storage.

## 2. MLOps Walkthrough

Describe how synthetic healthcare-like claims data flows from deterministic generation into training, experiment tracking, model registry metadata, promotion, deployment, inference, monitoring, and rollback.

## 3. LLMOps Walkthrough

Describe synthetic document ingestion, chunking, embeddings, Azure AI Search vector/hybrid retrieval, prompt registry, RAG responses, evaluations, safety checks, and audit logging.

## 4. Governance

Call out RBAC placeholders, audit events, lineage, reproducibility metadata, data-quality checks, drift monitoring, responsible AI checks, and human-in-the-loop flags. Show a production promotion blocked by missing governance controls, then add an approved model card and approval decision to unblock it. For RAG, show that production prompt selection requires an approved prompt card.

## 5. Azure Deployment

Explain how Dockerized services move to Azure Container Registry and Azure Container Apps, with Key Vault for secrets, Log Analytics/Application Insights for observability, and Terraform for infrastructure.
