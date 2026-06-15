import hashlib
import math
import os
import re
from abc import ABC, abstractmethod

import httpx


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class LocalDeterministicEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 64) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be greater than zero")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[a-z0-9_]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 8) for value in vector]


class AzureOpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-02-01",
        dimension: int = 1536,
        requested_dimensions: int | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version
        self._dimension = dimension
        self.requested_dimensions = requested_dimensions

    @classmethod
    def from_env(cls) -> "AzureOpenAIEmbeddingProvider | None":
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        if not endpoint or not api_key or not deployment:
            return None

        requested_dimensions = os.getenv("AZURE_OPENAI_EMBEDDING_REQUESTED_DIMENSIONS")
        dimension = int(os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS", "1536"))
        return cls(
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            dimension=dimension,
            requested_dimensions=(int(requested_dimensions) if requested_dimensions else None),
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        payload: dict[str, object] = {"input": texts}
        if self.requested_dimensions is not None:
            payload["dimensions"] = self.requested_dimensions

        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}/embeddings"
            f"?api-version={self.api_version}"
        )
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                headers={"api-key": self.api_key, "content-type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        rows = sorted(body["data"], key=lambda item: item["index"])
        embeddings = [list(map(float, row["embedding"])) for row in rows]
        if embeddings:
            self._dimension = len(embeddings[0])
        return embeddings


def embedding_provider_from_env() -> EmbeddingProvider:
    return AzureOpenAIEmbeddingProvider.from_env() or LocalDeterministicEmbeddingProvider()
