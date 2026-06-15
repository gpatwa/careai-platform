import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from careai_control_plane_api.models import Base

DEFAULT_SQLITE_URL = "sqlite:///./data/local/control-plane.db"


def resolve_database_url() -> str:
    return (
        os.getenv("CONTROL_PLANE_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_SQLITE_URL
    )


class Database:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or resolve_database_url()
        self.engine = self._create_engine(self.database_url)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    def create_all(self) -> None:
        Base.metadata.create_all(bind=self.engine)

    def upgrade(self) -> None:
        from careai_control_plane_api.migration_runner import upgrade_database

        upgrade_database(self.database_url)

    def prepare_schema(self) -> None:
        if self.database_url == "sqlite:///:memory:":
            self.create_all()
            return
        self.upgrade()

    def session(self) -> Generator[Session, None, None]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def _create_engine(self, database_url: str) -> Engine:
        if database_url.startswith("sqlite"):
            if database_url != "sqlite:///:memory:":
                database_path = database_url.removeprefix("sqlite:///")
                Path(database_path).parent.mkdir(parents=True, exist_ok=True)

            kwargs: dict[str, object] = {"connect_args": {"check_same_thread": False}}
            if database_url == "sqlite:///:memory:":
                kwargs["poolclass"] = StaticPool
            return create_engine(database_url, **kwargs)

        return create_engine(database_url, pool_pre_ping=True)
