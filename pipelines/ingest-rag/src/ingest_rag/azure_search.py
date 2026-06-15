import os
from dataclasses import asdict
from typing import Any

import httpx

from ingest_rag.models import ChunkRecord

DEFAULT_SEARCH_API_VERSION = "2026-04-01"
DEFAULT_INDEX_NAME = "careai-rag-chunks"


class AzureAISearchClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        index_name: str = DEFAULT_INDEX_NAME,
        api_version: str = DEFAULT_SEARCH_API_VERSION,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.index_name = index_name
        self.api_version = api_version

    @classmethod
    def from_env(cls) -> "AzureAISearchClient | None":
        endpoint = os.getenv("AZURE_AI_SEARCH_ENDPOINT")
        api_key = os.getenv("AZURE_AI_SEARCH_API_KEY")
        if not endpoint or not api_key:
            return None
        return cls(
            endpoint=endpoint,
            api_key=api_key,
            index_name=os.getenv("AZURE_AI_SEARCH_INDEX_NAME", DEFAULT_INDEX_NAME),
            api_version=os.getenv("AZURE_AI_SEARCH_API_VERSION", DEFAULT_SEARCH_API_VERSION),
        )

    def _headers(self) -> dict[str, str]:
        return {"api-key": self.api_key, "content-type": "application/json"}

    def _url(self, path: str) -> str:
        separator = "&" if "?" in path else "?"
        return f"{self.endpoint}{path}{separator}api-version={self.api_version}"

    def index_schema(self, embedding_dimension: int) -> dict[str, Any]:
        return {
            "name": self.index_name,
            "fields": [
                {
                    "name": "id",
                    "type": "Edm.String",
                    "key": True,
                    "filterable": True,
                    "retrievable": True,
                },
                {
                    "name": "doc_id",
                    "type": "Edm.String",
                    "filterable": True,
                    "retrievable": True,
                },
                {
                    "name": "chunk_id",
                    "type": "Edm.String",
                    "filterable": True,
                    "retrievable": True,
                },
                {
                    "name": "title",
                    "type": "Edm.String",
                    "searchable": True,
                    "filterable": True,
                    "sortable": True,
                    "retrievable": True,
                },
                {
                    "name": "version",
                    "type": "Edm.String",
                    "filterable": True,
                    "retrievable": True,
                },
                {
                    "name": "sensitivity_class",
                    "type": "Edm.String",
                    "filterable": True,
                    "retrievable": True,
                },
                {
                    "name": "source_uri",
                    "type": "Edm.String",
                    "filterable": True,
                    "retrievable": True,
                },
                {
                    "name": "allowed_roles",
                    "type": "Collection(Edm.String)",
                    "filterable": True,
                    "retrievable": True,
                },
                {
                    "name": "content",
                    "type": "Edm.String",
                    "searchable": True,
                    "retrievable": True,
                    "analyzer": "en.microsoft",
                },
                {
                    "name": "content_vector",
                    "type": "Collection(Edm.Single)",
                    "searchable": True,
                    "retrievable": False,
                    "stored": False,
                    "dimensions": embedding_dimension,
                    "vectorSearchProfile": "content-vector-profile",
                },
            ],
            "vectorSearch": {
                "algorithms": [
                    {
                        "name": "content-hnsw",
                        "kind": "hnsw",
                        "hnswParameters": {
                            "m": 4,
                            "efConstruction": 400,
                            "efSearch": 500,
                            "metric": "cosine",
                        },
                    }
                ],
                "profiles": [
                    {
                        "name": "content-vector-profile",
                        "algorithm": "content-hnsw",
                    }
                ],
            },
        }

    def create_or_update_index(self, embedding_dimension: int) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            response = client.put(
                self._url(f"/indexes/{self.index_name}?allowIndexDowntime=true"),
                headers=self._headers(),
                json=self.index_schema(embedding_dimension),
            )
            response.raise_for_status()
            return dict(response.json())

    def upload_chunks(self, chunks: list[ChunkRecord]) -> dict[str, Any]:
        documents = []
        for chunk in chunks:
            document = asdict(chunk)
            document["@search.action"] = "upload"
            documents.append(document)

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                self._url(f"/indexes/{self.index_name}/docs/index"),
                headers=self._headers(),
                json={"value": documents},
            )
            response.raise_for_status()
            return dict(response.json())

    def search(
        self,
        *,
        query: str,
        query_vector: list[float],
        allowed_role: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "search": query,
            "top": top_k,
            "select": (
                "id,doc_id,chunk_id,title,version,sensitivity_class,"
                "source_uri,allowed_roles,content"
            ),
            "vectorQueries": [
                {
                    "kind": "vector",
                    "vector": query_vector,
                    "fields": "content_vector",
                    "k": top_k,
                }
            ],
        }
        if allowed_role:
            safe_role = allowed_role.replace("'", "''")
            payload["filter"] = f"allowed_roles/any(role: role eq '{safe_role}')"

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                self._url(f"/indexes/{self.index_name}/docs/search"),
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return dict(response.json())
