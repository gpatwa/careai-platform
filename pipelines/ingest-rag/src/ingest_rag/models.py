from dataclasses import dataclass, field


@dataclass(frozen=True)
class DocumentMetadata:
    doc_id: str
    title: str
    version: str
    sensitivity_class: str
    source_uri: str
    allowed_roles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceDocument:
    metadata: DocumentMetadata
    text: str


@dataclass(frozen=True)
class ChunkRecord:
    id: str
    doc_id: str
    chunk_id: str
    title: str
    version: str
    sensitivity_class: str
    source_uri: str
    allowed_roles: list[str]
    content: str
    content_vector: list[float] = field(default_factory=list)
