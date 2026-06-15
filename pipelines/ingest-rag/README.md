# ingest-rag

Synthetic document ingestion pipeline for the `careai-platform` LLMOps demo. It loads healthcare-operations policy documents, chunks them, embeds each chunk, and writes either an Azure AI Search vector index or a local JSON vector index fallback.

No real patient data, PHI, PII, credentials, or proprietary policy content is used.

## Local Ingestion

```bash
python -m ingest_rag.ingest \
  --input-dir data/synthetic_docs \
  --output data/local/rag-index.json \
  --force-local
```

The local fallback writes `data/local/rag-index.json`, which is ignored by git. It uses deterministic hash-based embeddings so tests and demos are reproducible without Azure credentials.

## Azure AI Search Ingestion

Set these values in your local environment or deployment secret store:

```bash
export AZURE_AI_SEARCH_ENDPOINT=https://<search-service>.search.windows.net
export AZURE_AI_SEARCH_API_KEY=<admin-or-index-key>
export AZURE_AI_SEARCH_INDEX_NAME=careai-rag-chunks
export AZURE_OPENAI_ENDPOINT=https://<azure-openai-resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=<embedding-key>
export AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<embedding-deployment>
```

Then run:

```bash
python -m ingest_rag.ingest --input-dir data/synthetic_docs
```

If Azure AI Search env vars are present, the pipeline creates or updates the index and uploads chunks. If they are absent, it writes the local JSON index.

## Index Schema

The Azure AI Search index contains:

- `id`: chunk key.
- `doc_id`, `chunk_id`, `title`, `version`, `sensitivity_class`, `source_uri`.
- `allowed_roles`: `Collection(Edm.String)` used for role filters.
- `content`: searchable plain text for keyword and hybrid retrieval.
- `content_vector`: `Collection(Edm.Single)` vector field with HNSW cosine search.

## Chunking Strategy

Markdown documents are split by paragraph into approximately 900-character chunks with 150-character overlap. Chunk IDs are deterministic from document ID, chunk index, and content hash.

## Role-Based Retrieval

Azure queries include a filter such as:

```text
allowed_roles/any(role: role eq 'member_support')
```

The local fallback applies the same role filter before scoring. This demonstrates document-level access control before context is passed to a RAG prompt.
