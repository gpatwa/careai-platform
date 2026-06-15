FROM python:3.12-slim

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/local /app/data/synthetic_docs \
    && chown -R appuser:appuser /app

COPY requirements.txt /tmp/requirements.txt
COPY libs/common-python /tmp/libs/common-python
COPY pipelines/ingest-rag /tmp/pipelines/ingest-rag
COPY data/synthetic_docs /app/data/synthetic_docs
COPY apps/rag-service /app

RUN pip install -r /tmp/requirements.txt \
    && pip install /tmp/libs/common-python /tmp/pipelines/ingest-rag /app

USER appuser

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/healthz', timeout=3)"

CMD ["uvicorn", "careai_rag_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
