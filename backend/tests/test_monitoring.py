import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.inventory import device_out
from netsentinel.main import create_app
from netsentinel.models import Device, NetworkScope, ScanRun, Setting, utcnow
from netsentinel.monitoring import schedule_once, service_became_reachable
from netsentinel.scans import execute_scan, recover_interrupted


class FakeProbe:
    def __init__(self, result: ProbeResult):
        self.result = result

    async def scan(self, _scope):
        return [self.result]


def app_with_scope(path: Path):
    app = create_app(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        db.add(
            NetworkScope(
                name="Test",
                cidr="10.0.0.0/28",
                enabled=True,
                approved_at=utcnow(),
                max_concurrency=1,
                connect_timeout_ms=100,
                ports="80",
            )
        )
        db.commit()
    return app


def queued_run(app) -> int:
    with app.state.session_factory() as db:
        run = ScanRun(scope_id=1, type="manual", status="queued", host_count=0)
        db.add(run)
        db.commit()
        return run.id


def test_two_missed_scans_required_for_offline(tmp_path: Path) -> None:
    app = app_with_scope(tmp_path / "test.db")
    app.state.prober = FakeProbe(
        ProbeResult("10.0.0.7", True, 2, "aa:bb:cc:dd:ee:ff", "tcp", {80: "reachable"})
    )
    asyncio.run(execute_scan(app, queued_run(app)))
    with app.state.session_factory() as db:
        device = db.scalar(select(Device))
        assert device is not None and device_out(db, device)["status"] == "online"
    app.state.prober = FakeProbe(
        ProbeResult("10.0.0.7", None, None, None, "probe", {80: "unknown"})
    )
    asyncio.run(execute_scan(app, queued_run(app)))
    with app.state.session_factory() as db:
        device = db.scalar(select(Device))
        assert device is not None and device_out(db, device)["status"] == "unconfirmed"
    asyncio.run(execute_scan(app, queued_run(app)))
    with app.state.session_factory() as db:
        device = db.scalar(select(Device))
        assert device is not None and device_out(db, device)["status"] == "offline"


def test_scheduler_is_opt_in_and_does_not_duplicate_after_restart(tmp_path: Path) -> None:
    app = app_with_scope(tmp_path / "test.db")
    app.state.scan_queue = asyncio.Queue(maxsize=4)
    assert schedule_once(app) == 0
    with app.state.session_factory() as db:
        db.add(Setting(key="schedule_enabled", value="true", updated_at=utcnow()))
        db.commit()
    assert schedule_once(app) == 1
    assert schedule_once(app) == 0
    recover_interrupted(app)
    assert schedule_once(app) == 0


def test_monitoring_settings_validation_and_baseline(tmp_path: Path) -> None:
    app = app_with_scope(tmp_path / "test.db")
    client = TestClient(app)
    assert client.get("/api/v1/settings").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    headers = {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}
    assert client.get("/api/v1/settings").json()["schedule_enabled"] is False
    assert (
        client.patch("/api/v1/settings", json={"interval_minutes": 1}, headers=headers).status_code
        == 422
    )
    assert (
        client.patch("/api/v1/settings", json={"schedule_enabled": True}, headers=headers).json()[
            "schedule_enabled"
        ]
        is True
    )
    assert service_became_reachable(None, "reachable") is False
    assert service_became_reachable("unknown", "reachable") is True
    assert service_became_reachable("reachable", "reachable") is False
