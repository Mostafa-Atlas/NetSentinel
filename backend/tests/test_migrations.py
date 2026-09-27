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
        "network_profiles",
        "device_hints",
        "monitor_rules",
        "monitor_checks",
        "agent_enrollments",
        "agent_nonces",
        "agent_reports",
        "topology_links",
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


def test_phase_two_upgrade_preserves_existing_inventory(tmp_path: Path) -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    database = tmp_path / "existing.db"
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "0004")
    with closing(sqlite3.connect(database)) as db:
        db.execute(
            "INSERT INTO network_scopes "
            "(id, name, cidr, enabled, approved_at, max_concurrency, "
            "connect_timeout_ms, ports, created_at) "
            "VALUES (1, 'Home', '10.0.0.0/28', 1, CURRENT_TIMESTAMP, "
            "1, 100, '80', CURRENT_TIMESTAMP)"
        )
        db.execute(
            "INSERT INTO devices "
            "(id, display_name, identity_confidence, known_state, notes, "
            "first_seen_at, last_seen_at) "
            "VALUES (1, 'Desk', 'observed_mac', 'known', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        db.execute(
            "INSERT INTO device_addresses "
            "(device_id, ip, mac, first_seen_at, last_seen_at) "
            "VALUES (1, '10.0.0.7', 'aa:bb:cc:dd:ee:01', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        db.commit()
    command.upgrade(config, "head")
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT profile_id, enabled FROM network_scopes").fetchone() == (1, 1)
        assert db.execute("SELECT profile_id, display_name FROM devices").fetchone() == (1, "Desk")
        assert db.execute("SELECT ip FROM device_addresses").fetchone() == ("10.0.0.7",)
