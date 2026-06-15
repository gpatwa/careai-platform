import hashlib
import re
from dataclasses import replace
from pathlib import Path

from ingest_rag.models import ChunkRecord, DocumentMetadata, SourceDocument

DEFAULT_DOCS_DIR = Path("data/synthetic_docs")
DEFAULT_VERSION = "2026.06"
DEFAULT_SENSITIVITY_CLASS = "synthetic-internal"
DEFAULT_ALLOWED_ROLES = ["platform_admin", "clinical_ops", "member_support"]

DOCUMENT_CATALOG: dict[str, dict[str, object]] = {
    "prior_authorization_policy.md": {
        "doc_id": "prior_authorization_policy",
        "allowed_roles": ["platform_admin", "clinical_ops", "member_support"],
    },
    "claims_review_policy.md": {
        "doc_id": "claims_review_policy",
        "allowed_roles": ["platform_admin", "claims_ops"],
    },
    "member_support_playbook.md": {
        "doc_id": "member_support_playbook",
        "allowed_roles": ["platform_admin", "member_support"],
    },
    "pharmacy_exception_policy.md": {
        "doc_id": "pharmacy_exception_policy",
        "allowed_roles": ["platform_admin", "pharmacy_ops", "clinical_ops"],
    },
    "responsible_ai_guidelines.md": {
        "doc_id": "responsible_ai_guidelines",
        "allowed_roles": ["platform_admin", "model_risk_reviewer", "clinical_ops"],
    },
}


def title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback


def source_uri_for(path: Path) -> str:
    return path.resolve().as_uri()


def load_documents(input_dir: str | Path = DEFAULT_DOCS_DIR) -> list[SourceDocument]:
    docs_dir = Path(input_dir)
    documents: list[SourceDocument] = []
    for path in sorted(docs_dir.glob("*.md")):
        catalog_entry = DOCUMENT_CATALOG.get(path.name, {})
        text = path.read_text(encoding="utf-8")
        doc_id = str(catalog_entry.get("doc_id") or path.stem)
        allowed_roles = list(catalog_entry.get("allowed_roles") or DEFAULT_ALLOWED_ROLES)
        metadata = DocumentMetadata(
            doc_id=doc_id,
            title=title_from_markdown(text, path.stem.replace("_", " ").title()),
            version=DEFAULT_VERSION,
            sensitivity_class=DEFAULT_SENSITIVITY_CLASS,
            source_uri=source_uri_for(path),
            allowed_roles=allowed_roles,
        )
        documents.append(SourceDocument(metadata=metadata, text=text))
    return documents


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, max_chars: int = 900, overlap_chars: int = 150) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")

    paragraphs = [normalize_whitespace(part) for part in text.split("\n\n")]
    paragraphs = [part for part in paragraphs if part]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(paragraph):
                chunks.append(paragraph[start : start + max_chars].strip())
                start += max_chars - overlap_chars
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            overlap = current[-overlap_chars:].strip() if overlap_chars else ""
            current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph

    if current:
        chunks.append(current)
    return chunks


def stable_chunk_key(doc_id: str, chunk_index: int, content: str) -> str:
    digest = hashlib.sha256(f"{doc_id}:{chunk_index}:{content}".encode()).hexdigest()
    return digest[:32]


def chunk_documents(
    documents: list[SourceDocument],
    *,
    max_chars: int = 900,
    overlap_chars: int = 150,
) -> list[ChunkRecord]:
    records: list[ChunkRecord] = []
    for document in documents:
        for index, content in enumerate(
            chunk_text(document.text, max_chars=max_chars, overlap_chars=overlap_chars)
        ):
            chunk_id = f"{document.metadata.doc_id}-{index:04d}"
            records.append(
                ChunkRecord(
                    id=stable_chunk_key(document.metadata.doc_id, index, content),
                    doc_id=document.metadata.doc_id,
                    chunk_id=chunk_id,
                    title=document.metadata.title,
                    version=document.metadata.version,
                    sensitivity_class=document.metadata.sensitivity_class,
                    source_uri=document.metadata.source_uri,
                    allowed_roles=list(document.metadata.allowed_roles),
                    content=content,
                )
            )
    return records


def with_source_root(document: SourceDocument, source_root: str) -> SourceDocument:
    return SourceDocument(
        metadata=replace(
            document.metadata,
            source_uri=f"{source_root.rstrip('/')}/{document.metadata.doc_id}.md",
        ),
        text=document.text,
    )
