from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.inventory import reconcile_device
from netsentinel.main import create_app
from netsentinel.models import Device, DeviceAddress, NetworkScope, Observation, ScanRun, utcnow


def probe(ip: str, mac: str | None) -> ProbeResult:
    return ProbeResult(
        ip=ip, reachable=True, latency_ms=1.0, mac=mac, source="tcp", services={80: "reachable"}
    )


def test_identity_reconciliation_preserves_address_history(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        first = reconcile_device(db, probe("10.0.0.7", "aa:bb:cc:dd:ee:01"))
        db.commit()
        first_id = first.id
        same = reconcile_device(db, probe("10.0.0.8", "aa:bb:cc:dd:ee:01"))
        assert same.id == first_id
        db.commit()
        assert db.scalar(select(func.count(DeviceAddress.id))) == 2
        reused_ip = reconcile_device(db, probe("10.0.0.7", "aa:bb:cc:dd:ee:02"))
        assert reused_ip.id != first_id
        db.commit()
        provisional = reconcile_device(db, probe("10.0.0.7", None))
        assert provisional.id != reused_ip.id
        db.commit()
        assert reconcile_device(db, probe("10.0.0.7", None)).id == provisional.id
        assert db.scalar(select(func.count(Device.id))) == 3


def test_inventory_api_labels_and_history(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        scope = NetworkScope(
            name="Test",
            cidr="10.0.0.0/28",
            enabled=True,
            approved_at=utcnow(),
            max_concurrency=1,
            connect_timeout_ms=100,
            ports="80",
        )
        db.add(scope)
        db.flush()
        run = ScanRun(scope_id=scope.id, type="manual", status="completed", host_count=1)
        db.add(run)
        db.flush()
        device = reconcile_device(db, probe("10.0.0.7", "aa:bb:cc:dd:ee:01"))
        db.add(
            Observation(
                device_id=device.id,
                scan_run_id=run.id,
                observed_at=utcnow(),
                source="tcp",
                reachable=True,
                latency_ms=1,
                raw_summary="Mocked connect",
            )
        )
        db.commit()
        device_id = device.id
    client = TestClient(app)
    assert client.get("/api/v1/devices").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    headers = {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}
    response = client.get("/api/v1/devices?search=10.0.0.7")
    assert response.status_code == 200 and response.json()["total"] == 1
    assert response.json()["items"][0]["status"] == "online"
    assert (
        client.patch(
            f"/api/v1/devices/{device_id}", json={"display_name": "Desk", "known_state": "known"}
        ).status_code
        == 403
    )
    saved = client.patch(
        f"/api/v1/devices/{device_id}",
        json={"display_name": "Desk", "known_state": "known", "notes": "Owner workstation"},
        headers=headers,
    )
    assert saved.status_code == 200 and saved.json()["display_name"] == "Desk"
    assert saved.json()["addresses"][0]["mac"] == "aa:bb:cc:dd:ee:01"
    assert client.get("/api/v1/devices?known_state=known").json()["total"] == 1
    assert client.get(f"/api/v1/devices/{device_id}/observations").json()["total"] == 1
    assert client.get(f"/api/v1/devices/{device_id}/services").json()["total"] == 0
