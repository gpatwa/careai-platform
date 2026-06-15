import logging

import httpx

from careai_rag_service.schemas import PromptTemplate, PromptTemplateSummary

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = PromptTemplate(
    id="local-healthcare-ops-rag",
    name="Healthcare Operations RAG",
    version="local-v1",
    template_text=(
        "You are a healthcare operations assistant for synthetic policy documents. "
        "Answer only from the retrieved context. If context is insufficient, say so. "
        "Do not provide medical diagnosis or treatment advice. Cite sources inline using "
        "the provided source ids in square brackets.\n\n"
        "Question:\n{question}\n\n"
        "Retrieved context:\n{context}\n\n"
        "Answer:"
    ),
    owner="careai-platform",
    safety_notes=(
        "Synthetic-document RAG prompt. Requires citations and human review for clinical advice."
    ),
    status="approved",
    source="local",
)


class PromptRegistry:
    def __init__(self, control_plane_url: str | None, timeout_seconds: float = 2.0) -> None:
        self.control_plane_url = control_plane_url.rstrip("/") if control_plane_url else None
        self.timeout_seconds = timeout_seconds

    def get_prompts(self) -> list[PromptTemplateSummary]:
        prompts = self._fetch_control_plane_prompts()
        approved_prompts = [prompt for prompt in prompts if prompt.status == "approved"]
        if approved_prompts:
            return [
                PromptTemplateSummary(
                    id=prompt.id,
                    name=prompt.name,
                    version=prompt.version,
                    status=prompt.status,
                    owner=prompt.owner,
                    source=prompt.source,
                    safety_notes=prompt.safety_notes,
                )
                for prompt in approved_prompts
            ]

        return [
            PromptTemplateSummary(
                id=DEFAULT_PROMPT.id,
                name=DEFAULT_PROMPT.name,
                version=DEFAULT_PROMPT.version,
                status=DEFAULT_PROMPT.status,
                owner=DEFAULT_PROMPT.owner,
                source=DEFAULT_PROMPT.source,
                safety_notes=DEFAULT_PROMPT.safety_notes,
            )
        ]

    def select_prompt(self, prompt_template_id: str | None = None) -> PromptTemplate:
        prompts = self._fetch_control_plane_prompts()
        approved_prompts = [prompt for prompt in prompts if prompt.status == "approved"]
        if prompt_template_id:
            for prompt in approved_prompts:
                if prompt.id == prompt_template_id:
                    return prompt
            logger.warning(
                "approved prompt template not found; using local default",
                extra={"prompt_template_id": prompt_template_id},
            )
            return DEFAULT_PROMPT

        return approved_prompts[0] if approved_prompts else DEFAULT_PROMPT

    def _fetch_control_plane_prompts(self) -> list[PromptTemplate]:
        if not self.control_plane_url:
            return []

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(f"{self.control_plane_url}/prompts")
                response.raise_for_status()
                rows = response.json()
        except httpx.HTTPError as exc:
            logger.warning("control-plane prompt registry unavailable", extra={"error": str(exc)})
            return []

        prompts: list[PromptTemplate] = []
        for row in rows:
            prompts.append(
                PromptTemplate(
                    id=row["id"],
                    name=row["name"],
                    version=row["version"],
                    template_text=row["template_text"],
                    owner=row["owner"],
                    safety_notes=row.get("safety_notes", ""),
                    status=row.get("status", "draft"),
                    source="control-plane",
                )
            )
        return prompts
