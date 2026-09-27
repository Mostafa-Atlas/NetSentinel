"""Synthetic read-load and SQLite backup drill; sends no LAN probes."""

import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from time import perf_counter

from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from netsentinel.main import create_app
from netsentinel.models import Device, DeviceAddress, NetworkScope, Observation, ScanRun, utcnow


def main() -> None:
    backend = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="netsentinel-load-") as temporary:
        root = Path(temporary)
        database = root / "load.db"
        config = Config(str(backend / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
        command.upgrade(config, "head")
        app = create_app(f"sqlite:///{database.as_posix()}")
        with app.state.session_factory() as db:
            scope = NetworkScope(
                name="Synthetic",
                cidr="10.0.0.0/24",
                enabled=True,
                approved_at=utcnow(),
                max_concurrency=1,
                connect_timeout_ms=100,
                ports="80,443",
            )
            db.add(scope)
            db.flush()
            runs = []
            for _ in range(8):
                run = ScanRun(
                    scope_id=scope.id,
                    type="manual",
                    status="completed",
                    host_count=128,
                    started_at=utcnow(),
                    finished_at=utcnow(),
                )
                db.add(run)
                db.flush()
                runs.append(run)
            for host in range(1, 129):
                ip = f"10.0.0.{host}"
                device = Device(
                    display_name=ip,
                    identity_confidence="provisional",
                    known_state="unknown",
                    notes="",
                    first_seen_at=utcnow(),
                    last_seen_at=utcnow(),
                )
                db.add(device)
                db.flush()
                db.add(
                    DeviceAddress(
                        device_id=device.id, ip=ip, first_seen_at=utcnow(), last_seen_at=utcnow()
                    )
                )
                for run in runs:
                    db.add(
                        Observation(
                            device_id=device.id,
                            scan_run_id=run.id,
                            observed_at=utcnow(),
                            source="synthetic",
                            ip=ip,
                            reachable=True,
                            latency_ms=2.0,
                            raw_summary="Synthetic",
                        )
                    )
            db.commit()
        client = TestClient(app)
        assert (
            client.post(
                "/api/v1/auth/bootstrap",
                json={"username": "load-owner", "password": "synthetic-test-password"},
            ).status_code
            == 201
        )
        for path in ("/api/v1/overview", "/api/v1/devices?limit=50", "/api/v1/topology"):
            started = perf_counter()
            response = client.get(path)
            elapsed = perf_counter() - started
            assert response.status_code == 200, response.text
            print(f"{path}: {elapsed:.3f}s")
        backup = root / "backup.db"
        restored = root / "restored.db"
        helper = backend / "scripts" / "sqlite_backup.py"
        subprocess.run([sys.executable, str(helper), str(database), str(backup)], check=True)
        subprocess.run([sys.executable, str(helper), str(backup), str(restored)], check=True)
        with closing(sqlite3.connect(restored)) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert connection.execute("SELECT count(*) FROM devices").fetchone() == (128,)
            assert connection.execute("SELECT count(*) FROM observations").fetchone() == (1024,)
        print("Backup/restore integrity and row counts: passed")
        client.close()
        app.state.engine.dispose()


if __name__ == "__main__":
    main()
