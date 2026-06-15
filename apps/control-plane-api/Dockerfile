FROM python:3.12-slim

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/local \
    && chown -R appuser:appuser /app

COPY requirements.txt /tmp/requirements.txt
COPY libs/common-python /tmp/libs/common-python
COPY apps/control-plane-api /app

RUN pip install -r /tmp/requirements.txt \
    && pip install /tmp/libs/common-python /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["uvicorn", "careai_control_plane_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
