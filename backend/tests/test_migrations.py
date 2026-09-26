import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_fresh_migrations(tmp_path: Path) -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    database = tmp_path / "migrated.db"
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
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
        "alerts",
        "events",
    }.issubset(tables)
    with closing(sqlite3.connect(database)) as db:
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("drill", "true", "2026-09-27 00:00:00"),
        )
        db.commit()
    helper = Path(__file__).parents[1] / "scripts" / "sqlite_backup.py"
    backup = tmp_path / "backup.db"
    subprocess.run([sys.executable, str(helper), str(database), str(backup)], check=True)
    with closing(sqlite3.connect(database)) as db:
        db.execute("DELETE FROM settings WHERE key = 'drill'")
        db.commit()
    subprocess.run(
        [sys.executable, str(helper), str(backup), str(database), "--replace"], check=True
    )
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT value FROM settings WHERE key = 'drill'").fetchone() == ("true",)
