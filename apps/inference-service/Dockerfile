FROM python:3.12-slim

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

COPY requirements.txt /tmp/requirements.txt
COPY requirements-inference.txt /tmp/requirements-inference.txt
COPY libs/common-python /tmp/libs/common-python
COPY apps/inference-service /app

RUN cd /tmp \
    && pip install -r requirements-inference.txt \
    && pip install /tmp/libs/common-python /app

USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=3)"

CMD ["uvicorn", "careai_inference_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
