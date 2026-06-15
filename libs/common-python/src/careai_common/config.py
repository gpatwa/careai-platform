import os
from functools import lru_cache

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    service_name: str
    environment: str = "local"
    log_level: str = "INFO"
    service_port: int
    database_url: str = "postgresql://careai:careai_dev_password@localhost:5432/careai"
    redis_url: str = "redis://localhost:6379/0"
    mlflow_tracking_uri: str = "http://localhost:5000"
    synthetic_data_seed: int = Field(default=20260614, ge=0)


@lru_cache(maxsize=32)
def load_settings(service_name: str, default_port: int) -> AppSettings:
    """Load deterministic local settings from environment variables."""

    return AppSettings(
        service_name=os.getenv("SERVICE_NAME", service_name),
        environment=os.getenv("ENVIRONMENT", "local"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        service_port=int(os.getenv("SERVICE_PORT", str(default_port))),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://careai:careai_dev_password@localhost:5432/careai",
        ),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        mlflow_tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        synthetic_data_seed=int(os.getenv("SYNTHETIC_DATA_SEED", "20260614")),
    )
