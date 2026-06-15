import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

from careai_control_plane_api.database import resolve_database_url

MIGRATIONS_PATH = Path(__file__).resolve().parent / "migrations"


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade_database(database_url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url or resolve_database_url()), revision)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run control-plane database migrations.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--revision", default="head")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    upgrade_database(database_url=args.database_url, revision=args.revision)


if __name__ == "__main__":
    main()
