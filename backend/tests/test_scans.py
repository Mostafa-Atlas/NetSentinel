import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.main import create_app
from netsentinel.models import (
    Device,
    NetworkScope,
    Observation,
    ScanRun,
    ServiceObservation,
    utcnow,
)
from netsentinel.scans import recover_interrupted


class FakeProbe:
    async def scan(self, _scope):
        return [
            ProbeResult(
                ip="10.0.0.7",
                reachable=True,
                latency_ms=4.2,
                mac="aa:bb:cc:dd:ee:ff",
                source="tcp",
                services={22: "unreachable", 80: "reachable"},
            )
        ]


def setup_app(path: Path):
    app = create_app(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(app.state.engine)
    app.state.prober = FakeProbe()
    return app


def authorize(client: TestClient) -> dict[str, str]:
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    return {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}


def test_scan_requires_approved_scope_and_persists_fake_evidence(tmp_path: Path) -> None:
    app = setup_app(tmp_path / "test.db")
    with TestClient(app) as client:
        assert client.post("/api/v1/scans", json={"scope_id": 1}).status_code == 401
        headers = authorize(client)
        assert (
            client.post("/api/v1/scans", json={"scope_id": 1}, headers=headers).status_code == 400
        )
        scope = client.post(
            "/api/v1/scopes",
            json={"name": "Test", "cidr": "10.0.0.0/28", "approved": True},
            headers=headers,
        )
        assert scope.status_code == 201
        queued = client.post(
            "/api/v1/scans", json={"scope_id": scope.json()["id"]}, headers=headers
        )
        assert queued.status_code == 202
        run_id = queued.json()["id"]
        for _ in range(100):
            run = client.get(f"/api/v1/scans/{run_id}").json()
            if run["status"] != "queued" and run["status"] != "running":
                break
            time.sleep(0.01)
        assert run["status"] == "completed", run
        assert run["host_count"] == 1
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(Device.id))) == 1
        assert db.scalar(select(func.count(Observation.id))) == 1
        assert db.scalar(select(func.count(ServiceObservation.id))) == 2


def test_out_of_scope_probe_result_fails_without_persistence(tmp_path: Path) -> None:
    app = setup_app(tmp_path / "test.db")
    with TestClient(app) as client:
        headers = authorize(client)
        scope = client.post(
            "/api/v1/scopes",
            json={"name": "Test", "cidr": "192.168.1.0/24", "approved": True},
            headers=headers,
        ).json()
        queued = client.post(
            "/api/v1/scans", json={"scope_id": scope["id"]}, headers=headers
        ).json()
        for _ in range(100):
            run = client.get(f"/api/v1/scans/{queued['id']}").json()
            if run["status"] == "failed":
                break
            time.sleep(0.01)
        assert run["status"] == "failed"
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(Observation.id))) == 0


def test_interrupted_jobs_fail_on_restart(tmp_path: Path) -> None:
    app = setup_app(tmp_path / "test.db")
    with app.state.session_factory() as db:
        db.add(
            NetworkScope(
                name="Test",
                cidr="10.0.0.0/28",
                enabled=True,
                approved_at=utcnow(),
                max_concurrency=1,
                connect_timeout_ms=100,
                ports="22",
            )
        )
        db.commit()
        db.add(ScanRun(scope_id=1, type="manual", status="running", host_count=0))
        db.commit()
    recover_interrupted(app)
    with app.state.session_factory() as db:
        run = db.scalar(select(ScanRun))
        assert run is not None and run.status == "failed"
        assert run.error_summary == "Interrupted by application restart"


def test_full_queue_refuses_scan(tmp_path: Path) -> None:
    app = setup_app(tmp_path / "test.db")
    app.state.scan_queue = asyncio.Queue(maxsize=1)
    app.state.scan_queue.put_nowait(999)
    client = TestClient(app)
    headers = authorize(client)
    scope = client.post(
        "/api/v1/scopes",
        json={"name": "Test", "cidr": "10.0.0.0/28", "approved": True},
        headers=headers,
    ).json()
    response = client.post("/api/v1/scans", json={"scope_id": scope["id"]}, headers=headers)
    assert response.status_code == 429
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(ScanRun.id))) == 0
