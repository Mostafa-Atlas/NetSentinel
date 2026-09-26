from pathlib import Path

from fastapi.testclient import TestClient

from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.inventory import reconcile_device
from netsentinel.main import create_app
from netsentinel.models import NetworkScope, Observation, ScanRun, utcnow


def test_overview_and_topology_mark_inferred_links(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    assert client.get("/api/v1/overview").status_code == 401
    assert client.get("/api/v1/topology").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    assert client.get("/api/v1/overview").json()["device_count"] == 0
    with app.state.session_factory() as db:
        scope = NetworkScope(
            name="Home",
            cidr="192.168.1.0/24",
            enabled=True,
            approved_at=utcnow(),
            max_concurrency=1,
            connect_timeout_ms=100,
            ports="80",
        )
        db.add(scope)
        db.flush()
        run = ScanRun(
            scope_id=scope.id,
            type="manual",
            status="completed",
            host_count=1,
            started_at=utcnow(),
            finished_at=utcnow(),
        )
        db.add(run)
        db.flush()
        device = reconcile_device(
            db, ProbeResult("192.168.1.7", True, 3.0, "aa:bb:cc:dd:ee:ff", "tcp", {80: "reachable"})
        )
        db.add(
            Observation(
                device_id=device.id,
                scan_run_id=run.id,
                observed_at=utcnow(),
                source="tcp",
                reachable=True,
                latency_ms=3.0,
                raw_summary="Mocked connect",
            )
        )
        db.commit()
    overview = client.get("/api/v1/overview").json()
    assert overview["device_count"] == 1
    assert overview["online_count"] == 1
    assert overview["review_count"] == 1
    assert overview["latest_scan"]["status"] == "completed"
    assert overview["updated_at"].endswith("Z")
    topology = client.get("/api/v1/topology").json()
    assert len(topology["nodes"]) == 2
    assert topology["links"] == [
        {
            "source": "scope:1",
            "target": "device:1",
            "kind": "inferred",
            "provenance": "IP observed in approved subnet; physical link unknown",
        }
    ]
