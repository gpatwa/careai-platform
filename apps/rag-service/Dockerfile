FROM python:3.12-slim

WORKDIR /app

COPY requirements-dev.txt /tmp/requirements-dev.txt
COPY libs/common-python /tmp/libs/common-python
COPY pipelines/ingest-rag /tmp/pipelines/ingest-rag
COPY data/synthetic_docs /app/data/synthetic_docs
COPY apps/rag-service /app

RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && pip install --no-cache-dir /tmp/libs/common-python /tmp/pipelines/ingest-rag /app

EXPOSE 8002

CMD ["uvicorn", "careai_rag_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
