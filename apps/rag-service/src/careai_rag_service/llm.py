import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from careai_rag_service.schemas import PromptTemplate, RetrievedChunk


@dataclass(frozen=True)
class LLMResponse:
    answer: str
    provider: str
    model_name: str
    fallback_mode: bool = False


class LLMProvider(ABC):
    @abstractmethod
    def generate_answer(
        self,
        *,
        question: str,
        prompt: PromptTemplate,
        retrieved_chunks: list[RetrievedChunk],
        safety_flags: list[str],
        correlation_id: str,
    ) -> LLMResponse:
        raise NotImplementedError


class LocalMockChatProvider(LLMProvider):
    def generate_answer(
        self,
        *,
        question: str,
        prompt: PromptTemplate,
        retrieved_chunks: list[RetrievedChunk],
        safety_flags: list[str],
        correlation_id: str,
    ) -> LLMResponse:
        if not retrieved_chunks:
            return LLMResponse(
                answer=(
                    "I could not find enough approved synthetic policy context to answer. "
                    "Route this to a human reviewer."
                ),
                provider="local-mock",
                model_name="local-deterministic-rag",
                fallback_mode=True,
            )

        lead = retrieved_chunks[0]
        second = retrieved_chunks[1] if len(retrieved_chunks) > 1 else None
        answer_parts = [
            f"Based on {lead.title}, {summarize_excerpt(lead.excerpt)} [{lead.source_id}]"
        ]
        if second:
            answer_parts.append(
                f"Related guidance from {second.title} says {summarize_excerpt(second.excerpt)} "
                f"[{second.source_id}]"
            )
        if safety_flags:
            answer_parts.append(
                "Safety note: this response should be reviewed before operational use."
            )
        return LLMResponse(
            answer=" ".join(answer_parts),
            provider="local-mock",
            model_name="local-deterministic-rag",
            fallback_mode=True,
        )


class AzureOpenAIChatProvider(LLMProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-02-01",
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version

    @classmethod
    def from_env(cls) -> "AzureOpenAIChatProvider | None":
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
        if not endpoint or not api_key or not deployment:
            return None

        return cls(
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        )

    def generate_answer(
        self,
        *,
        question: str,
        prompt: PromptTemplate,
        retrieved_chunks: list[RetrievedChunk],
        safety_flags: list[str],
        correlation_id: str,
    ) -> LLMResponse:
        context = format_context(retrieved_chunks)
        prompt_text = prompt.template_text.format(question=question, context=context)
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
            f"?api-version={self.api_version}"
        )
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Use only provided synthetic context. Return concise answers with "
                        "inline citations using the source ids."
                    ),
                },
                {"role": "user", "content": prompt_text},
            ],
            "temperature": 0.0,
            "max_tokens": 500,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                headers={"api-key": self.api_key, "content-type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        answer = body["choices"][0]["message"]["content"]
        return LLMResponse(
            answer=str(answer),
            provider="azure-openai",
            model_name=self.deployment,
            fallback_mode=False,
        )


def llm_provider_from_env() -> LLMProvider:
    return AzureOpenAIChatProvider.from_env() or LocalMockChatProvider()


def format_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"Source id: {chunk.source_id}\nTitle: {chunk.title}\nContent: {chunk.excerpt}"
        for chunk in chunks
    )


def summarize_excerpt(excerpt: str, max_words: int = 28) -> str:
    words = excerpt.replace("\n", " ").split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(".,;:") + "..."
