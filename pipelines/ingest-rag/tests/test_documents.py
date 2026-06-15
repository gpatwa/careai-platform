from ingest_rag.documents import chunk_documents, chunk_text, load_documents


def test_load_documents_assigns_required_metadata() -> None:
    documents = load_documents("data/synthetic_docs")

    assert len(documents) == 5
    doc_ids = {document.metadata.doc_id for document in documents}
    assert "prior_authorization_policy" in doc_ids
    assert "responsible_ai_guidelines" in doc_ids
    for document in documents:
        assert document.metadata.title
        assert document.metadata.version == "2026.06"
        assert document.metadata.sensitivity_class == "synthetic-internal"
        assert document.metadata.source_uri.startswith("file://")
        assert document.metadata.allowed_roles
        assert "real patient data" in document.text or "synthetic" in document.text.lower()


def test_chunk_text_is_deterministic_and_uses_overlap() -> None:
    text = "Alpha " * 80 + "\n\n" + "Beta " * 80 + "\n\n" + "Gamma " * 80

    first = chunk_text(text, max_chars=180, overlap_chars=30)
    second = chunk_text(text, max_chars=180, overlap_chars=30)

    assert first == second
    assert len(first) > 1
    assert all(len(chunk) <= 220 for chunk in first)


def test_chunk_documents_preserves_metadata() -> None:
    documents = load_documents("data/synthetic_docs")
    chunks = chunk_documents(documents, max_chars=500, overlap_chars=80)

    assert len(chunks) >= len(documents)
    assert all(chunk.id for chunk in chunks)
    assert all(chunk.doc_id for chunk in chunks)
    assert all(chunk.allowed_roles for chunk in chunks)
    assert all(chunk.sensitivity_class == "synthetic-internal" for chunk in chunks)
