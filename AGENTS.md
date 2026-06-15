# AGENTS.md

## Project Goal

`careai-platform` is a production-style local-first monorepo for demonstrating enterprise MLOps and LLMOps platform design for healthcare-style workflows using synthetic data only. The platform should be able to run locally for interview demos and deploy to Azure using containerized services and infrastructure as code.

The target architecture demonstrates:

- MLOps lifecycle: synthetic data generation, training, experiment tracking, model registry metadata, promotion, deployment, inference, monitoring, and rollback.
- LLMOps lifecycle: document ingestion, chunking, embeddings, Azure AI Search vector and hybrid retrieval, RAG APIs, prompt registry, evaluations, safety checks, and audit logging.
- Azure deployment: Azure Container Registry, Azure Container Apps, Log Analytics / Application Insights, Azure AI Search, Event Hubs, Key Vault, Storage Account, PostgreSQL, Redis, and optional Azure ML workspace.
- Healthcare-grade governance patterns without real PHI: RBAC placeholders, audit trails, lineage, reproducibility, responsible AI checks, data-quality checks, drift monitoring, and human-in-the-loop flags.

## Safety Rules

- Use synthetic healthcare-like data only.
- Never commit secrets, credentials, tokens, private keys, connection strings, or real environment files.
- Use `.env.example` for configuration documentation.
- Do not log raw PHI, PII, or PHI/PII-like values, even when synthetic.
- Do not include real patient data.
- Do not include Optum, UHG, customer, employer, or proprietary branding.
- Prefer deterministic, testable code.
- Prefer explicit seed values for generated data, experiments, tests, and demos.
- Redact sensitive-looking values in logs, traces, screenshots, docs, and test fixtures.

## Coding Standards

- Use Python 3.11+ for backend services, data workflows, ML pipelines, and automation.
- Use FastAPI for HTTP services.
- Use Pydantic for request, response, configuration, and domain schemas.
- Use SQLAlchemy or SQLModel for persistence.
- Use Pytest for tests.
- Use structured JSON logging for services and jobs.
- Add Dockerfiles for every runnable service.
- Keep modules small, typed, and easy to test.
- Favor dependency injection or explicit configuration over hidden global state.
- Keep demo behavior reproducible with fixed seeds, clear inputs, and documented outputs.
- Validate inputs at boundaries and return safe, interview-friendly error messages.

## Frontend Standards

- Use TypeScript.
- Use React/Vite or Next.js.
- Keep the UI simple, credible, and interview-demo friendly.
- Favor clear operational workflows over marketing-style pages.
- Show system state, lineage, audit events, evaluation results, monitoring signals, and human review flags plainly.
- Avoid storing or displaying raw PHI/PII-like values.

## Azure Deployment Standards

- Put Terraform under `infra/terraform`.
- Put GitHub Actions workflows under `.github/workflows`.
- Use Azure Container Registry and Azure Container Apps as the default deployment path.
- Use Log Analytics and Application Insights for observability.
- Use Key Vault references for secrets and managed configuration.
- Use Azure AI Search for vector and hybrid retrieval.
- Use PostgreSQL for relational metadata and Redis for cache or queue acceleration where needed.
- Use Event Hubs for event streaming and monitoring signals where appropriate.
- Keep AKS and Helm as optional extensions, not the default deployment path.
- Keep Azure ML workspace integration optional unless the feature specifically requires it.

## Required Commands

The repository should expose these commands through `make`:

```bash
make setup
make test
make lint
make docker-build
make local-up
make local-down
```

Expected meanings:

- `make setup`: install local development dependencies and prepare environment files.
- `make test`: run the test suite.
- `make lint`: run formatting, linting, and static checks.
- `make docker-build`: build all service containers.
- `make local-up`: start the local demo stack.
- `make local-down`: stop the local demo stack.

## Agent Workflow

Before coding:

1. Inspect the repository structure and existing conventions.
2. Read relevant docs, Makefiles, package files, service code, tests, and infrastructure before editing.
3. Identify whether a change affects MLOps, LLMOps, governance, frontend, deployment, or shared contracts.

While coding:

1. Make small coherent changes.
2. Keep changes scoped to the requested behavior.
3. Add or update tests for every feature.
4. Use deterministic synthetic test data.
5. Preserve existing user changes and avoid unrelated refactors.
6. Update `.env.example` when configuration changes.
7. Update README and architecture docs when behavior, commands, services, or deployment shape changes.

Before finishing:

1. Run relevant tests and lint checks when available.
2. Check generated files for accidental secrets or raw PHI/PII-like values.
3. Confirm Docker, local, or deployment commands are documented when touched.
4. End each task with a concise summary of files changed, tests run, and remaining risks.

