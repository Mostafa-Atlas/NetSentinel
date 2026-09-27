from pathlib import Path

from fastapi.testclient import TestClient

from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.inventory import reconcile_device
from netsentinel.main import create_app
from netsentinel.models import (
    Device,
    NetworkProfile,
    NetworkScope,
    ScanRun,
    ServiceObservation,
    utcnow,
)


def setup(tmp_path: Path) -> tuple[TestClient, int, int, int]:
    app = create_app(f"sqlite:///{(tmp_path / 'investigation.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        profile = NetworkProfile(name="Home", description="")
        other_profile = NetworkProfile(name="Office", description="")
        db.add_all([profile, other_profile])
        db.flush()
        scope = NetworkScope(
            profile_id=profile.id,
            name="Home",
            cidr="10.0.0.0/24",
            enabled=True,
            approved_at=utcnow(),
            max_concurrency=1,
            connect_timeout_ms=100,
            ports="80",
        )
        db.add(scope)
        db.flush()
        run = ScanRun(scope_id=scope.id, type="manual", status="completed", host_count=2)
        db.add(run)
        db.flush()
        first = reconcile_device(
            db, ProbeResult("10.0.0.2", True, 2, None, "tcp", {}), profile_id=profile.id
        )
        second = reconcile_device(
            db, ProbeResult("10.0.0.3", True, 3, None, "tcp", {}), profile_id=profile.id
        )
        db.flush()
        db.add(
            ServiceObservation(
                device_id=first.id,
                scan_run_id=run.id,
                ip="10.0.0.2",
                port=80,
                protocol="tcp",
                state="reachable",
                observed_at=utcnow(),
            )
        )
        third = Device(
            profile_id=other_profile.id,
            display_name="Other",
            identity_confidence="provisional",
            known_state="unknown",
            notes="",
            first_seen_at=utcnow(),
            last_seen_at=utcnow(),
        )
        db.add(third)
        db.flush()
        ids = (first.id, second.id, third.id)
        db.commit()
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    return client, *ids


def test_comparison_and_owner_annotation(tmp_path: Path) -> None:
    client, first, second, other = setup(tmp_path)
    csrf = {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}
    comparison = client.get(f"/api/v1/devices/compare?left_id={first}&right_id={second}")
    assert comparison.status_code == 200
    assert comparison.json()["left"]["services"][0]["port"] == 80
    assert (
        client.get(f"/api/v1/devices/compare?left_id={first}&right_id={other}").status_code == 409
    )
    path = "/api/v1/topology/annotations"
    body = {"source_id": second, "target_id": first, "label": "Known switch", "note": "Owner note"}
    assert client.post(path, json=body).status_code == 403
    assert client.post(path, json={**body, "target_id": other}, headers=csrf).status_code == 409
    created = client.post(path, json=body, headers=csrf)
    assert created.status_code == 201, created.text
    assert created.json()["provenance"] == "owner_supplied_unverified"
    assert client.post(path, json=body, headers=csrf).status_code == 409
    assert (
        sum(
            link["kind"] == "owner_annotation"
            for link in client.get("/api/v1/topology").json()["links"]
        )
        == 1
    )
    assert client.get(path).json()[0]["note"] == "Owner note"
    assert client.get("/api/v1/events?event_type=topology_link_added").json()["total"] == 1
    assert client.delete(f"{path}/{created.json()['id']}", headers=csrf).status_code == 200
    assert client.get(path).json() == []
