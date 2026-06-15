FROM python:3.12-slim

WORKDIR /app

COPY requirements-dev.txt /tmp/requirements-dev.txt
COPY libs/common-python /tmp/libs/common-python
COPY apps/inference-service /app

RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && pip install --no-cache-dir /tmp/libs/common-python /app

EXPOSE 8001

CMD ["uvicorn", "careai_inference_service.main:app", "--host", "0.0.0.0", "--port", "8001"]

