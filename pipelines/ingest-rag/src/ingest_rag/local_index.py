import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ingest_rag.models import ChunkRecord

LOCAL_INDEX_SCHEMA_VERSION = "careai-local-rag-index-v1"


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimension")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def write_local_index(
    chunks: list[ChunkRecord],
    output_path: str | Path,
    *,
    embedding_dimension: int,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": LOCAL_INDEX_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "embedding_dimension": embedding_dimension,
        "chunks": [asdict(chunk) for chunk in chunks],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_local_index(index_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(index_path).read_text(encoding="utf-8"))


def keyword_overlap_score(query: str, content: str) -> float:
    query_terms = {term for term in query.lower().split() if len(term) > 2}
    if not query_terms:
        return 0.0
    content_terms = set(content.lower().split())
    return len(query_terms & content_terms) / len(query_terms)


def search_local_index(
    *,
    index_path: str | Path,
    query: str,
    query_vector: list[float],
    allowed_role: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    payload = load_local_index(index_path)
    results: list[dict[str, Any]] = []
    for chunk in payload["chunks"]:
        if allowed_role and allowed_role not in chunk["allowed_roles"]:
            continue

        vector_score = cosine_similarity(query_vector, chunk["content_vector"])
        hybrid_score = vector_score + 0.15 * keyword_overlap_score(query, chunk["content"])
        result = {
            "id": chunk["id"],
            "doc_id": chunk["doc_id"],
            "chunk_id": chunk["chunk_id"],
            "title": chunk["title"],
            "version": chunk["version"],
            "sensitivity_class": chunk["sensitivity_class"],
            "source_uri": chunk["source_uri"],
            "allowed_roles": chunk["allowed_roles"],
            "content": chunk["content"],
            "score": round(hybrid_score, 8),
        }
        results.append(result)

    return sorted(results, key=lambda item: item["score"], reverse=True)[:top_k]
