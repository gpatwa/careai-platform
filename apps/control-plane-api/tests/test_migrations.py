from careai_control_plane_api.database import Database
from careai_control_plane_api.migration_runner import upgrade_database
from sqlalchemy import create_engine, inspect, text


def sqlite_url(tmp_path, name: str) -> str:
    return f"sqlite:///{tmp_path / name}"


def test_upgrade_database_creates_model_error_events_table(tmp_path) -> None:
    database_url = sqlite_url(tmp_path, "control-plane-migration.db")

    upgrade_database(database_url)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "model_error_events" in inspector.get_table_names()
    assert "prediction_events" in inspector.get_table_names()
    assert "alembic_version" in inspector.get_table_names()

    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert revision == "0001_initial_control_plane_schema"


def test_prepare_schema_uses_migrations_for_persistent_database(tmp_path) -> None:
    database_url = sqlite_url(tmp_path, "control-plane-prepare.db")
    database = Database(database_url)

    database.prepare_schema()

    inspector = inspect(database.engine)
    assert "model_error_events" in inspector.get_table_names()
    assert "alembic_version" in inspector.get_table_names()
