from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_fresh_migrations(tmp_path: Path) -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}")
    command.upgrade(config, "head")
    tables = set(inspect(create_engine(config.get_main_option("sqlalchemy.url"))).get_table_names())
    assert {
        "users",
        "sessions",
        "network_scopes",
        "settings",
        "scan_runs",
        "devices",
        "device_addresses",
        "observations",
        "service_observations",
    }.issubset(tables)
